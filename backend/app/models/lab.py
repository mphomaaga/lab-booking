from sqlalchemy import Boolean, CheckConstraint, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Lab(Base):
    __tablename__ = "labs"
    __table_args__ = (
        UniqueConstraint("name", name="uq_labs_name"),
        CheckConstraint("seats > 0", name="ck_labs_seats_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    seats: Mapped[int] = mapped_column(nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
