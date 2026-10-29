"""Add new columns from Phase 2 missing features.

Adds:
  - pickers.is_blocked          (MF#17)
  - pickers.risk_flag           (MF#18)
  - pickers.total_submissions   (MF#18)
  - pickers.total_rejections    (MF#18)
  - collections.unit_normalised (MF#7)
  - completion_records.invoice_number (MF#9)

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-20 00:01:00
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # pickers — MF#17 + MF#18
    with op.batch_alter_table("pickers") as batch_op:
        batch_op.add_column(sa.Column("is_blocked",        sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("risk_flag",         sa.String(),  nullable=True))
        batch_op.add_column(sa.Column("total_submissions", sa.Integer(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("total_rejections",  sa.Integer(), nullable=False, server_default="0"))

    # collections — MF#7
    with op.batch_alter_table("collections") as batch_op:
        batch_op.add_column(sa.Column("unit_normalised", sa.Boolean(), nullable=False, server_default="0"))

    # completion_records — MF#9
    with op.batch_alter_table("completion_records") as batch_op:
        batch_op.add_column(sa.Column("invoice_number", sa.String(), nullable=True, unique=True))


def downgrade() -> None:
    with op.batch_alter_table("completion_records") as batch_op:
        batch_op.drop_column("invoice_number")

    with op.batch_alter_table("collections") as batch_op:
        batch_op.drop_column("unit_normalised")

    with op.batch_alter_table("pickers") as batch_op:
        batch_op.drop_column("total_rejections")
        batch_op.drop_column("total_submissions")
        batch_op.drop_column("risk_flag")
        batch_op.drop_column("is_blocked")
