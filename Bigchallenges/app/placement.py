"""Правила площадки ЭДКТ без привязки к БД и серверу.

Здесь живёт вся «предметная» логика: геометрия площадки (YardConfig), занимаемые
контейнером позиции (20 фут. — одна ячейка, 40 фут. — фиксированная пара рядов),
правила штабелирования, оценка ячейки, тарификация и настраиваемые правила размещения.
Модуль чистый (без БД), поэтому его же использует имитационное тестирование.
"""
from dataclasses import dataclass, field

EMPTY = "0"


@dataclass(frozen=True)
class YardConfig:
    layers: str = "ABC"            # снизу вверх
    columns: str = "XYZ"           # крайние колонны — первая и последняя
    rows: int = 30
    path_rows: tuple = (5, 15, 25)  # путь 1 -> ряд 5, путь 2 -> ряд 15, ...

    def __post_init__(self):
        if len(set(self.layers)) != len(self.layers) or not self.layers:
            raise ValueError("ярусы должны быть уникальными буквами")
        if len(set(self.columns)) != len(self.columns) or not self.columns:
            raise ValueError("колонны должны быть уникальными буквами")
        if self.rows < 2:
            raise ValueError("рядов должно быть не меньше 2")
        if any(not 1 <= r <= self.rows for r in self.path_rows):
            raise ValueError("ряд пути вне площадки")

    @property
    def d_norm(self) -> int:
        """Нормировка удалённости от пути (для 30 рядов = 25, как в исходной версии)."""
        return max(self.rows - 5, 1)

    def path_row(self, path: int) -> int:
        if path is None or not 1 <= int(path) <= len(self.path_rows):
            raise ValueError(f"unknown path: {path}")
        return self.path_rows[int(path) - 1]

    def parse(self, cell_id: str):
        layer, column = cell_id[0], cell_id[1]
        row = int(cell_id[2:])
        if layer not in self.layers or column not in self.columns or not 1 <= row <= self.rows:
            raise ValueError(f"cell outside the yard: {cell_id}")
        return layer, column, row

    def all_cells(self):
        return [f"{l}{c}{r}" for l in self.layers for c in self.columns for r in range(1, self.rows + 1)]

    def layer_idx(self, layer: str) -> int:
        return self.layers.index(layer)

    def is_edge_column(self, column: str) -> bool:
        return column in (self.columns[0], self.columns[-1])

    def below(self, cell_id: str):
        i = self.layer_idx(cell_id[0])
        return None if i == 0 else self.layers[i - 1] + cell_id[1:]

    def above(self, cell_id: str):
        i = self.layer_idx(cell_id[0])
        return None if i == len(self.layers) - 1 else self.layers[i + 1] + cell_id[1:]

    def footprint(self, cell_id: str, size: int) -> list:
        """Ячейки, которые занимает контейнер. 40 фут. — фиксированная пара рядов (1–2, 3–4, ...)."""
        layer, column, row = self.parse(cell_id)
        if size == 20:
            return [cell_id]
        if size == 40:
            anchor = row if row % 2 == 1 else row - 1
            if anchor + 1 > self.rows:
                raise ValueError(f"40-foot container does not fit: row {anchor} has no pair")
            return [f"{layer}{column}{anchor}", f"{layer}{column}{anchor + 1}"]
        raise ValueError(f"unsupported container size: {size}")


DEFAULT_YARD = YardConfig()


@dataclass(frozen=True)
class ScoringConfig:
    urgent_hours: float = 96       # до 96 ч — срочный
    medium_hours: float = 240      # 96–240 ч — средний, дальше — долгий
    lower_penalty: float = 0.5     # множитель, если нижний контейнер уедет раньше
    long_target_rows: int = 5      # долгие ставим примерно в 5 рядах от пути


DEFAULT_SCORING = ScoringConfig()


# ---------- штабелирование ----------

def placement_problem(cfg: YardConfig, cells: dict, cell_id: str, size: int, moving_value=None):
    """None, если контейнер размера size можно поставить в cell_id, иначе текст причины.
    cells — словарь cell_id -> объект с полями value и size (строки БД или симуляции).
    moving_value — номер переставляемого контейнера: он не может быть опорой сам себе."""
    try:
        fp = cfg.footprint(cell_id, size)
    except ValueError as e:
        return str(e)
    for c in fp:
        obj = cells.get(c)
        if obj is None:
            return "not found"
        if obj.value != EMPTY:
            return "cell is not empty"
        b = cfg.below(c)
        if b is not None:
            lo = cells.get(b)
            if lo is None or lo.value == EMPTY or (moving_value is not None and lo.value == moving_value):
                return "there is no support under the cell"
            if lo.size != size:
                return "The container size does not match the one below it"
    return None


def blocked_by(cfg: YardConfig, cells: dict, footprint: list) -> list:
    """Занятые ячейки непосредственно над контейнером (мешают его достать)."""
    out = []
    for c in footprint:
        a = cfg.above(c)
        if a is not None and cells.get(a) is not None and cells[a].value != EMPTY:
            out.append(a)
    return out


# ---------- оценка ячейки ----------

def calculation_score(delta_time, cell, path_from, lower_delta_time,
                      cfg: YardConfig = DEFAULT_YARD, sc: ScoringConfig = DEFAULT_SCORING):
    layer, column, row = cfg.parse(cell)
    d = abs(row - cfg.path_row(path_from)) / cfg.d_norm
    n, idx, edge = len(cfg.layers), cfg.layer_idx(layer), cfg.is_edge_column(column)

    if delta_time <= sc.urgent_hours:              # срочный: ближе к пути, выше, крайние колонны
        lv = (idx + 1) / n
        cv = 1 if edge else 0.5
        score = (100 * (1 - d) + 60 * lv + 20 * cv) / 180
    elif delta_time <= sc.medium_hours:            # средний: средний ярус, средние колонны
        mid = (n - 1) / 2
        lv = 1 - 0.5 * abs(idx - mid) / max(mid, 1) if n > 1 else 1
        cv = 0.5 if edge else 1
        score = (60 * (1 - d) + 40 * lv + 10 * cv) / 110
    else:                                          # долгий: нижний ярус, в стороне от пути
        lv = 1 - idx / (n - 1) if n > 1 else 1
        cv = 0.5 if edge else 1
        d_ideal = abs(d - sc.long_target_rows / cfg.d_norm)
        score = (30 * (1 - d_ideal) + 70 * lv + 5 * cv) / 105

    if lower_delta_time is not None and lower_delta_time < delta_time:
        score *= sc.lower_penalty
    return round(score, 2)


# ---------- тарификация ----------

def calculation_movement_price(mov_type, size, cell_1, cell_2=None, path=None, cfg: YardConfig = DEFAULT_YARD):
    power = {20: 1, 40: 2}
    if size not in power:
        raise ValueError(f"unsupported container size: {size}")
    n = len(cfg.layers)
    if mov_type in ("adding", "loading"):
        CONST_PRICE = 50                            # подъём/опускание на транспорт
        layer, column, row = cfg.parse(cell_1)
        lay_price = n - cfg.layer_idx(layer)        # чем ниже, тем дороже (A=3, B=2, C=1)
        col_price = 2 if cfg.is_edge_column(column) else 3
        row_price = abs(row - cfg.path_row(path)) / cfg.d_norm
        return power[size] * (25 * lay_price + 35 * col_price + 100 * row_price + CONST_PRICE)
    if mov_type == "rearrangement":
        lf, cf, rf = cfg.parse(cell_1)
        lt, ct, rt = cfg.parse(cell_2)
        up, down = n - cfg.layer_idx(lf), n - cfg.layer_idx(lt)
        col_price = abs(cfg.columns.index(cf) - cfg.columns.index(ct))
        row_price = abs(rt - rf) / max(cfg.rows - 1, 1)
        return round(power[size] * (up * 25 + down * 25 + col_price * 50 + row_price * 500))
    raise ValueError(f"unknown movement type: {mov_type}")


# ---------- настраиваемые правила размещения ----------

@dataclass
class Rule:
    """Правило размещения. Условия (company, cont_type, size) — None означает «любой».
    Зона: допустимые ярусы/колонны (строка букв) и диапазон рядов (None — без ограничения).
    mode: 'require' — размещать только в зоне (жёсткое), 'prefer' — бонус к оценке,
    'forbid' — запрещено размещать в зоне."""
    name: str
    mode: str = "require"
    company: str | None = None
    cont_type: str | None = None
    size: int | None = None
    layers: str | None = None
    columns: str | None = None
    row_from: int | None = None
    row_to: int | None = None
    bonus: float = 0.2
    is_active: bool = True
    id: int | None = None

    def matches(self, company=None, cont_type=None, size=None) -> bool:
        if not self.is_active:
            return False
        if self.company and (company or "").strip().lower() != self.company.strip().lower():
            return False
        if self.cont_type and (cont_type or "").strip().lower() != self.cont_type.strip().lower():
            return False
        if self.size and size != self.size:
            return False
        return True

    def in_zone(self, cfg: YardConfig, cell_id: str) -> bool:
        layer, column, row = cfg.parse(cell_id)
        if self.layers and layer not in self.layers:
            return False
        if self.columns and column not in self.columns:
            return False
        if self.row_from is not None and row < self.row_from:
            return False
        if self.row_to is not None and row > self.row_to:
            return False
        return True


def rules_check(cfg: YardConfig, rules: list, footprint: list, company=None, cont_type=None, size=None):
    """(ok, bonus, причина). Все ячейки контейнера должны удовлетворять жёстким правилам."""
    bonus = 0.0
    for r in rules:
        if not r.matches(company, cont_type, size):
            continue
        inside = all(r.in_zone(cfg, c) for c in footprint)
        if r.mode == "require" and not inside:
            return False, 0.0, f"нарушено правило «{r.name}»"
        if r.mode == "forbid" and any(r.in_zone(cfg, c) for c in footprint):
            return False, 0.0, f"нарушено правило «{r.name}»"
        if r.mode == "prefer" and inside:
            bonus += r.bonus
    return True, bonus, None
