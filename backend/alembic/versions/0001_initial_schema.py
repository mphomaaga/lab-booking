"""Initial schema: users, labs, slots, bookings, lab_closures

Revision ID: 0001
Revises:
Create Date: 2026-11-20
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("student_number", sa.String(length=32), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column("is_admin", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("student_number", name="uq_users_student_number"),
    )

    op.create_table(
        "labs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("seats", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", name="uq_labs_name"),
        sa.CheckConstraint("seats > 0", name="ck_labs_seats_positive"),
    )

    op.create_table(
        "slots",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lab_id", sa.Integer(), nullable=False),
        sa.Column("start_time", sa.DateTime(), nullable=False),
        sa.Column("end_time", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"], name="fk_slots_lab_id"),
        sa.UniqueConstraint("lab_id", "start_time", name="uq_slots_lab_start"),
        sa.CheckConstraint("end_time > start_time", name="ck_slots_end_after_start"),
    )
    op.create_index("ix_slots_start_time", "slots", ["start_time"])

    op.create_table(
        "bookings",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("slot_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.Column("cancelled_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["slot_id"], ["slots.id"], name="fk_bookings_slot_id"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_bookings_user_id"),
    )
    op.create_index("ix_bookings_slot_id", "bookings", ["slot_id"])
    op.create_index("ix_bookings_user_id", "bookings", ["user_id"])
    # Partial unique index: one *active* booking per user and slot (rule 5.7).
    op.create_index(
        "uq_bookings_active_user_slot",
        "bookings",
        ["user_id", "slot_id"],
        unique=True,
        sqlite_where=sa.text("cancelled_at IS NULL"),
    )

    op.create_table(
        "lab_closures",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("lab_id", sa.Integer(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.current_timestamp(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["lab_id"], ["labs.id"], name="fk_lab_closures_lab_id"),
        sa.UniqueConstraint("lab_id", "date", name="uq_lab_closures_lab_date"),
    )


def downgrade() -> None:
    op.drop_table("lab_closures")
    op.drop_index("uq_bookings_active_user_slot", table_name="bookings")
    op.drop_index("ix_bookings_user_id", table_name="bookings")
    op.drop_index("ix_bookings_slot_id", table_name="bookings")
    op.drop_table("bookings")
    op.drop_index("ix_slots_start_time", table_name="slots")
    op.drop_table("slots")
    op.drop_table("labs")
    op.drop_table("users")
