from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKeyConstraint, Index, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Slot(Base):
    __tablename__ = "slots"
    __table_args__ = (
        ForeignKeyConstraint(["lab_id"], ["labs.id"], name="fk_slots_lab_id"),
        UniqueConstraint("lab_id", "start_time", name="uq_slots_lab_start"),
        CheckConstraint("end_time > start_time", name="ck_slots_end_after_start"),
        Index("ix_slots_start_time", "start_time"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lab_id: Mapped[int] = mapped_column(nullable=False)
    start_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    end_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)
