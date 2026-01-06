from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Schedule(Base):
    __tablename__ = "schedules"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(), primary_key=True, default=uuid.uuid4)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("workspaces.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    strategy_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(),
        ForeignKey("strategies.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    account_selector: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    frequency: Mapped[str] = mapped_column(String(32), nullable=False, default="manual")
    schedule_spec: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    random_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    max_parallel: Mapped[int] = mapped_column(Integer, nullable=False, default=1)

    next_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_run_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )

