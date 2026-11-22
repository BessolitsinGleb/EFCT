from fastapi import Response, APIRouter, Depends, HTTPException
from .database import get_db
from sqlalchemy.orm import Session
from .models import Coordinates, Mooving, Movement_info, User, Role, PlacementRule
from sqlalchemy import select, cast, String, update, desc
from .schemas import FindCells, AddCont, Layer, Mooves, Recomend, UploadData, RuleIn, RuleOut, RuleToggle
from typing import List
from datetime import datetime
from .mig_to_excel import (migration, calculation_score, ask_ai, calculation_movement_price,
                           upload_company_mov, to_utc_naive, hours_until)
from .placement import EMPTY, placement_problem, blocked_by, rules_check
from .yard import YARD, load_rules, yard_info
from .settings import get_current_user

router = APIRouter(prefix="/container", tags=['container'])


def require_transceiver(user: User):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")


def all_cells(db: Session) -> dict:
    """Вся площадка одним запросом: cell_id -> строка БД."""
    return {c.cell_id: c for c in db.query(Coordinates).order_by(Coordinates.cell_id).all()}


def container_cells(db: Session, value: str) -> list:
    """Ячейки, занятые контейнером (у 40-футового — две), по возрастанию ряда."""
    return (db.query(Coordinates)
              .filter(cast(Coordinates.value, String) == str(value), Coordinates.value != EMPTY)
              .order_by(Coordinates.row_num).all())


def clear_values():
    return dict(value=EMPTY, size=None, company='empty', cont_type='null',
                path_num_to=None, path_num_from=None, sent_date=None)


@router.get("/yard")
def get_yard(user: User = Depends(get_current_user)):
    """Параметры площадки (для интерфейса)."""
    return yard_info()


@router.get("/find_cells", response_model=List[FindCells])
def find_cells(value: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    return container_cells(db, value)


@router.post("/add")
def add_cont(data: AddCont, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    if data.value == EMPTY or container_cells(db, data.value):
        raise HTTPException(409, "This container number already exists in the database.")
    cells = all_cells(db)
    if data.cell_id not in cells:
        raise HTTPException(404, detail="not found")
    problem = placement_problem(YARD, cells, data.cell_id, data.size)
    if problem:
        raise HTTPException(403, problem)
    fp = YARD.footprint(data.cell_id, data.size)
    ok, _, reason = rules_check(YARD, load_rules(db), fp, data.company, data.cont_type, data.size)
    if not ok:
        raise HTTPException(403, reason)

    db.add(Mooving(value=data.value))
    try:
        price = calculation_movement_price('adding', data.size, fp[0], path=data.path_num_from)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.add(Movement_info(moove_type="adding", value=data.value, path_num_from=data.path_num_from,
                         cell_to=fp[0], movement_time=datetime.utcnow(), company=data.company, price=price))
    db.execute(update(Coordinates).where(Coordinates.cell_id.in_(fp)).values(
        value=data.value, size=data.size, company=data.company, cont_type=data.cont_type,
        sent_date=to_utc_naive(data.sent_date), path_num_from=data.path_num_from, path_num_to=data.path_num_to))
    db.commit()
    migration()
    return {"status": "success", "cell": fp[0], "cells": fp, "container": data.value, "price": price}


@router.get("/check")
def check_cont(cont_num: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """Какие ячейки и контейнеры находятся над контейнером."""
    require_transceiver(user)
    own = container_cells(db, cont_num)
    if not own:
        raise HTTPException(404, "not found")
    cells = all_cells(db)
    list_cells, list_conts = [], []
    for c in own:
        a = YARD.above(c.cell_id)
        while a is not None:
            list_cells.append(a)
            list_conts.append(cells[a].value if a in cells else EMPTY)
            a = YARD.above(a)
    if not list_cells:
        return "there are no other containers above your container"
    return list_cells, list_conts


@router.get("/find_cont")
def find_cont(cell_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    cell = db.get(Coordinates, cell_id)
    if not cell:
        raise HTTPException(404, "not found")
    return {"status": "success", "container num": cell.value, "size": cell.size,
            "path num": cell.path_num_to, "sent date": cell.sent_date}


@router.post("/loading")
def load_cont(value: str, path_num: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    own = container_cells(db, value)
    if not own:
        raise HTTPException(404, "not found")
    if blocked_by(YARD, all_cells(db), [c.cell_id for c in own]):
        raise HTTPException(403, "the cell above is not free")
    first = own[0]
    try:
        price = calculation_movement_price('loading', first.size, first.cell_id, path=path_num)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.add(Movement_info(moove_type="loading", value=value, path_num_to=path_num, cell_from=first.cell_id,
                         movement_time=datetime.utcnow(), company=first.company, price=price))
    db.execute(update(Mooving).where(cast(Mooving.value, String) == value).values(deleted_at=datetime.utcnow()))
    db.execute(update(Coordinates).where(Coordinates.cell_id.in_([c.cell_id for c in own])).values(**clear_values()))
    db.commit()
    migration()
    return {"status": "success", "price": price}


@router.post("/rearrangement")
def rearrange_cont(value: str, cell: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    own = container_cells(db, value)
    cells = all_cells(db)
    if not own or cell not in cells:
        raise HTTPException(404, "not found")
    src = own[0]
    if blocked_by(YARD, cells, [c.cell_id for c in own]):
        raise HTTPException(403, "the cell above is not free")
    problem = placement_problem(YARD, cells, cell, src.size, moving_value=value)
    if problem:
        raise HTTPException(403, problem)
    fp = YARD.footprint(cell, src.size)
    ok, _, reason = rules_check(YARD, load_rules(db), fp, src.company, src.cont_type, src.size)
    if not ok:
        raise HTTPException(403, reason)

    price = calculation_movement_price('rearrangement', size=src.size, cell_1=src.cell_id, cell_2=fp[0])
    keep = dict(value=value, size=src.size, company=src.company, cont_type=src.cont_type,
                path_num_to=src.path_num_to, path_num_from=src.path_num_from, sent_date=src.sent_date)
    db.add(Movement_info(moove_type="rearrangement", value=value, cell_from=src.cell_id, cell_to=fp[0],
                         movement_time=datetime.utcnow(), company=src.company, price=price))
    db.execute(update(Coordinates).where(Coordinates.cell_id.in_([c.cell_id for c in own])).values(**clear_values()))
    db.execute(update(Coordinates).where(Coordinates.cell_id.in_(fp)).values(**keep))
    db.commit()
    migration()
    return {"status": "success", "container": value, "from": src.cell_id, "to": fp[0], "cells": fp, "price": price}


@router.get("/layer", response_model=List[Layer])
def get_layer(layer: str, db: Session = Depends(get_db)):
    return db.execute(select(Coordinates).where(Coordinates.layer == layer)).scalars().all()


@router.get("/mooves", response_model=List[Mooves])
def mooves(db: Session = Depends(get_db)):
    stmt = select(Movement_info).order_by(desc(Movement_info.moove_id)).limit(10)
    return db.execute(stmt).scalars().all()


@router.post("/recommend")
def recommend_cells(data: Recomend, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    try:
        delta_time = hours_until(data.sent_date)
        size = int(data.size)
        cells = all_cells(db)          # вся площадка одним запросом, порядок фиксирован
        rules = load_rules(db)
        recommendations = []
        for cell_id, cell in cells.items():
            if cell.value != EMPTY:
                continue
            try:
                fp = YARD.footprint(cell_id, size)
            except ValueError:
                continue
            if fp[0] != cell_id:       # 40 фут.: перебираем пары по первой ячейке
                continue
            if placement_problem(YARD, cells, cell_id, size):
                continue
            ok, bonus, _ = rules_check(YARD, rules, fp, data.company, data.cont_type, size)
            if not ok:
                continue
            # контейнер под новым уедет раньше? (для 40 фут. — самый ранний из двух нижних)
            lower = [cells[b] for b in (YARD.below(c) for c in fp) if b is not None]
            dates = [hours_until(l.sent_date) for l in lower if l.sent_date is not None]
            lower_delta_time = min(dates) if dates else None
            try:
                score = calculation_score(delta_time, cell_id, data.path_to, lower_delta_time)
            except ValueError as e:
                raise HTTPException(400, str(e))
            score = round(score * (1 + bonus), 2)
            recommendations.append({"cell": cell_id, "cells": fp, "score": score})

        recommendations.sort(key=lambda x: x["score"], reverse=True)
        top_5 = recommendations[:5]
        if not top_5:
            return {"top 5": [], "объяснение": "Нет подходящих свободных ячеек."}
        best = top_5[0]
        layers, cols = YARD.layers, YARD.columns
        paths = ", ".join(f"путь {i + 1} возле ряда {r}" for i, r in enumerate(YARD.path_rows))
        prompt = f"""
            Ты объясняешь решение системы контейнерного терминала.
            Информация о терминале: ярусы {', '.join(layers)} (нижний {layers[0]}, верхний {layers[-1]}),
            {YARD.rows} рядов, пути: {paths}; колонны {', '.join(cols)}, крайние ({cols[0]} и {cols[-1]})
            предназначены для контейнеров с быстрой/средней скоростью отправки.
            40-футовый контейнер занимает пару соседних рядов (1–2, 3–4, ...).

            Контейнер: размер {size} фут., часов до отправки: {delta_time}. Классы срочности:
            до 96 ч — срочный (ближе к пути, верхний ярус, крайние колонны), 96–240 ч — средний
            (средний ярус и колонна), больше 240 ч — долгий (нижний ярус, около 5 рядов от пути).
            Путь отправления: {data.path_to}.

            Выбранная ячейка: {', '.join(best['cells'])} (ярус {best['cell'][0]}), оценка {best['score']}.

            Объясни кратко: почему выбрана эта ячейка, как влияет расстояние до пути, как влияет ярус,
            как это уменьшает перестановки. Ответ не длиннее 3 предложений.
            """
        try:
            explanation = ask_ai(prompt)
        except Exception as e:  # сервис пояснений недоступен — рекомендация всё равно выдаётся
            print(f"ask_ai error: {e}")
            explanation = 'Пояснение временно недоступно.'
        return {"top 5": top_5, "объяснение": explanation}
    finally:
        db.close()


@router.post("/data_upload")
def uploading_to_company(data: UploadData, user: User = Depends(get_current_user)):
    require_transceiver(user)
    report = upload_company_mov(data.company, data.start_data, data.end_data)
    if report is None:
        raise HTTPException(500, "Не удалось сформировать отчёт")
    filename, content, rows = report
    return Response(content, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Rows": str(rows), "Access-Control-Expose-Headers": "Content-Disposition, X-Rows"})


# ---------- настраиваемые правила размещения ----------

def validate_rule(data: RuleIn):
    if data.mode not in ("require", "prefer", "forbid"):
        raise HTTPException(422, "mode: require | prefer | forbid")
    if data.layers and any(l not in YARD.layers for l in data.layers):
        raise HTTPException(422, f"ярусы площадки: {YARD.layers}")
    if data.columns and any(c not in YARD.columns for c in data.columns):
        raise HTTPException(422, f"колонны площадки: {YARD.columns}")
    for r in (data.row_from, data.row_to):
        if r is not None and not 1 <= r <= YARD.rows:
            raise HTTPException(422, f"ряды площадки: 1–{YARD.rows}")


@router.get("/rules", response_model=List[RuleOut])
def list_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    return db.query(PlacementRule).order_by(PlacementRule.id).all()


@router.post("/rules", response_model=RuleOut)
def create_rule(data: RuleIn, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    validate_rule(data)
    rule = PlacementRule(**data.model_dump())
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.patch("/rules/{rule_id}", response_model=RuleOut)
def toggle_rule(rule_id: int, data: RuleToggle, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_transceiver(user)
    rule = db.get(PlacementRule, rule_id)
    if rule is None:
        raise HTTPException(404, "Правило не найдено")
    rule.is_active = data.is_active
    db.commit()
    db.refresh(rule)
    return rule
