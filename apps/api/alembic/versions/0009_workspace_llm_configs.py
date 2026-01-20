"""workspace llm configs

Revision ID: 0009_workspace_llm_configs
Revises: 0008_prompt_stacks
Create Date: 2026-01-20

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0009_workspace_llm_configs"
down_revision = "0008_prompt_stacks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "workspace_llm_configs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False, server_default="openai"),
        sa.Column("api_key_encrypted", sa.LargeBinary(), nullable=False),
        sa.Column("base_url", sa.String(length=200), nullable=True),
        sa.Column("model", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id"),
    )
    op.create_index(op.f("ix_workspace_llm_configs_workspace_id"), "workspace_llm_configs", ["workspace_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workspace_llm_configs_workspace_id"), table_name="workspace_llm_configs")
    op.drop_table("workspace_llm_configs")

