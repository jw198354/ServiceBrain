from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api import http_routes, ws_routes
from app.models.database import init_db

app = FastAPI(
    title=settings.APP_NAME,
    description="Intelligent Customer Service Robot Platform",
    version="0.1.0",
)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Demo 阶段允许所有来源
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(http_routes.router, prefix="/api/v1", tags=["HTTP API"])
app.include_router(ws_routes.router, tags=["WebSocket"])


@app.on_event("startup")
async def startup_event():
    """应用启动时初始化数据库"""
    await init_db()
    print(f"✅ {settings.APP_NAME} started on http://{settings.HOST}:{settings.PORT}")


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭时清理资源"""
    print(f"👋 {settings.APP_NAME} shutting down...")


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
