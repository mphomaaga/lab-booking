import datetime as dt

from sqlalchemy import Date, DateTime, ForeignKeyConstraint, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._common import utcnow


class LabClosure(Base):
    __tablename__ = "lab_closures"
    __table_args__ = (
        ForeignKeyConstraint(["lab_id"], ["labs.id"], name="fk_lab_closures_lab_id"),
        UniqueConstraint("lab_id", "date", name="uq_lab_closures_lab_date"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    lab_id: Mapped[int] = mapped_column(nullable=False)
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=func.current_timestamp()
    )
