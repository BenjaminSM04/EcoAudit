"""Agrega las asignaciones de lectores a casos."""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "case_readers",
        sa.Column(
            "case_id", sa.Integer(), sa.ForeignKey("cases.id", ondelete="CASCADE"), primary_key=True
        ),
        sa.Column("reader_id", sa.Integer(), sa.ForeignKey("users.id"), primary_key=True),
        sa.Column("assigned_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_case_readers_reader_id", "case_readers", ["reader_id"])


def downgrade() -> None:
    op.drop_index("ix_case_readers_reader_id", table_name="case_readers")
    op.drop_table("case_readers")
