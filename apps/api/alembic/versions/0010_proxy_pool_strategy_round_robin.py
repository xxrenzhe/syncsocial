"""normalize proxy pool strategy names

Revision ID: 0010_proxy_pool_strategy_round_robin
Revises: 0009_workspace_llm_configs
Create Date: 2026-01-20

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_proxy_pool_strategy_round_robin"
down_revision = "0009_workspace_llm_configs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE proxy_pools SET strategy='round_robin' WHERE strategy='random'"))


def downgrade() -> None:
    op.execute(sa.text("UPDATE proxy_pools SET strategy='random' WHERE strategy='round_robin'"))

