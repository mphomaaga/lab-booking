from datetime import datetime

from sqlalchemy import Boolean, DateTime, String, UniqueConstraint, false, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._common import utcnow


class User(Base):
    __tablename__ = "users"
    __table_args__ = (UniqueConstraint("student_number", name="uq_users_student_number"),)

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    student_number: Mapped[str] = mapped_column(String(32), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=func.current_timestamp()
    )
