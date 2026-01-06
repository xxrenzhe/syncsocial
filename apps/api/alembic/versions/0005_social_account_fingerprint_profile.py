"""social account fingerprint profile

Revision ID: 0005_social_account_fingerprint_profile
Revises: 0004_subscriptions_and_usage
Create Date: 2026-01-06

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0005_social_account_fingerprint_profile"
down_revision = "0004_subscriptions_and_usage"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "social_accounts",
        sa.Column("fingerprint_profile", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("social_accounts", "fingerprint_profile")

