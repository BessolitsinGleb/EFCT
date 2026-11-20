"""Площадка и оценка, собранные из настроек (.env), и начальное заполнение БД."""
from sqlalchemy.orm import Session
from .core import settings
from .placement import YardConfig, ScoringConfig, Rule, EMPTY

YARD = YardConfig(
    layers=settings.YARD_LAYERS.strip(),
    columns=settings.YARD_COLUMNS.strip(),
    rows=settings.YARD_ROWS,
    path_rows=tuple(int(x) for x in settings.YARD_PATH_ROWS.split(",") if x.strip()),
)
SCORING = ScoringConfig(
    urgent_hours=settings.SCORE_URGENT_HOURS,
    medium_hours=settings.SCORE_MEDIUM_HOURS,
    lower_penalty=settings.SCORE_LOWER_PENALTY,
)


def ensure_yard_cells(db: Session) -> int:
    """Создаёт недостающие ячейки площадки (существующие не трогает). Возвращает число созданных."""
    from .models import Coordinates
    existing = {c for (c,) in db.query(Coordinates.cell_id).all()}
    created = 0
    for cell_id in YARD.all_cells():
        if cell_id in existing:
            continue
        layer, column, row = YARD.parse(cell_id)
        db.add(Coordinates(cell_id=cell_id, layer=layer, row_num=row, coord_type=column,
                           value=EMPTY, company="empty", cont_type="null"))
        created += 1
    db.commit()
    return created


def ensure_cranes(db: Session) -> None:
    from .models import Crane
    if db.query(Crane).count() == 0:
        for name in [n.strip() for n in settings.YARD_CRANES.split(",") if n.strip()]:
            db.add(Crane(name=name))
        db.commit()


def load_rules(db: Session) -> list:
    from .models import PlacementRule
    return [Rule(id=r.id, name=r.name, mode=r.mode, company=r.company, cont_type=r.cont_type, size=r.size,
                 layers=r.layers, columns=r.columns, row_from=r.row_from, row_to=r.row_to,
                 bonus=r.bonus, is_active=r.is_active)
            for r in db.query(PlacementRule).order_by(PlacementRule.id).all()]


def yard_info() -> dict:
    return {"layers": list(YARD.layers), "columns": list(YARD.columns), "rows": YARD.rows,
            "path_rows": list(YARD.path_rows), "pair_rule": "40-футовый контейнер занимает пару рядов 1–2, 3–4, ..."}
