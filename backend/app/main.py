from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
from app.api import http_routes, ws_routes
from app.models.database import init_db


@asynccontextmanager
async def lifespan(_: FastAPI):
    """应用生命周期管理"""
    await init_db()
    print(f"✅ {settings.APP_NAME} started on http://{settings.HOST}:{settings.PORT}")
    try:
        yield
    finally:
        print(f"👋 {settings.APP_NAME} shutting down...")


app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Customer Service Robot Platform",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(http_routes.router, prefix="/api/v1", tags=["HTTP API"])
app.include_router(ws_routes.router, tags=["WebSocket"])


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "app": settings.APP_NAME}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
