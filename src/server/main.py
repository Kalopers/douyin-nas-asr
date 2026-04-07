# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : main.py
# @Desc     : FastAPI 服务器主程序

import sys
import uuid
import os
from pathlib import Path
from contextlib import asynccontextmanager

from loguru import logger
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    Header,
)
from fastapi.responses import JSONResponse


from src.server.settings import settings
from src.server.models import (
    JobInfo,
    TaskKind,
    TaskStatus,
    DownloadRequest,
    TaskResponse,
    MessageCode,
    MESSAGE_TEMPLATES,
)
from src.server.job_store import JobStore
from src.server.task_manager import TaskManager


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
    job_store = JobStore()
    task_manager.configure_store(job_store)
    app.state.job_store = job_store

    logger.info("JobStore 已准备就绪，API 进程仅负责入队和查状态。")

    yield

    logger.info("FastAPI 应用关闭...")
    job_store.dispose()
    logger.info("JobStore 已关闭。")


app = FastAPI(title="Douyin Downloader Service", lifespan=lifespan)


def build_readiness_report() -> dict:
    job_store = getattr(app.state, "job_store", None)

    report = {
        "status": "ready",
        "checks": {
            "database": {"ok": False, "detail": "job store not initialized"},
            "queue": {"ok": False, "detail": "job store not initialized"},
            "storage_json_dir": {"ok": False, "detail": "not checked"},
            "storage_video_dir": {"ok": False, "detail": "not checked"},
            "storage_image_dir": {"ok": False, "detail": "not checked"},
        },
    }

    if job_store is not None:
        report["checks"].update(job_store.readiness_report())

    storage_checks = {
        "storage_json_dir": settings.json_dir,
        "storage_video_dir": settings.video_dir,
        "storage_image_dir": settings.image_dir,
    }
    for check_name, path in storage_checks.items():
        path_exists = path.exists()
        path_writable = path_exists and os.access(path, os.W_OK)
        report["checks"][check_name] = {
            "ok": path_exists and path.is_dir() and path_writable,
            "detail": (
                f"path={path} exists={path_exists} writable={path_writable}"
            ),
        }

    if not all(check["ok"] for check in report["checks"].values()):
        report["status"] = "not_ready"

    return report


# ============================================================
# 依赖项
# ============================================================
async def verify_api_key(
    x_api_key: str = Header(..., alias=settings.api_key_header_name)
):
    if x_api_key != settings.dy_api_key:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    return True


@app.post(
    "/download",
    response_model=TaskResponse,
    dependencies=[Depends(verify_api_key)],
)
async def handle_download_request(
    body: DownloadRequest,
):
    """
    API 进程只负责创建任务并入队，不直接执行下载主链路。
    """
    task_id = str(uuid.uuid4())

    job = JobInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_id=body.video_id,
    )
    job.message_code = MessageCode.DOWNLOAD_PENDING
    job.message = MESSAGE_TEMPLATES[MessageCode.DOWNLOAD_PENDING]
    await task_manager.enqueue_job(job, TaskKind.DOWNLOAD)

    logger.info(f"[Download] 任务入队: {task_id} | 视频: {body.video_id}")

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
    body: DownloadRequest,
):
    task_id = str(uuid.uuid4())

    job = JobInfo(
        task_id=task_id,
        status=TaskStatus.PENDING,
        video_id=body.video_id,
    )
    job.message_code = MessageCode.DOWNLOAD_PENDING
    job.message = MESSAGE_TEMPLATES[MessageCode.DOWNLOAD_PENDING]
    await task_manager.enqueue_job(job, TaskKind.DOWNLOAD_AND_TRANSCRIBE)

    logger.info(f"[Download+Transcribe] 任务入队: {task_id} | 视频: {body.video_id}")

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
    job = await task_manager.get_job(task_id)
    if not job:
        raise HTTPException(status_code=404, detail="Task not found or expired")
    return job


@app.get("/")
def read_root():
    return {"message": "Douyin Downloader Service is running."}


@app.get("/healthz")
def healthz():
    return {"status": "ok"}


@app.get("/readyz")
def readyz():
    report = build_readiness_report()
    status_code = 200 if report["status"] == "ready" else 503
    return JSONResponse(status_code=status_code, content=report)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.server.main:app",
        host=settings.app_host,
        port=settings.app_port,
    )
