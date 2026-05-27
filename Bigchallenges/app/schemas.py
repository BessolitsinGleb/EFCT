from pydantic import BaseModel
from datetime import datetime

class FindCells(BaseModel):
    cell_id: str
    cont_type: str
    size: str
    sent_date: datetime | None
    path_num_to: int | None
    
class AddCont(BaseModel):
    cell_id: str
    value: str
    company: str
    size: str
    cont_type: str
    sent_date: datetime | None
    path_num_from: int | None
    path_num_to: int | None

class Layer(BaseModel):
    cell_id: str
    value: float

class Mooves(BaseModel):
    value: float
    added_at: datetime
    deleted_at: datetime