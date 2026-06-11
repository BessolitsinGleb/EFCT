from sqlalchemy.orm import Mapped, mapped_column
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
