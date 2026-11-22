"""Признаки для агента. Одни и те же функции используются при обучении (симулятор)
и в работающей программе (состояние площадки из БД) — иначе агент «видел» бы разное.

Время везде в часах на одной шкале: now — текущий момент, dep — плановая отправка.
cells: cell_id -> объект с полями value (EMPTY = свободно), size, dep.
"""
import numpy as np

K = 8          # агент выбирает одну из K лучших по формуле ячеек
F = 12         # признаков на ячейку-кандидата
G = 12         # общих признаков


def candidates(P, cfg, cells, size, exclude=frozenset()):
    """Все допустимые позиции: (якорная ячейка, footprint). Правила штабелирования — из placement.py."""
    out = []
    for c in cfg.all_cells():
        if cells[c].value != P.EMPTY:
            continue
        try:
            fp = cfg.footprint(c, size)
        except ValueError:
            continue
        if fp[0] != c or any(x[1:] in exclude for x in fp):
            continue
        if P.placement_problem(cfg, cells, c, size) is None:
            out.append((c, fp))
    return out


def lower_dep(cfg, cells, fp):
    """Самая ранняя отправка среди контейнеров прямо под footprint (None — ставим на землю)."""
    lows = [cells[b].dep for b in (cfg.below(x) for x in fp) if b is not None and cells[b].dep is not None]
    return min(lows) if lows else None


def score(P, cfg, sc, cells, cont, now, c, fp, bonus=0.0):
    lo = lower_dep(cfg, cells, fp)
    s = P.calculation_score(round(cont["dep"] - now, 2), c, cont["path"],
                            None if lo is None else round(lo - now, 2), cfg, sc)
    return s * (1 + bonus)


def top_k(P, cfg, sc, cells, cont, now, cands, k=K, bonus_of=None):
    """K лучших кандидатов по формуле (по убыванию оценки)."""
    scored = []
    for c, fp in cands:
        b = bonus_of(fp) if bonus_of else 0.0
        scored.append((score(P, cfg, sc, cells, cont, now, c, fp, b), c, fp))
    scored.sort(key=lambda t: (-t[0], t[1]))
    return scored[:k]


def _cell_features(P, cfg, cells, cont, now, s, c, fp):
    n = len(cfg.layers)
    layer, col, row = cfg.parse(c)
    li = cfg.layer_idx(layer)
    d = abs(row - cfg.path_row(cont["path"])) / cfg.d_norm
    lo = lower_dep(cfg, cells, fp)
    has_lower = 0.0 if lo is None else 1.0
    gap = 0.0 if lo is None else float(np.clip((lo - cont["dep"]) / 240.0, -1, 1))  # >0: нижний уедет позже — хорошо
    penalty = 1.0 if (lo is not None and lo < cont["dep"]) else 0.0
    above = (n - 1 - li) / max(n - 1, 1)                     # сколько ещё можно поставить сверху
    # 20-футовый в пустую пару рядов «ломает» место для 40-футового
    frag = 0.0
    if cont["size"] == 20:
        mate = row + 1 if row % 2 == 1 else row - 1
        if 1 <= mate <= cfg.rows:
            mc = f"{layer}{col}{mate}"
            if cells[mc].value == P.EMPTY:
                frag = 1.0
    stack = [f"{l}{cl}{row}" for l in cfg.layers for cl in cfg.columns]
    crowd = sum(cells[x].value != P.EMPTY for x in stack) / len(stack)
    # насколько рано уезжают соседи по ряду (риск, что этот контейнер будет мешать)
    deps = [cells[x].dep for x in stack if cells[x].dep is not None]
    near_dep = 0.0 if not deps else float(np.clip((min(deps) - now) / 480.0, 0, 1))
    return [s, li / max(n - 1, 1), 1.0 if cfg.is_edge_column(col) else 0.0, d, has_lower, gap, penalty,
            above, frag, crowd, near_dep, 1.0]                # последний — «кандидат существует»


def observation(P, cfg, cells, cont, now, top, relocation=False, sc=None):
    """Вектор наблюдения (K*F + G) и маска действий (K)."""
    obs = np.zeros(K * F + G, dtype=np.float32)
    mask = np.zeros(K, dtype=bool)
    for i, (s, c, fp) in enumerate(top[:K]):
        obs[i * F:(i + 1) * F] = _cell_features(P, cfg, cells, cont, now, s, c, fp)
        mask[i] = True
    dt = cont["dep"] - now
    urgent = sc.urgent_hours if sc else 96
    medium = sc.medium_hours if sc else 240
    total = len(cells)
    occ = sum(v.value != P.EMPTY for v in cells.values()) / total
    g = [1.0 if cont["size"] == 40 else 0.0,
         1.0 if dt <= urgent else 0.0, 1.0 if urgent < dt <= medium else 0.0, 1.0 if dt > medium else 0.0,
         float(np.clip(dt / 480.0, 0, 1.5)), occ, len(top) / K, 1.0 if relocation else 0.0,
         *[1.0 if cont["path"] == p else 0.0 for p in (1, 2, 3)], 1.0]
    obs[K * F:] = g[:G]
    return obs, mask
