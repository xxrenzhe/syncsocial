from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    action: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(), nullable=True)
    metadata_: Mapped[dict] = mapped_column("metadata", JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
