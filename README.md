# douyin-nas-asr
## Douyin NAS Downloader & Transcriber

一个基于 **FastAPI** 的后端服务，配合 **Tampermonkey**，实现从浏览器一键将抖音视频（无水印）下载到 NAS，并使用本地 `faster-whisper` 模型进行离线语音转录（ASR）。

> Maintainer: [@Kalopers](https://github.com/Kalopers)  
> Language: 🇨🇳 Chinese UI / API comments, English-friendly codebase

---

## ✨ 特性 / Features

- **无水印下载**
  - 集成第三方解析服务，自动解析抖音分享链接
  - 下载最高画质的无水印视频

- **NAS 自动归档**
  - 以 `作者昵称/视频描述` 的目录结构自动整理本地文件
  - JSON 元数据、封面图、视频文件分目录存放，方便后续索引与备份

- **本地 ASR 转录**
  - 使用 `faster-whisper` 模型进行中文离线转录
  - 支持 CPU 推理，可选量化模型（如 int8）以降低内存占用
  - 输出字幕文本，可扩展为 `.srt` / `.vtt` 等格式

- **异步任务队列**
  - 下载 + 转录使用后台任务队列管理，前端通过任务 ID 轮询进度
  - 解决长视频导致 HTTP 超时的问题

- **PostgreSQL 元数据索引**
  - 使用 PostgreSQL 管理视频索引，防止重复下载和路径冲突
  - 便于你在 NAS 上做二次开发（如搭建个人“抖音资料库”）

---

## 🏗 架构概览

> 浏览器 → 油猴脚本 → FastAPI → 下载器 & 转录器 → NAS / PostgreSQL

- **前端**：Tampermonkey 脚本挂在抖音网页上，抓取当前视频信息并发起 API 请求  
- **后端**：FastAPI 提供统一接口：
  - 创建下载任务
  - 查询任务进度
  - 触发转录
- **存储**：
  - 媒体文件、封面图、元数据 JSON 存在 NAS（通过挂载目录）
  - 视频索引存入 PostgreSQL
- **转录**：
  - 使用 `faster-whisper` 在本地进行语音识别，支持 CPU/GPU

---

## 📦 环境要求

- Python 3.10+
- FFmpeg（用于音频提取）
- PostgreSQL 14+（或兼容版本）
- 一个挂载了 NAS 的目录（如 `/mnt/nas/douyin`）
- （可选）Docker / Docker Compose

---

## 🚀 快速开始（本地开发）

### 1. 克隆项目

```bash
git clone https://github.com/your-github-id/douyin-nas-asr.git
cd douyin-nas-asr
```

### 2. 创建并编辑 .env
基于示例文件创建：
```bash
cp .env.example .env
```

然后根据你的环境修改其中的：
- 数据库配置：POSTGRES_*、DATABASE_URL
- NAS 路径：NAS_JSON_DIR / NAS_VIDEO_DIR / NAS_IMAGE_DIR
- 第三方解析服务密钥：例如 DY_TIKHUB_AUTH_KEY
- Whisper 模型大小：WHISPER_MODEL_SIZE（如 small / medium）

### 3. 安装依赖
建议使用虚拟环境：
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 4. 启动数据库（可选：如果你本机没装 PostgreSQL）
如果使用 Docker 里的数据库，可以先运行：
```bash
docker compose up -d db
```

### 5. 启动 API 服务
```
uvicorn src.server.main:app --host 0.0.0.0 --port 17650 --reload
```

启动后，默认可以访问：

- API文档: http://localhost:17650/docs
- 健康检查: GET /health

## 🐳 使用 Docker / Docker Compose 部署
本仓库提供了 Dockerfile 和 docker-compose.yml，方便一键部署。

### 1. 编辑 .env
确保 .env 中的配置与你的 NAS 路径和数据库需求匹配。

### 2. 启动服务
```
docker compose up -d
```
这会启动两个容器：
- douyin-nas-asr-app：FastAPI 应用
- douyin-nas-asr-db：PostgreSQL 数据库

默认暴露端口：
- 应用服务：17650（可在 docker-compose.yml 中调整）

## ⚙️ 配置说明（.env）
以下是 .env.example 中关键字段示例说明：
- 应用相关
  - APP_HOST / APP_PORT：FastAPI 绑定地址和端口
  - SECRET_KEY：用于签名、安全相关用途的随机字符串
- NAS 路径（容器内路径）
  - NAS_JSON_DIR：元数据 JSON 存放目录（容器内，例如 /app/data/json）
  - NAS_VIDEO_DIR：视频文件目录（例如 /app/data/videos）
  - NAS_IMAGE_DIR：封面图目录（例如 /app/data/images）
- 数据库配置
  - POSTGRES_HOST / POSTGRES_PORT
  - POSTGRES_USER / POSTGRES_PASSWORD / POSTGRES_DB
  - DATABASE_URL：应用使用的完整连接串（通常为 postgresql+psycopg2://...）
- Whisper 配置
  - WHISPER_MODEL_SIZE：如 small / medium
  - WHISPER_DEVICE：cpu 或 cuda
- 第三方解析服务
  - DY_TIKHUB_AUTH_KEY 等：用于解析抖音链接的第三方服务密钥

## 🧪 API 大致说明
- POST /tasks/download-and-transcribe
  - Body: { "share_url": "...", "transcribe": true }
  - 返回：{ "task_id": "xxx" }
- GET /tasks/{task_id}
  - 查询任务状态：PENDING / DOWNLOADING / TRANSCRIBING / SUCCESS / FAILED
  - 成功时返回文件路径、转录文本等
- GET /videos/{video_id}
  - 查询某个视频的元数据和本地路径

## ❓ 常见问题（FAQ）
**Q: 转录速度很慢？**   
A: 使用 CPU 推理时，速度会明显慢于 GPU。可以尝试：
选用更小的模型（如 small 或 base）
开启模型量化（如 int8）

**Q: 任务一直 Pending / 卡住？**  
A:确认 FFmpeg 是否正常安装；检查网络是否能访问解析服务（如 TikHub）；查看 logs/ 中的服务日志以定位具体错误

**Q: 为什么要用 PostgreSQL？**  
A: 主要用于统一管理 video_id 与本地文件路径的映射，防止重复下载相同视频；支持后续做搜索、标签、筛选等二次开发。  

**Q: 是否可以只用文件系统，不用数据库？**  
A: 理论上可以，但在大量视频、作者名重复时会比较脆弱。推荐使用 PostgreSQL，稳定性更好。

## 📜 License
本项目采用 MIT License 开源。详见 LICENSE 文件。