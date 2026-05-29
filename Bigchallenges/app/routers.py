from fastapi import APIRouter, Depends, HTTPException
from .database import get_db
from sqlalchemy.orm import Session
from .models import Coordinates, Mooving, Movement_info
from sqlalchemy import select, cast, String, update, Float, desc
from .schemas import FindCells, AddCont, Layer, Mooves
from typing import List
from datetime import datetime
from .mig_to_excel import migration

router = APIRouter(prefix="/container", tags=['container'])

@router.get("/find_cells", response_model=List[FindCells])
def find_cells(
    value: str,
    db: Session = Depends(get_db)
):
    list_ = select(Coordinates).where(cast(Coordinates.value, String) == str(value))

    values = db.execute(list_)
    res = values.scalars().all()
    return res

@router.post("/add")
def add_cont(
    data: AddCont,
    db: Session = Depends(get_db)
):
    stmt = select(Coordinates).where(Coordinates.cell_id == data.cell_id)
    cell_ = db.execute(stmt).scalar_one_or_none()

    if not cell_:
        raise HTTPException(404, detail="not found")
    
    if float(cell_.value) != 0.0:
        raise HTTPException(403, "cell is not empty")
   
    cell = list(cell_.cell_id)
    if cell[0] == 'B':
        cell[0] = 'A'
        a_cell = ''.join(cell)

        num = select(Coordinates).where(Coordinates.cell_id == a_cell)
        num = db.execute(num).scalar_one_or_none()
        if float(num.value) == 0.0:
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
        if float(num.value) == 0.0:
            raise HTTPException(403, "there is no support under the cell")
        # if num.cont_type != cell_.cont_type:
        #     raise HTTPException(403, "The container type does not match the one below it")
        if num.size != data.size:
            raise HTTPException(403, "The container size does not match the one below it")
            
    time = Mooving(value= cast(data.value, Float))
    db.add(time)
    
    movement = Movement_info(moove_type= "adding",
                             value= cast(data.value, Float),
                             path_num_from= data.path_num_from,
                             movement_time= datetime.utcnow())
    db.add(movement)

    update_stmt = (
        update(Coordinates)
        .where(Coordinates.cell_id == data.cell_id)
        .values(value=cast(data.value, Float),
                size=data.size,
                company=data.company,
                cont_type=data.cont_type) 
    )

    db.execute(update_stmt)
    db.commit()
    migration()
    return {"status": "success", "cell": data.cell_id, "container": data.value}

@router.get("/check")
def check_cont(
    # type: str,
    cont_num: str,
    db: Session = Depends(get_db)
):
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
              db: Session = Depends(get_db)):
    cell = select(Coordinates).where(Coordinates.cell_id == cell_id)
    cell = db.execute(cell).scalar_one_or_none()

    if not cell:
        raise HTTPException(404, "not found")
    
    return {"status": "success", "container num": cell.value, "size": cell.size, "path num": cell.path_num_to, "sent date": cell.sent_date}

@router.post("/loading")
def load_cont(value: str,
              path_num: int,
              db: Session = Depends(get_db)):
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
        if float(num.value) != 0.0:
            raise HTTPException(403, "the cell above is not free")
    
    if cell[0] == 'B':
        cell[0] = 'C'
        c_cell = ''.join(cell)

        num = select(Coordinates).where(Coordinates.cell_id == c_cell)
        num = db.execute(num).scalar_one_or_none()
        if float(num.value) != 0.0:
            raise HTTPException(403, "the cell above is not free")
        
    res = update(Coordinates).where(cast(Coordinates.value, String) == value).values(value = cast(0, Float))

    time = update(Mooving).where(cast(Mooving.value, String) == value).values(deleted_at = datetime.utcnow())

    movement = Movement_info(moove_type= "loading",
                             value= value,
                             path_num_to= path_num,
                             movement_time= datetime.utcnow())
    
    db.add(movement)
    db.execute(time)
    db.execute(res)
    db.commit()
    migration()
    return {"status": "success"}

@router.post("/rearrangement")
def rearrange_cont(value: str,
                   cell: str,
                   db: Session = Depends(get_db)):
    
    stmt = select(Coordinates).where(cast(Coordinates.value, String) == value)
    cell_from = db.execute(stmt).scalar_one_or_none()

    cell_to = select(Coordinates).where(Coordinates.cell_id == cell)
    cell_to = db.execute(cell_to).scalar_one_or_none()

    if not cell_from:
        raise HTTPException(404, "not found")
    if not cell_to:
        raise HTTPException(404, "not found")
    if float(cell_from.value) == 0.0:
        raise HTTPException(403, "cell is empty")
    if float(cell_to.value) != 0.0:
        raise HTTPException(403, "cell is not empty")
    
    cell__ = list(cell_from.cell_id)
    if cell__[0] == 'A':
        cell__[0] = 'B'
        b_cell = ''.join(cell__)

        num = select(Coordinates).where(Coordinates.cell_id == b_cell)
        num = db.execute(num).scalar_one_or_none()
        if float(num.value) != 0.0:
            raise HTTPException(403, "the cell above is not free")
    
    if cell__[0] == 'B':
        cell__[0] = 'C'
        c_cell = ''.join(cell__)

        num = select(Coordinates).where(Coordinates.cell_id == c_cell)
        num = db.execute(num).scalar_one_or_none()
        if float(num.value) != 0.0:
            raise HTTPException(403, "the cell above is not free")
        
    cell_ = list(cell_to.cell_id)
    if cell_[0] == 'B':
        cell_[0] = 'A'
        a_cell = ''.join(cell_)

        num = select(Coordinates).where(Coordinates.cell_id == a_cell)
        num = db.execute(num).scalar_one_or_none()
        if float(num.value) == 0.0:
            raise HTTPException(403, "there is no support under the cell")
        if num.size != cell_from.size:
            raise HTTPException(403, "The container size does not match the one below it")
        
    if cell_[0] == 'C':
        cell_[0] = 'B'
        b_cell = ''.join(cell_)

        num = select(Coordinates).where(Coordinates.cell_id == b_cell)
        num = db.execute(num).scalar_one_or_none()
        if float(num.value) == 0.0:
            raise HTTPException(403, "there is no support under the cell")
        if num.size != cell_from.size:
            raise HTTPException(403, "The container size does not match the one below it")
        
    rearrange_from = update(Coordinates).where(cast(Coordinates.value, String) == value).values(value = cast(0, Float),
                                                                                                size = 'null',
                                                                                                company = 'empty',
                                                                                                cont_type = 'null')
    rearrange_to = update(Coordinates).where(Coordinates.cell_id == cell).values(value = cast(value, Float),
                                                                                 size = cell_from.size,
                                                                                 company = cell_from.company,
                                                                                 cont_type = cell_from.cont_type)
    movement = Movement_info(moove_type= "rearrangement",
                             value= value,
                             cell_from= cell_from.cell_id,
                             cell_to= cell,
                             movement_time= datetime.utcnow())
    db.add(movement)
    db.execute(rearrange_from)
    db.execute(rearrange_to)
    db.commit()
    migration()
    return {"status": "success",
            "container": value,
            "from": cell_from.cell_id,
            "to": cell_to.cell_id}

@router.get("/layer", response_model=List[Layer])
def get_layer(layer: str,
          db: Session = Depends(get_db)):
    stmt = select(Coordinates).where(Coordinates.layer == layer)
    lay = db.execute(stmt).scalars().all()

    return lay

@router.get("/mooves", response_model=List[Mooves])
def mooves(db: Session = Depends(get_db)):
    stmt = select(Movement_info).order_by(desc(Movement_info.moove_id)).limit(10)
    res = db.execute(stmt).scalars().all()

    return res