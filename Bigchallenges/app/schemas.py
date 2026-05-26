from pydantic import BaseModel
from datetime import datetime

class FindCells(BaseModel):
    cell_id: str
    cont_type: str
    size: str
    
class AddCont(BaseModel):
    cell_id: str
    value: str
    company: str
    size: str
    cont_type: str

class Layer(BaseModel):
    cell_id: str
    value: float

class Mooves(BaseModel):
    value: float
    added_at: datetime
    deleted_at: datetime