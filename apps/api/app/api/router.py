from fastapi import APIRouter

from app.api.routes import (
    admin_subscription,
    admin_users,
    artifacts,
    auth,
    login_sessions,
    me,
    runs,
    schedules,
    social_accounts,
    strategies,
)

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, tags=["me"])
api_router.include_router(social_accounts.router, prefix="/social-accounts", tags=["social_accounts"])
api_router.include_router(login_sessions.router, prefix="/login-sessions", tags=["login_sessions"])
api_router.include_router(strategies.router, prefix="/strategies", tags=["strategies"])
api_router.include_router(schedules.router, prefix="/schedules", tags=["schedules"])
api_router.include_router(runs.router, prefix="/runs", tags=["runs"])
api_router.include_router(artifacts.router, tags=["artifacts"])
api_router.include_router(admin_users.router, prefix="/admin", tags=["admin"])
api_router.include_router(admin_subscription.router, prefix="/admin", tags=["admin"])
