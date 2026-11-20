from datetime import datetime

from sqlalchemy import DateTime, ForeignKeyConstraint, Index, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models._common import utcnow


class Booking(Base):
    """A booking is active while ``cancelled_at`` is NULL (no status column)."""

    __tablename__ = "bookings"
    __table_args__ = (
        ForeignKeyConstraint(["slot_id"], ["slots.id"], name="fk_bookings_slot_id"),
        ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_bookings_user_id"),
        Index(
            "uq_bookings_active_user_slot",
            "user_id",
            "slot_id",
            unique=True,
            sqlite_where=text("cancelled_at IS NULL"),
        ),
        Index("ix_bookings_slot_id", "slot_id"),
        Index("ix_bookings_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    slot_id: Mapped[int] = mapped_column(nullable=False)
    user_id: Mapped[int] = mapped_column(nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=utcnow, server_default=func.current_timestamp()
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, default=None)
