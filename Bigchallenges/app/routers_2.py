from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import or_
from .models import TaskAction, Task, TaskStatus, User, Role, Crane
from .schemas import TaskOut, TaskCreate, ActionStatusUpdate, ActionStatus, TaskActionOut, CraneCreate
from datetime import datetime
from .settings import get_current_user, get_db, notify_task_assigned, manager

router = APIRouter(prefix="/cran", tags=['cran'])


def require_role(user: User, role: Role, msg: str):
    if user.role != role:
        raise HTTPException(403, detail=msg)


def crane_out(db: Session, crane: Crane, online: set) -> dict:
    op = db.get(User, crane.operator_id) if crane.operator_id else None
    return {"crane_id": crane.crane_id, "name": crane.name, "operator_id": crane.operator_id,
            "operator_name": op.user_name if op else None,
            "online": crane.operator_id in online if crane.operator_id else False}


# ---------- краны ----------

@router.get("/cranes")
def list_cranes(db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Краны: кто на каком кране работает и онлайн ли он."""
    online = set(manager.get_online_users())
    return [crane_out(db, c, online) for c in db.query(Crane).order_by(Crane.crane_id).all()]


@router.post("/cranes")
def create_crane(payload: CraneCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_role(current_user, Role.transceiver, "you are not the transceiver")
    name = payload.name.strip()
    if not name:
        raise HTTPException(422, "Укажите название крана")
    if db.query(Crane).filter(Crane.name == name).first():
        raise HTTPException(409, "Кран с таким названием уже есть")
    crane = Crane(name=name)
    db.add(crane)
    db.commit()
    db.refresh(crane)
    return crane_out(db, crane, set(manager.get_online_users()))


@router.post("/cranes/{crane_id}/take")
def take_crane(crane_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    """Крановщик занимает кран в начале смены (освобождая предыдущий)."""
    require_role(current_user, Role.crane_operator, "you are not the crane operator")
    crane = db.get(Crane, crane_id)
    if crane is None:
        raise HTTPException(404, "Кран не найден")
    online = set(manager.get_online_users())
    if crane.operator_id not in (None, current_user.user_id) and crane.operator_id in online:
        raise HTTPException(409, "Кран занят другим крановщиком")
    for other in db.query(Crane).filter(Crane.operator_id == current_user.user_id).all():
        other.operator_id = None
    crane.operator_id = current_user.user_id
    db.commit()
    return crane_out(db, crane, online)


@router.post("/cranes/{crane_id}/release")
def release_crane(crane_id: int, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_role(current_user, Role.crane_operator, "you are not the crane operator")
    crane = db.get(Crane, crane_id)
    if crane is None:
        raise HTTPException(404, "Кран не найден")
    if crane.operator_id == current_user.user_id:
        crane.operator_id = None
        db.commit()
    return crane_out(db, crane, set(manager.get_online_users()))


# ---------- наряды ----------

def resolve_crane_operator(db: Session, crane_id: int) -> int:
    crane = db.get(Crane, crane_id)
    if crane is None:
        raise HTTPException(404, "Кран не найден")
    if crane.operator_id is None:
        raise HTTPException(409, f"На кране «{crane.name}» сейчас нет крановщика")
    return crane.operator_id


@router.post("/tasks", response_model=TaskOut)
def create_task(payload: TaskCreate, db: Session = Depends(get_db), current_user=Depends(get_current_user)):
    require_role(current_user, Role.transceiver, "you are not the transceiver")
    if payload.crane_id is not None:
        assigned = resolve_crane_operator(db, payload.crane_id)
    elif payload.assigned_to is not None:
        assigned = payload.assigned_to
    else:
        raise HTTPException(422, "Укажите кран или крановщика")

    task = Task(created_by=current_user.user_id, assigned_to=assigned, crane_id=payload.crane_id)
    for i, action in enumerate(payload.actions, start=1):
        task.actions.append(TaskAction(order_index=i, **action.model_dump()))
    db.add(task)
    db.commit()
    db.refresh(task)
    return task


@router.post("/tasks/{task_id}/send", response_model=TaskOut)
async def send_task(task_id: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    require_role(user, Role.transceiver, "you are not the transceiver")
    task = db.get(Task, task_id)
    if task is None:
        raise HTTPException(404, "Задание не найдено")
    if task.status != TaskStatus.draft:
        raise HTTPException(400, "Задание уже отправлено")
    if task.crane_id is not None:   # наряд на кран получает тот, кто на нём сейчас
        task.assigned_to = resolve_crane_operator(db, task.crane_id)

    task.status = TaskStatus.sent
    db.commit()
    db.refresh(task)
    await notify_task_assigned(task)
    return task


def my_crane_ids(db: Session, user_id: int) -> list:
    return [c.crane_id for c in db.query(Crane).filter(Crane.operator_id == user_id).all()]


@router.get("/tasks", response_model=list[TaskOut])
def list_my_tasks(assigned_to_me: bool = False, db: Session = Depends(get_db),
                  current_user=Depends(get_current_user)):
    query = db.query(Task).filter(Task.status != TaskStatus.completed)
    if assigned_to_me:
        cranes = my_crane_ids(db, current_user.user_id)
        cond = Task.assigned_to == current_user.user_id
        if cranes:
            cond = or_(cond, Task.crane_id.in_(cranes))
        query = query.filter(cond, Task.status != TaskStatus.draft)  # черновики крановщику не показываем
    else:
        query = query.filter(Task.created_by == current_user.user_id)
    return query.order_by(Task.id).all()


@router.patch("/tasks/{task_id}/actions/{action_id}", response_model=TaskActionOut)
def update_action_status(task_id: int, action_id: int, payload: ActionStatusUpdate,
                         current_user=Depends(get_current_user), db: Session = Depends(get_db)):
    action = db.get(TaskAction, action_id)
    if action is None or action.task_id != task_id:
        raise HTTPException(404, "Действие не найдено")
    task = action.task
    allowed = task.assigned_to == current_user.user_id or (
        task.crane_id is not None and task.crane_id in my_crane_ids(db, current_user.user_id))
    if not allowed:
        raise HTTPException(403, "Это задание назначено другому крановщику")

    if payload.status == ActionStatus.in_progress and action.started_at is None:
        action.started_at = datetime.utcnow()
    if payload.status == ActionStatus.done:
        action.completed_at = datetime.utcnow()
    action.status = payload.status
    if task.status == TaskStatus.sent:
        task.status = TaskStatus.in_progress
    if all(a.status == ActionStatus.done for a in task.actions):
        task.status = TaskStatus.completed
    db.commit()
    db.refresh(action)
    return action


@router.get("/crane-operators/online")
def get_online_operators(user: User = Depends(get_current_user)):
    require_role(user, Role.transceiver, "you are not the transceiver")
    return {"id": manager.get_online_users()}
