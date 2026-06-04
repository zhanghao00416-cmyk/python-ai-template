"""002_task_callback_url

Revision ID: 002
Revises: 001
Create Date: 2026-06-04

Add callback_url column to tasks table.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[Sequence[str], None] = None
depends_on: Union[Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "tasks",
        sa.Column("callback_url", sa.String(2048), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("tasks", "callback_url")