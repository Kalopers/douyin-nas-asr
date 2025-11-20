# 使用 Python 3.10 轻量级版本
FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置时区为上海（可按需调整）
ENV TZ=Asia/Shanghai
RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone

# 安装系统依赖
# ffmpeg: 音频提取
# libpq-dev, gcc: PostgreSQL 驱动编译
RUN apt-get update && apt-get install -y \
    ffmpeg \
    libpq-dev \
    gcc \
  && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt ./requirements.txt

RUN pip install --no-cache-dir --upgrade pip \
  && pip install --no-cache-dir -r requirements.txt

# 复制项目代码
COPY . /app

# 创建容器内部的数据目录
# 注意：这里创建的是容器里的路径，随后我们会把 NAS 路径挂载到这里
RUN mkdir -p \
    /app/logs \
    /app/data/json \
    /app/data/videos \
    /app/data/images

# 设置 PYTHONPATH，使得 src.server 等模块可被导入
ENV PYTHONPATH=/app

# 暴露端口（需与 uvicorn --port 一致）
EXPOSE 17650

# 启动命令
CMD ["uvicorn", "src.server.main:app", "--host", "0.0.0.0", "--port", "17650"]
