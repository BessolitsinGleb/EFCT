from pydantic import BaseModel
from datetime import datetime
from .models import ActionStatus, TaskStatus, ActionType

class FindCells(BaseModel):
    cell_id: str
    cont_type: str
    size: int | None
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

class UploadData(BaseModel):
    company: str
    start_data: datetime
    end_data: datetime

class UserReg(BaseModel):
    user_name: str
    role: str
    password: str

class Login(BaseModel):
    user_name: str
    password: str 

class TokenResp(BaseModel):
    access_token: str
    token_type: str = "bearer"

class UserResponse(BaseModel):
    user_name: str
    role: str

class TaskActionCreate(BaseModel):
    action_type: ActionType
    cont_num: str
    from_loc: str | None = None
    to_loc: str | None = None

class TaskCreate(BaseModel):
    assigned_to: int
    actions: list[TaskActionCreate]

class TaskActionOut(BaseModel):
    id: int
    order_index: int
    action_type: ActionType
    cont_num: str
    from_loc: str | None
    to_loc: str | None
    status: ActionStatus
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True

class TaskOut(BaseModel):
    id: int
    status: TaskStatus
    created_by: int
    assigned_to: int | None
    actions: list[TaskActionOut]

    class Config:
        from_attributes = True

class ActionStatusUpdate(BaseModel):
    status: ActionStatus