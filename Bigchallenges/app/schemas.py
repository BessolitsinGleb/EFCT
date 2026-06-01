from pydantic import BaseModel
from datetime import datetime

class FindCells(BaseModel):
    cell_id: str
    cont_type: str
    size: int
    sent_date: datetime | None
    path_num_to: int | None

class AddCont(BaseModel):
    cell_id: str
    value: str
    company: str
    size: int
    cont_type: str
    sent_date: datetime | None
    path_num_from: int | None
    path_num_to: int | None

class Layer(BaseModel):
    cell_id: str
    value: str

class Mooves(BaseModel):
    value: str
    moove_type: str
    path_num_from: int | None
    path_num_to: int | None
    cell_from: str | None
    cell_to: str | None
    movement_time: datetime

class Recomend(BaseModel):
    size: int
    path_to: int
    sent_date: datetime

"""я люблю тебя"""