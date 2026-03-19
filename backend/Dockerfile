# ===== 后端 Dockerfile =====
# Python 3.12 + Conda 环境 → 基于官方 miniconda 镜像
FROM continuumio/miniconda3:latest

# 安装系统依赖（uvx/amap-mcp-server 需要）
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# 创建工作目录
WORKDIR /app

# 先复制依赖文件，利用 Docker 分层缓存
COPY requirements.txt ./

# 创建 Conda 环境并安装依赖
RUN conda create -n trip-agent python=3.12 -y \
    && conda run -n trip-agent pip install --no-cache-dir -r requirements.txt

# 安装 uvx（供 amap-mcp-server 使用）
RUN conda run -n trip-agent pip install uv

# 复制应用代码
COPY . .

# 创建日志目录
RUN mkdir -p logs

# 暴露端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/ || exit 1

# 启动命令（使用 conda run 激活环境）
CMD ["conda", "run", "--no-capture-output", "-n", "trip-agent", \
    "uvicorn", "app.api.main:app", \
    "--host", "0.0.0.0", "--port", "8000", \
    "--log-level", "info"]
