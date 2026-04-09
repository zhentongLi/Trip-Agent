"""FastAPI主应用"""

import sys
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from .rate_limit import limiter
from loguru import logger
from ..config import get_settings, validate_config, print_config
from .routes import trip, poi, map as map_routes, share, auth, user, guide
from ..models.db_models import create_db_tables
from ..errors import register_error_handlers

# ========== loguru 全局配置 ==========
# 移除默认 handler，重新配置格式
logger.remove()
logger.add(
    sys.stdout,
    format="<green>{time:HH:mm:ss}</green> | <level>{level: <7}</level> | {message}",
    level="INFO",
    colorize=True
)
logger.add(
    "logs/app_{time:YYYY-MM-DD}.log",
    format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
    rotation="1 day",
    retention="7 days",
    level="DEBUG",
    encoding="utf-8",
    enqueue=True  # 异步写入，不阻塞主线程
)

# 获取配置
settings = get_settings()

# 创建FastAPI应用
app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    description="基于HelloAgents框架的智能旅行规划助手API",
    docs_url="/docs",
    redoc_url="/redoc"
)

# 注册限流器与错误处理
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# 注册集中式错误处理器（AppError、RequestValidationError、兜底 Exception）
register_error_handlers(app)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.get_cors_origins_list(),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(trip.router, prefix="/api")
app.include_router(poi.router, prefix="/api")
app.include_router(map_routes.router, prefix="/api")
app.include_router(share.router, prefix="/api")
app.include_router(auth.router, prefix="/api")   # 功能18：/api/auth/*
app.include_router(user.router, prefix="/api")   # 功能23：/api/user/*
app.include_router(guide.router, prefix="/api")  # 功能27：/api/guide/*


@app.on_event("startup")
async def startup_event():
    """应用启动事件"""
    # 创建数据库表（幂等）
    create_db_tables()
    logger.info("=" * 60)
    logger.info(f"🚀 {settings.app_name} v{settings.app_version}")
    logger.info("=" * 60)

    # 打印配置信息
    print_config()

    # 验证配置
    try:
        validate_config()
        logger.success("✅ 配置验证通过")
    except ValueError as e:
        logger.error(f"❌ 配置验证失败:\n{e}")
        logger.error("请检查.env文件并确保所有必要的配置项都已设置")
        raise

    logger.info("📚 API文档: http://localhost:8000/docs")
    logger.info("📖 ReDoc文档: http://localhost:8000/redoc")
    logger.info("=" * 60)


@app.on_event("shutdown")
async def shutdown_event():
    """应用关闭事件"""
    logger.info("=" * 60)
    logger.info("👋 应用正在关闭...")
    logger.info("=" * 60)


@app.get("/")
async def root():
    """根路径"""
    return {
        "name": settings.app_name,
        "version": settings.app_version,
        "status": "running",
        "docs": "/docs",
        "redoc": "/redoc"
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {
        "status": "healthy",
        "service": settings.app_name,
        "version": settings.app_version
    }


if __name__ == "__main__":
    import uvicorn
    
    uvicorn.run(
        "app.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=True
    )

