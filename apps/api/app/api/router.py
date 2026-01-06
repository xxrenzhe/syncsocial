from fastapi import APIRouter

from app.api.routes import admin_users, auth, me

api_router = APIRouter()
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(me.router, tags=["me"])
api_router.include_router(admin_users.router, prefix="/admin", tags=["admin"])

