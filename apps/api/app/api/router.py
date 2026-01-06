from fastapi import APIRouter

from app.api.routes import admin_users, auth, login_sessions, me, social_accounts

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, tags=["me"])
api_router.include_router(social_accounts.router, prefix="/social-accounts", tags=["social_accounts"])
api_router.include_router(login_sessions.router, prefix="/login-sessions", tags=["login_sessions"])
api_router.include_router(admin_users.router, prefix="/admin", tags=["admin"])
