# ===== 前端 Dockerfile =====
# 两阶段构建：Node.js 构建 → Nginx 服务

# ---- 构建阶段 ----
FROM node:20-alpine AS builder

WORKDIR /app

# 先复制依赖文件，利用缓存
COPY package*.json ./

RUN npm ci --prefer-offline

# 复制源代码并构建
COPY . .

# 构建时注入后端地址（可通过 docker-compose 的 build.args 覆盖）
ARG VITE_API_BASE_URL=http://localhost:8000
ARG VITE_AMAP_WEB_JS_KEY=
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
ENV VITE_AMAP_WEB_JS_KEY=${VITE_AMAP_WEB_JS_KEY}

RUN npm run build

# ---- 服务阶段 ----
FROM nginx:alpine

# 复制构建产物
COPY --from=builder /app/dist /usr/share/nginx/html

# 自定义 Nginx 配置：支持 Vue Router history 模式，并代理 /api 到后端
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
