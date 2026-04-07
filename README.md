# douyin-nas-asr

一个用于“抖音内容下载到 NAS，并可离线转写”的小型服务。

当前仓库的实际运行方式是：
- `api` 进程：接收请求、创建任务、查询状态
- `worker` 进程：执行下载、ffmpeg、ASR、落盘
- PostgreSQL：保存任务状态和索引

默认端口是 `17650`。仓库根目录没有 `run.sh`，开发脚本是 [utils/run.sh](/opt/docker-services/douyin-nas-asr/utils/run.sh)。

## 快速开始

1. 准备配置：
```bash
cp .env.example .env
```

2. 安装依赖：
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. 启动数据库：
```bash
docker compose up -d db
```

4. 启动 API：
```bash
python -m src.server.main
```

5. 启动 worker：
```bash
python -m src.server.worker
```

开发模式下也可以只启动带热更新的 API：
```bash
./utils/run.sh
```

## Docker Compose

仓库内自带的 [docker-compose.yml](/opt/docker-services/douyin-nas-asr/docker-compose.yml) 会启动：
- `api`
- `worker`
- `db`

启动命令：
```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
docker compose logs -f api worker
```

## 关键配置

默认值统一定义在 [src/server/settings.py](/opt/docker-services/douyin-nas-asr/src/server/settings.py)。

最常用的配置项：
- `APP_HOST` / `APP_PORT`
- `DY_API_KEY`
- `API_KEY_HEADER_NAME`
- `DY_TIKHUB_AUTH_KEY`
- `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
- `NAS_JSON_DIR` / `NAS_VIDEO_DIR` / `NAS_IMAGE_DIR`
- `ASR_BACKEND`
- `ASR_MODEL`
- `FASTER_WHISPER_MODEL`
- `ASR_MAX_CONCURRENCY`
- `WORKER_POLL_INTERVAL_SECONDS`
- `WORKER_CONCURRENCY`

ASR 默认使用 `sensevoice`，需要回滚时可切到 `faster_whisper`：
```env
ASR_BACKEND=faster_whisper
FASTER_WHISPER_MODEL=medium
```

## API

所有业务接口都需要带鉴权头，默认是：
```http
X-API-KEY: <DY_API_KEY>
```

主要接口：
- `POST /download`
- `POST /download_and_transcribe`
- `GET /task/{task_id}`
- `GET /healthz`
- `GET /readyz`

最小调用示例：
```bash
curl -X POST http://localhost:17650/download \
  -H 'Content-Type: application/json' \
  -H 'X-API-KEY: change_me_to_your_secure_key' \
  -d '{"video_id":"1234567890123456789"}'
```

```bash
curl -H 'X-API-KEY: change_me_to_your_secure_key' \
  http://localhost:17650/task/<task_id>
```

## 健康检查

- `/healthz`
  - 只表示 API 进程存活
- `/readyz`
  - 表示 API 当前具备接收流量和入队条件
  - 当前会检查：
    - PostgreSQL 可连接
    - `jobs` 表可访问
    - `NAS_JSON_DIR` / `NAS_VIDEO_DIR` / `NAS_IMAGE_DIR` 存在且可写

说明：
- `/readyz` 不代表 worker 一定正在消费任务
- worker 状态建议结合 `docker compose logs worker` 和任务状态一起看

## 最小验证

```bash
curl http://localhost:17650/healthz
curl http://localhost:17650/readyz
```

```bash
curl -X POST http://localhost:17650/download_and_transcribe \
  -H 'Content-Type: application/json' \
  -H 'X-API-KEY: change_me_to_your_secure_key' \
  -d '{"video_id":"1234567890123456789"}'
```

```bash
curl -H 'X-API-KEY: change_me_to_your_secure_key' \
  http://localhost:17650/task/<task_id>
```

## 排障

- `readyz` 失败：先看 API 日志和数据库配置
- 任务长时间停在 `pending`：先看 worker 是否启动、worker 日志是否报错
- ASR 依赖不稳定：把 `ASR_BACKEND` 改回 `faster_whisper`，然后重启 worker
- 目录不可写：检查 NAS 挂载路径和容器内映射是否正确
