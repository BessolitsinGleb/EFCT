from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from .models import TaskAction, Task, TaskStatus, User, Role
from .schemas import TaskOut, TaskCreate, ActionStatusUpdate, ActionStatus, TaskActionOut
from datetime import datetime
from .settings import get_current_user, get_db, notify_task_assigned, manager

router = APIRouter(prefix="/cran", tags=['cran'])

@router.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):

    if current_user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    task = Task(created_by=current_user.user_id, assigned_to=payload.assigned_to)
    for i, action in enumerate(payload.actions, start=1):
        task.actions.append(TaskAction(order_index=i, **action.model_dump()))
    db.add(task)
    db.commit()
    db.refresh(task)
    return task

@router.post("/tasks/{task_id}/send", response_model=TaskOut)
async def send_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Задание не найдено")
    if task.status != TaskStatus.draft:
        raise HTTPException(400, "Задание уже отправлено")

    task.status = TaskStatus.sent
    db.commit()
    db.refresh(task)

    await notify_task_assigned(task)
    return task


@router.get("/tasks", response_model=list[TaskOut])
def list_my_tasks(
    assigned_to_me: bool = False,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user),
):
    query = db.query(Task)
    if assigned_to_me:
        query = query.filter(Task.assigned_to == current_user.user_id,
                             Task.status != TaskStatus.completed)#.order_by(Task.id.desc()).limit(5)
    else:
        query = query.filter(Task.created_by == current_user.user_id,
                             Task.status != TaskStatus.completed)#.order_by(Task.id.desc()).limit(5)
    return query.all()


@router.patch("/tasks/{task_id}/actions/{action_id}", response_model=TaskActionOut)
def update_action_status(
    task_id: int,
    action_id: int,
    payload: ActionStatusUpdate,
    current_user=Depends(get_current_user),
    db: Session = Depends(get_db),
):

    action = db.get(TaskAction, action_id)
    if action is None or action.task_id != task_id:
        raise HTTPException(404, "Действие не найдено")

    if payload.status == ActionStatus.in_progress and action.started_at is None:
        action.started_at = datetime.utcnow()
    if payload.status == ActionStatus.done:
        action.completed_at = datetime.utcnow()

    action.status = payload.status
    db.commit()

    task = action.task
    if task.status == TaskStatus.sent:
        task.status = TaskStatus.in_progress
        db.commit()

    all_done = all(a.status == ActionStatus.done for a in task.actions)
    if all_done:
        task.status = TaskStatus.completed
        db.commit()

    db.refresh(action)
    return action

@router.get("/crane-operators/online")
def get_online_operators(user: User = Depends(get_current_user)):

    if user.role != Role.transceiver:
        raise HTTPException(403, detail="you are not the transceiver")
    
    online_ids = manager.get_online_users()
    return {"id": online_ids} #, "count": len(online_ids)}