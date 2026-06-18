from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy import ForeignKey, Enum as SAEnum, String
from .database import Base
from datetime import datetime
from enum import Enum

class Coordinates(Base):

    __tablename__ = "container_storage"

    cell_id: Mapped[str] = mapped_column(primary_key=True, unique=True)
    layer: Mapped[str] = mapped_column(nullable=False)
    row_num: Mapped[int] = mapped_column(nullable=False) # 1 <= x <= 30
    coord_type: Mapped[str] = mapped_column(nullable=False)
    value: Mapped[str] = mapped_column(default='0')
    company: Mapped[str] = mapped_column(nullable=False)
    size: Mapped[int | None] = mapped_column(nullable=True)
    cont_type: Mapped[str] = mapped_column(nullable=False)
    sent_date: Mapped[datetime] = mapped_column(nullable=True)
    path_num_from: Mapped[int] = mapped_column(nullable=True)
    path_num_to: Mapped[int] = mapped_column(nullable=True)

class Mooving(Base):
    __tablename__ = "mooving"
    id: Mapped[int] = mapped_column(primary_key=True)
    value: Mapped[str] = mapped_column(nullable=False)
    added_at: Mapped[datetime] = mapped_column(default= datetime.utcnow)
    deleted_at: Mapped[datetime] = mapped_column(default= datetime.utcnow)


class Moove_types(Enum):
    adding = "adding"
    rearrangement = "rearrangement"
    loading = "loading"

class Movement_info(Base):

    __tablename__ = "movement_information"

    moove_id: Mapped[int] = mapped_column(primary_key=True, unique=True)
    moove_type: Mapped[Moove_types] = mapped_column(nullable=False)
    value: Mapped[str] = mapped_column(nullable=False)  # cont_num
    path_num_from: Mapped[int] = mapped_column(nullable=True)   # path № 1, 2, 3
    path_num_to: Mapped[int] = mapped_column(nullable=True)
    cell_from: Mapped[str] = mapped_column(nullable=True)
    cell_to: Mapped[str] = mapped_column(nullable=True)
    movement_time: Mapped[datetime] = mapped_column(nullable=False)
    company: Mapped[str] = mapped_column(nullable=False)
    price: Mapped[int] = mapped_column(default=0)

class Role(Enum):
    crane_operator = "crane_operator"
    transceiver = "transceiver"

class User(Base):

    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(primary_key=True)
    user_name: Mapped[str] = mapped_column(unique=False)
    role: Mapped[Role] = mapped_column(nullable=False)
    password_hash: Mapped[str] = mapped_column()

class ActionType(str, Enum):
    ADD = "ADD"
    LOAD = "LOAD"
    REAR = "REAR"

class ActionStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    done = "done"
    failed = "failed"

class TaskStatus(str, Enum):
    draft = "draft"
    sent = "sent"
    in_progress = "in_progress"
    completed = "completed"

class Task(Base):

    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.user_id"))
    assigned_to: Mapped[int | None] = mapped_column(ForeignKey("users.user_id"))
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), default=TaskStatus.draft)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow())

    actions: Mapped[list["TaskAction"]] = relationship(
        back_populates="task", order_by="TaskAction.order_index", cascade="all, delete-orphan"
    )

class TaskAction(Base):

    __tablename__ = "task_actions"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    order_index: Mapped[int]
    action_type: Mapped[ActionType] = mapped_column(SAEnum(ActionType))
    cont_num: Mapped[str] = mapped_column(String(20))
    from_loc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    to_loc: Mapped[str | None] = mapped_column(String(50), nullable=True)
    status: Mapped[ActionStatus] = mapped_column(SAEnum(ActionStatus), default=ActionStatus.pending)
    started_at: Mapped[datetime | None] = mapped_column(nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    task: Mapped["Task"] = relationship(back_populates="actions")