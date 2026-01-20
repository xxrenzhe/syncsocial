"""prompt stacks

Revision ID: 0008_prompt_stacks
Revises: 0007_account_run_retries
Create Date: 2026-01-20

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0008_prompt_stacks"
down_revision = "0007_account_run_retries"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "prompt_stacks",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("workspace_id", sa.Uuid(), nullable=False),
        sa.Column("key", sa.String(length=64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("payload", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "key"),
    )
    op.create_index(op.f("ix_prompt_stacks_workspace_id"), "prompt_stacks", ["workspace_id"], unique=False)
    op.create_index(op.f("ix_prompt_stacks_key"), "prompt_stacks", ["key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_prompt_stacks_key"), table_name="prompt_stacks")
    op.drop_index(op.f("ix_prompt_stacks_workspace_id"), table_name="prompt_stacks")
    op.drop_table("prompt_stacks")

