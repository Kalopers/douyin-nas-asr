# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : main.py
# @Desc     : FastAPI 服务器主程序

import sys
import uuid
from pathlib import Path
from contextlib import asynccontextmanager

import aiohttp
from loguru import logger
from asyncio import Semaphore
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Header,
    status,
    BackgroundTasks,
    Request,
)


from src.server.settings import settings
from src.server.models import (
    JobInfo,
    TaskStatus,
    DownloadRequest,
    TaskResponse,
    MessageCode,
)
from src.server.downloader import DouyinDownloader
from src.server.transcriber import Transcriber
from src.server.json_manager import DataManager
from src.server.task_manager import TaskManager
from src.server.tasks import DownloadTask, DownloadAndTranscribeTask


# ============================================================
# 日志配置
# ============================================================
logger.remove()
logger.add(
    sys.stdout,
    level="INFO",
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
    "<level>{level: <8}</level> | "
    "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
    "<level>{message}</level>",
)

Path("logs").mkdir(exist_ok=True)
logger.add(
    "logs/api_server.log",
    rotation="00:00",
    retention="10 days",
    level="INFO",
    encoding="utf-8",
    compression="zip",
)


# ============================================================
# 全局 TaskManager
# ============================================================
task_manager = TaskManager()


# ============================================================
# 应用生命周期
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("FastAPI 应用启动...")
    app.state.semaphore = Semaphore(3)
    # 全局 aiohttp session
    session = aiohttp.ClientSession()

    # 实例化 DataManager（用于索引与 JSON 缓存）
    data_manager = DataManager(base_dir=str(settings.json_dir))

    # Downloader：需要 data_manager + tikhub_auth_key
    downloader = DouyinDownloader(
        api_key=settings.tikhub_auth_key,
        session=session,
        data_manager=data_manager,
    )

    # Transcriber
    transcriber = Transcriber()

    # 注入到 app.state
    app.state.session = session
    app.state.downloader = downloader
    app.state.transcriber = transcriber
    app.state.data_manager = data_manager

    logger.info("Downloader, Transcriber, DataManager 已准备就绪。")

    yield

    logger.info("FastAPI 应用关闭...")
    await session.close()
    logger.info("aiohttp.ClientSession 已关闭。")


app = FastAPI(title="Douyin Downloader Service", lifespan=lifespan)


# ============================================================
# 依赖项
# ============================================================
async def verify_api_key(
    x_api_key: str = Header(..., alias=settings.api_key_header_name)
):
    if x_api_key != settings.dy_api_key:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return True


def get_downloader(request: Request) -> DouyinDownloader:
    return request.app.state.downloader


def get_transcriber(request: Request) -> Transcriber:
    return request.app.state.transcriber


# ============================================================
# /download → 使用 DownloadTask + TaskManager
# ============================================================
@app.post(
    "/download",
    response_model=TaskResponse,
    dependencies=[Depends(verify_api_key)],
)
async def handle_download_request(
    body: DownloadRequest,  # 1. 改名：这是前端传来的 JSON 数据
    request: Request,  # 2. 新增：这是 FastAPI 的请求对象（包含 app.state）
    background_tasks: BackgroundTasks,
    downloader: DouyinDownloader = Depends(get_downloader),
):
    """
    纯下载也使用 TaskManager 统一管理，返回 task_id，可轮询状态。
    """
    task_id = str(uuid.uuid4())

    job = JobInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_id=body.video_id,
    )

    task = DownloadTask(
        job=job,
        video_id=body.video_id,
        downloader=downloader,
    )
    task.set_message(MessageCode.DOWNLOAD_PENDING)

    task_manager.register(task)

    logger.info(f"[Download] 任务入队: {task_id} | 视频: {body.video_id}")

    background_tasks.add_task(
        task_manager.run_task, task_id, request.app.state.semaphore
    )

    return TaskResponse(
        status="queued",
        task_id=task_id,
        message="下载任务已提交，请使用 GET /task/{task_id} 查询状态",
    )


# ============================================================
# /download_and_transcribe → DownloadAndTranscribeTask
# ============================================================
@app.post(
    "/download_and_transcribe",
    response_model=TaskResponse,
    dependencies=[Depends(verify_api_key)],
)
async def handle_download_and_transcribe_request(
    body: DownloadRequest,  # 1. 改名：这是前端传来的 JSON 数据
    request: Request,  # 2. 新增：这是 FastAPI 的请求对象（包含 app.state）
    background_tasks: BackgroundTasks,
    downloader: DouyinDownloader = Depends(get_downloader),
    transcriber: Transcriber = Depends(get_transcriber),
):
    task_id = str(uuid.uuid4())

    job = JobInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_id=body.video_id,
    )

    task = DownloadAndTranscribeTask(
        job=job,
        video_id=body.video_id,
        downloader=downloader,
        transcriber=transcriber,
    )
    task.set_message(MessageCode.DOWNLOAD_PENDING)

    task_manager.register(task)

    logger.info(f"[Download+Transcribe] 任务入队: {task_id} | 视频: {body.video_id}")

    background_tasks.add_task(
        task_manager.run_task, task_id, request.app.state.semaphore
    )

    return TaskResponse(
        status="queued",
        task_id=task_id,
        message="任务已提交，请使用 GET /task/{task_id} 查询状态",
    )


# ============================================================
# 查询任务状态
# ============================================================
@app.get(
    "/task/{task_id}",
    response_model=JobInfo,
    dependencies=[Depends(verify_api_key)],
)
async def get_task_status(task_id: str):
    job = task_manager.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found or expired")
    return job


@app.get("/")
def read_root():
    return {"message": "Douyin Downloader Service is running."}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=17649)
