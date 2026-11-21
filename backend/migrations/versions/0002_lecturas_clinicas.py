"""Agrega las lecturas clínicas independientes."""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "clinical_readings",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "analysis_id",
            sa.Integer(),
            sa.ForeignKey("analyses.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("reader_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("birads", sa.String(2), nullable=False),
        sa.Column("blinded", sa.Boolean(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("analysis_id", "reader_id", name="uq_reading_analysis_reader"),
    )
    op.create_index("ix_clinical_readings_reader_id", "clinical_readings", ["reader_id"])


def downgrade() -> None:
    op.drop_index("ix_clinical_readings_reader_id", table_name="clinical_readings")
    op.drop_table("clinical_readings")
