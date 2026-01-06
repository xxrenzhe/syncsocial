from __future__ import annotations

from sqlalchemy import select

from app.core.config import settings
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User
from app.models.workspace import Workspace


def _require(value: str | None, key: str) -> str:
    if value is None or not value.strip():
        raise SystemExit(f"Missing required env var: {key}")
    return value.strip()


def seed() -> None:
    admin_email = _require(settings.seed_admin_email, "SEED_ADMIN_EMAIL").lower()
    admin_password = _require(settings.seed_admin_password, "SEED_ADMIN_PASSWORD")
    workspace_name = settings.seed_workspace_name.strip() or "Default Workspace"

    with SessionLocal() as db:
        workspace = db.scalar(select(Workspace).limit(1))
        if workspace is None:
            workspace = Workspace(name=workspace_name, status="active")
            db.add(workspace)
            db.flush()

        admin = db.scalar(select(User).where(User.email == admin_email))
        if admin is None:
            admin = User(
                workspace_id=workspace.id,
                email=admin_email,
                display_name="Admin",
                password_hash=hash_password(admin_password),
                role="admin",
                status="active",
                must_change_password=False,
            )
            db.add(admin)
        else:
            admin.workspace_id = workspace.id
            admin.role = "admin"
            admin.status = "active"
            admin.password_hash = hash_password(admin_password)
            admin.must_change_password = False
            db.add(admin)

        db.commit()
        print(f"Seeded admin user: {admin.email}")


if __name__ == "__main__":
    seed()

