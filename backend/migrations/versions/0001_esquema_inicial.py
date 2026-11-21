"""Esquema inicial de EcoAudit.

Es el esquema completo que hasta ahora creaba ``Base.metadata.create_all``, escrito a mano (no
se generó con autogenerate). No importa ``app.models``: una migración es una foto fija y no debe
cambiar cuando cambien los modelos. Los cambios posteriores van en migraciones nuevas.

Revisión: 0001
Anterior: (ninguna)
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def _fecha(nombre: str, *, nullable: bool = False) -> sa.Column:
    """Columna de fecha con zona (el modelo la guarda siempre en UTC, ver ``UtcDateTime``)."""
    return sa.Column(nombre, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        sa.Column(
            "role",
            sa.Enum("medico", "investigador", "admin", name="role", native_enum=False, length=20),
            nullable=False,
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _fecha("created_at"),
        # Los tokens emitidos antes de este instante dejan de valer.
        _fecha("password_changed_at", nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    op.create_table(
        "model_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("bundle_sha256", sa.String(length=64), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("card", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        _fecha("created_at"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("bundle_sha256"),
    )

    op.create_table(
        "cases",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("patient_ref", sa.String(length=64), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("created_by_id", sa.Integer(), nullable=False),
        _fecha("created_at"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cases_created_by_id", "cases", ["created_by_id"])

    op.create_table(
        "images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("case_id", sa.Integer(), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("pixel_sha256", sa.String(length=64), nullable=False),
        sa.Column("dhash", sa.String(length=16), nullable=False),
        sa.Column("width", sa.Integer(), nullable=False),
        sa.Column("height", sa.Integer(), nullable=False),
        sa.Column("source_format", sa.String(length=16), nullable=False),
        sa.Column("qc_flags", sa.JSON(), nullable=False),
        sa.Column("duplicate_of_id", sa.Integer(), nullable=True),
        _fecha("created_at"),
        sa.ForeignKeyConstraint(["case_id"], ["cases.id"]),
        sa.ForeignKeyConstraint(["duplicate_of_id"], ["images.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_images_case_id", "images", ["case_id"])
    op.create_index("ix_images_pixel_sha256", "images", ["pixel_sha256"])

    op.create_table(
        "analyses",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("image_id", sa.Integer(), nullable=False),
        sa.Column("requested_by_id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "running",
                "done",
                "failed",
                name="analysisstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("roi", sa.JSON(), nullable=True),
        # Veces que un worker lo reclamó; si el worker muere se reencola hasta agotar los intentos.
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("probability_raw", sa.Float(), nullable=True),
        sa.Column("probability", sa.Float(), nullable=True),
        sa.Column("member_spread", sa.Float(), nullable=True),
        sa.Column("decision", sa.String(length=32), nullable=True),
        sa.Column("shift_score", sa.Float(), nullable=True),
        sa.Column("shift_flag", sa.Boolean(), nullable=True),
        sa.Column("warnings", sa.JSON(), nullable=False),
        sa.Column("cam_key", sa.String(length=255), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        _fecha("created_at"),
        _fecha("started_at", nullable=True),
        _fecha("finished_at", nullable=True),
        sa.ForeignKeyConstraint(["image_id"], ["images.id"]),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.ForeignKeyConstraint(["requested_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_analyses_image_id", "analyses", ["image_id"])
    op.create_index("ix_analyses_status", "analyses", ["status"])

    op.create_table(
        "cohorts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column(
            "source",
            sa.Enum("analyses", "batch", name="cohortsource", native_enum=False, length=16),
            nullable=False,
        ),
        sa.Column(
            "status",
            sa.Enum(
                "processing",
                "done",
                "failed",
                name="cohortstatus",
                native_enum=False,
                length=16,
            ),
            nullable=False,
        ),
        sa.Column("owner_id", sa.Integer(), nullable=False),
        sa.Column("model_version_id", sa.Integer(), nullable=False),
        sa.Column("csv_hash", sa.String(length=64), nullable=False),
        sa.Column("results", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        _fecha("created_at"),
        _fecha("finished_at", nullable=True),
        sa.ForeignKeyConstraint(["model_version_id"], ["model_versions.id"]),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cohorts_owner_id", "cohorts", ["owner_id"])
    op.create_index("ix_cohorts_status", "cohorts", ["status"])

    op.create_table(
        "cohort_items",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cohort_id", sa.Integer(), nullable=False),
        sa.Column("analysis_id", sa.Integer(), nullable=False),
        sa.Column("patient_ref", sa.String(length=64), nullable=False),
        sa.Column("label", sa.Integer(), nullable=False),  # 0 benigno, 1 maligno
        sa.ForeignKeyConstraint(["analysis_id"], ["analyses.id"]),
        sa.ForeignKeyConstraint(["cohort_id"], ["cohorts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_cohort_items_analysis_id", "cohort_items", ["analysis_id"])
    op.create_index("ix_cohort_items_cohort_id", "cohort_items", ["cohort_id"])

    op.create_table(
        "audit_log",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("entity", sa.String(length=32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=True),
        sa.Column("detail", sa.JSON(), nullable=False),
        _fecha("created_at"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_audit_log_action", "audit_log", ["action"])


def downgrade() -> None:
    # Orden inverso al de creación, por las claves foráneas.
    for tabla in (
        "audit_log",
        "cohort_items",
        "cohorts",
        "analyses",
        "images",
        "cases",
        "model_versions",
        "users",
    ):
        op.drop_table(tabla)  # los índices caen junto con su tabla
