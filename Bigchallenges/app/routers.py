from fastapi import APIRouter, Depends, HTTPException
from .database import get_db
from sqlalchemy.orm import Session
from .models import Coordinates, Mooving, Movement_info, User, Role
from sqlalchemy import select, cast, String, update, desc
from .schemas import FindCells, AddCont, Layer, Mooves, Recomend, UploadData
from typing import List
from datetime import datetime, timezone
from .mig_to_excel import migration, calculation_score, check_stack_size, ask_ai, calculation_movement_price, upload_company_mov
from .settings import get_current_user

router = APIRouter(prefix="/container", tags=['container'])

@router.get("/find_cells", response_model=List[FindCells])
def find_cells(
    value: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    list_ = select(Coordinates).where(cast(Coordinates.value, String) == str(value))

    values = db.execute(list_)
    res = values.scalars().all()
    return res

@router.post("/add")
def add_cont(
    data: AddCont,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    stmt = select(Coordinates).where(Coordinates.cell_id == data.cell_id)
    cell_ = db.execute(stmt).scalar_one_or_none()
    cont = select(Coordinates).where(Coordinates.value == data.value)
    cont = db.execute(cont).scalars().all()

    if cont:
        raise HTTPException(409, "This container number already exists in the database.")
    if not cell_:
        raise HTTPException(404, detail="not found")
    
    if cell_.value != "0":
        raise HTTPException(403, "cell is not empty")
   
    cell = list(cell_.cell_id)
    if cell[0] == 'B':
        cell[0] = 'A'
        a_cell = ''.join(cell)

        num = select(Coordinates).where(Coordinates.cell_id == a_cell)
        num = db.execute(num).scalar_one_or_none()
        if num.value == "0":
            raise HTTPException(403, "there is no support under the cell")
        # if num.cont_type != cell_.cont_type:
        #     raise HTTPException(403, "The container type does not match the one below it")
        if num.size != data.size:
            raise HTTPException(403, "The container size does not match the one below it")
        
    if cell[0] == 'C':
        cell[0] = 'B'
        b_cell = ''.join(cell)

        num = select(Coordinates).where(Coordinates.cell_id == b_cell)
        num = db.execute(num).scalar_one_or_none()
        if float(num.value) == "0":
            raise HTTPException(403, "there is no support under the cell")
        # if num.cont_type != cell_.cont_type:
        #     raise HTTPException(403, "The container type does not match the one below it")
        if num.size != data.size:
            raise HTTPException(403, "The container size does not match the one below it")
            
    time = Mooving(value= data.value)
    db.add(time)
    
    price = calculation_movement_price(mov_type='adding',
                                       cell_1=data.cell_id,
                                       size= data.size,
                                       path= data.path_num_from)
    
    movement = Movement_info(moove_type= "adding",
                             value= data.value,
                             path_num_from= data.path_num_from,
                             movement_time= datetime.utcnow(),
                             company= data.company,
                             price= price)
    db.add(movement)

    update_stmt = (
        update(Coordinates)
        .where(Coordinates.cell_id == data.cell_id)
        .values(value=data.value,
                size=data.size,
                company=data.company,
                cont_type=data.cont_type,
                sent_date=data.sent_date,
                path_num_from=data.path_num_from,
                path_num_to=data.path_num_to) 
    )

    db.execute(update_stmt)
    db.commit()
    migration()
    return {"status": "success", "cell": data.cell_id, "container": data.value, "price": price}

@router.get("/check")
def check_cont(
    # type: str,
    cont_num: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    list_cells = []
    list_conts = []
    cont = select(Coordinates).where(cast(Coordinates.value, String) == cont_num)
    cont = db.execute(cont).scalar_one_or_none()

    if not cont:
        raise HTTPException(404, "not found")
    
    cell = list(cont.cell_id)
    if cell[0] == 'A':
        cell[0] = 'B'
        b_cell = ''.join(cell)
        list_cells.append(b_cell)

        num = select(Coordinates).where(Coordinates.cell_id == b_cell)
        num = db.execute(num).scalar_one_or_none()
        list_conts.append(num.value)

        cell[0] = 'C'
        c_cell = ''.join(cell)
        list_cells.append(c_cell)

        num = select(Coordinates).where(Coordinates.cell_id == c_cell)
        num = db.execute(num).scalar_one_or_none()
        list_conts.append(num.value)

        return list_cells, list_conts
    
    if cell[0] == 'B':

        cell[0] = 'C'
        c_cell = ''.join(cell)
        list_cells.append(c_cell)

        num = select(Coordinates).where(Coordinates.cell_id == c_cell)
        num = db.execute(num).scalar_one_or_none()
        list_conts.append(num.value)

        return list_cells, list_conts
    
    if cell[0] == 'C':
        return "there are no other containers above your container"

@router.get("/find_cont")
def find_cont(cell_id: str,
              user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    cell = select(Coordinates).where(Coordinates.cell_id == cell_id)
    cell = db.execute(cell).scalar_one_or_none()

    if not cell:
        raise HTTPException(404, "not found")
    
    return {"status": "success", "container num": cell.value, "size": cell.size, "path num": cell.path_num_to, "sent date": cell.sent_date}

@router.post("/loading")
def load_cont(value: str,
              path_num: int,
              user: User = Depends(get_current_user),
              db: Session = Depends(get_db)):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    stmt = select(Coordinates).where(cast(Coordinates.value, String) == value)
    cont = db.execute(stmt).scalar_one_or_none()

    if not cont:
        raise HTTPException(404, "not found")
    if value == '0':
        raise HTTPException(404, "no")
    
    cell = list(cont.cell_id)
    if cell[0] == 'A':
        cell[0] = 'B'
        b_cell = ''.join(cell)

        num = select(Coordinates).where(Coordinates.cell_id == b_cell)
        num = db.execute(num).scalar_one_or_none()
        if num.value != "0":
            raise HTTPException(403, "the cell above is not free")
    
    if cell[0] == 'B':
        cell[0] = 'C'
        c_cell = ''.join(cell)

        num = select(Coordinates).where(Coordinates.cell_id == c_cell)
        num = db.execute(num).scalar_one_or_none()
        if num.value != "0":
            raise HTTPException(403, "the cell above is not free")
        
    res = update(Coordinates).where(cast(Coordinates.value, String) == value).values(value = "0",
                                                                                    size = None,
                                                                                    company = 'empty',
                                                                                    cont_type = 'null',
                                                                                    path_num_to = None,
                                                                                    path_num_from = None,
                                                                                    sent_date = None)

    time = update(Mooving).where(cast(Mooving.value, String) == value).values(deleted_at = datetime.utcnow())
    
    price = calculation_movement_price(mov_type='loading',
                                       cell_1=cont.cell_id,
                                       size=cont.size,
                                       path=path_num)
    
    movement = Movement_info(moove_type= "loading",
                             value= value,
                             path_num_to= path_num,
                             movement_time= datetime.utcnow(),
                             company= cont.company,
                             price= price)
    
    db.add(movement)
    db.execute(time)
    db.execute(res)
    db.commit()
    migration()
    return {"status": "success",
            "price": price}

@router.post("/rearrangement")
def rearrange_cont(value: str,
                   cell: str,
                   user: User = Depends(get_current_user),
                   db: Session = Depends(get_db)):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    stmt = select(Coordinates).where(cast(Coordinates.value, String) == value)
    cell_from = db.execute(stmt).scalar_one_or_none()

    cell_to = select(Coordinates).where(Coordinates.cell_id == cell)
    cell_to = db.execute(cell_to).scalar_one_or_none()

    if not cell_from:
        raise HTTPException(404, "not found")
    if not cell_to:
        raise HTTPException(404, "not found")
    if cell_from.value == "0":
        raise HTTPException(403, "cell is empty")
    if cell_to.value != "0":
        raise HTTPException(403, "cell is not empty")
    
    cell__ = list(cell_from.cell_id)
    if cell__[0] == 'A':
        cell__[0] = 'B'
        b_cell = ''.join(cell__)

        num = select(Coordinates).where(Coordinates.cell_id == b_cell)
        num = db.execute(num).scalar_one_or_none()
        if num.value != "0":
            raise HTTPException(403, "the cell above is not free")
    
    if cell__[0] == 'B':
        cell__[0] = 'C'
        c_cell = ''.join(cell__)

        num = select(Coordinates).where(Coordinates.cell_id == c_cell)
        num = db.execute(num).scalar_one_or_none()
        if num.value != "0":
            raise HTTPException(403, "the cell above is not free")
        
    cell_ = list(cell_to.cell_id)
    if cell_[0] == 'B':
        cell_[0] = 'A'
        a_cell = ''.join(cell_)

        num = select(Coordinates).where(Coordinates.cell_id == a_cell)
        num = db.execute(num).scalar_one_or_none()
        if num.value == "0":
            raise HTTPException(403, "there is no support under the cell")
        if num.size != cell_from.size:
            raise HTTPException(403, "The container size does not match the one below it")
        
    if cell_[0] == 'C':
        cell_[0] = 'B'
        b_cell = ''.join(cell_)

        num = select(Coordinates).where(Coordinates.cell_id == b_cell)
        num = db.execute(num).scalar_one_or_none()
        if num.value == "0":
            raise HTTPException(403, "there is no support under the cell")
        if num.size != cell_from.size:
            raise HTTPException(403, "The container size does not match the one below it")
        
    rearrange_from = update(Coordinates).where(cast(Coordinates.value, String) == value).values(value = "0",
                                                                                                size = None,
                                                                                                company = 'empty',
                                                                                                cont_type = 'null',
                                                                                                path_num_to = None,
                                                                                                path_num_from = None,
                                                                                                sent_date = None)
    rearrange_to = update(Coordinates).where(Coordinates.cell_id == cell).values(value = value,
                                                                                 size = cell_from.size,
                                                                                 company = cell_from.company,
                                                                                 cont_type = cell_from.cont_type,
                                                                                 path_num_to = cell_from.path_num_to,
                                                                                 path_num_from = cell_from.path_num_from,
                                                                                 sent_date = cell_from.sent_date)
    price = calculation_movement_price(mov_type='rearrangement',
                                       size=cell_from.size,
                                       cell_1=cell_from.cell_id,
                                       cell_2=cell)
    
    movement = Movement_info(moove_type= "rearrangement",
                             value= value,
                             cell_from= cell_from.cell_id,
                             cell_to= cell,
                             movement_time= datetime.utcnow(),
                             company= cell_from.company,
                             price= price)
    db.add(movement)
    db.execute(rearrange_from)
    db.execute(rearrange_to)
    db.commit()
    migration()
    return {"status": "success",
            "container": value,
            "from": cell_from.cell_id,
            "to": cell_to.cell_id,
            "price": price}

@router.get("/layer", response_model=List[Layer])
def get_layer(layer: str,
              current_user=Depends(get_current_user),
              db: Session = Depends(get_db)):
    stmt = select(Coordinates).where(Coordinates.layer == layer)
    lay = db.execute(stmt).scalars().all()

    return lay

@router.get("/mooves", response_model=List[Mooves])
def mooves(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    stmt = select(Movement_info).order_by(desc(Movement_info.moove_id)).limit(10)
    res = db.execute(stmt).scalars().all()

    return res

@router.post("/recommend")
def recommend_cells(data: Recomend,
                    user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")

    EMPTY_CELL = "0"
    try:
        time_diff_data = data.sent_date - datetime.now(timezone.utc)
        delta_time = round(time_diff_data.total_seconds() / 3600, 2)
        # print(delta_time)
        free_cells = db.query(Coordinates).filter(
            Coordinates.value == EMPTY_CELL
        ).all()
        recommendations = []
        lower_delta_time = None

        for cell in free_cells:
            # print(cell.cell_id)
            if not check_stack_size(
                db,
                cell.cell_id,
                int(data.size)
            ):
                # print("not")
                continue

            list_cell = list(cell.cell_id)
            
            if list_cell[0] == 'B':

                list_cell[0] = 'A'
                lower_cell = ''.join(list_cell)
                # print(lower_cell)
                stmt = db.query(Coordinates).filter(Coordinates.cell_id == lower_cell)
                lower_cell = stmt.first()
                time_diff = lower_cell.sent_date.replace(tzinfo=None) - datetime.now().replace(tzinfo=None)
                lower_delta_time = round(time_diff.total_seconds() / 3600, 2)
            
            elif list_cell[0] == 'C':
                
                list_cell[0] = 'B'
                lower_cell = ''.join(list_cell)
                stmt = db.query(Coordinates).filter(Coordinates.cell_id == lower_cell)
                lower_cell = stmt.first()
                time_diff = lower_cell.sent_date.replace(tzinfo=None) - datetime.now().replace(tzinfo=None)
                lower_delta_time = round(time_diff.total_seconds() / 3600, 2)
            # print(lower_delta_time)
            score = calculation_score(
                delta_time,
                cell.cell_id,
                data.path_to,
                lower_delta_time
            )
            recommendations.append({
                "cell": cell.cell_id,
                "score": score
            })

        recommendations.sort(
            key=lambda x: x["score"],
            reverse=True
        )
        # print(recommendations)
        top_5 = recommendations[:5]
        if not top_5:
            return {"top 5": [], "объяснение": "Нет подходящих свободных ячеек."}
        best = top_5[0]
        best_cell = best['cell']
        best_score = best['score']
        explanation = ask_ai(f"""
            Ты объясняешь решение системы контейнерного терминала.
            информация о терминале:
                             3 слоя(A, B, C, где нижний слой A, а C верхний),
                             30 рядов и 3 пути возле них(1 путь возле 5 ряда, 2 путь возле 15 ряда, 3 путь возле 25 ряда),
                             3 колонны(X, Y, Z, где X и Z предназначены для контейнеров с быстрой/средней скоростью отправки),
                             
            Контейнер:
            Размер: {data.size}
            Дней до отправки: {delta_time}, если значение больше 7, контейнер будут стараться поставить в пределах 5 рядов от пути отправления
            Путь отправления: {data.path_to}
            Выбранный слой: {list(best_cell)[0]}

            Выбранная ячейка:
            {best_cell}

            Score:
            {best_score}

            Объясни кратко:
            1. Почему выбрана эта ячейка.
            2. Как влияет расстояние до пути.
            3. Как влияет слой.
            4. Как это уменьшает перестановки.

            Ответ не длиннее 3 предложений.
            """)
        return {"top 5": top_5, "объяснение": explanation}
    finally:
        db.close()
    
@router.post("/data_upload")
def uploading_to_company(data: UploadData, user: User = Depends(get_current_user)):
    
    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    status = upload_company_mov(data.company, data.start_data, data.end_data)   
    if status:
        return {"status": "success"} 
    else:
        return {"status": "not success"}