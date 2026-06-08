from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routes import orchestrator

# 创建 FastAPI 应用实例
app = FastAPI(
    title="Orchestrator API",
    description="Orchestrator 服务的 RESTful API",
    version="1.0.0"
)

# 配置 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 在生产环境中应该设置具体的域名
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(orchestrator.router, prefix="/api/orchestrator", tags=["orchestrator"])

# 根路径
@app.get("/")
async def root():
    return {"message": "Orchestrator API is running"}

# 健康检查端点
@app.get("/health")
async def health_check():
    return {"status": "healthy"}
