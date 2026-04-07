# -*- coding: utf-8 -*-
# @Date     : 2026/04/08
# @Author   : Codex
# @File     : worker.py
# @Desc     : 任务 worker 进程入口

import asyncio
import sys
from pathlib import Path

import aiohttp
from loguru import logger
from asyncio import Semaphore

from src.server.downloader import DouyinDownloader
from src.server.job_store import JobStore, QueuedJob
from src.server.json_manager import DataManager
from src.server.models import TaskKind
from src.server.settings import settings
from src.server.task_manager import TaskManager
from src.server.tasks import DownloadAndTranscribeTask, DownloadTask
from src.server.transcriber import Transcriber


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
    "logs/worker.log",
    rotation="00:00",
    retention="10 days",
    level="INFO",
    encoding="utf-8",
    compression="zip",
)


class WorkerRuntime:
    def __init__(self):
        self.job_store = JobStore()
        self.task_manager = TaskManager()
        self.task_manager.configure_store(self.job_store)
        self.job_store.mark_processing_jobs_as_failed()
        self.semaphore = Semaphore(settings.worker_concurrency)
        self.data_manager = DataManager(base_dir=str(settings.json_dir))
        self.session: aiohttp.ClientSession | None = None
        self.downloader: DouyinDownloader | None = None
        self.transcriber: Transcriber | None = None

    async def setup(self) -> None:
        self.session = aiohttp.ClientSession()
        self.downloader = DouyinDownloader(
            api_key=settings.tikhub_auth_key,
            session=self.session,
            data_manager=self.data_manager,
        )
        self.transcriber = Transcriber()
        logger.info("Worker 依赖初始化完成。")

    async def shutdown(self) -> None:
        if self.session is not None:
            await self.session.close()
        self.job_store.dispose()
        logger.info("Worker 已关闭。")

    def build_task(self, queued_job: QueuedJob):
        if self.downloader is None or self.transcriber is None:
            raise RuntimeError("Worker 未完成初始化。")

        if queued_job.task_kind == TaskKind.DOWNLOAD:
            return DownloadTask(
                job=queued_job.job,
                video_id=queued_job.job.video_id,
                downloader=self.downloader,
            )

        if queued_job.task_kind == TaskKind.DOWNLOAD_AND_TRANSCRIBE:
            return DownloadAndTranscribeTask(
                job=queued_job.job,
                video_id=queued_job.job.video_id,
                downloader=self.downloader,
                transcriber=self.transcriber,
            )

        raise ValueError(f"不支持的任务类型: {queued_job.task_kind}")

    async def run_forever(self) -> None:
        await self.setup()
        try:
            while True:
                queued_job = await asyncio.to_thread(self.job_store.claim_next_pending_job)
                if queued_job is None:
                    await asyncio.sleep(settings.worker_poll_interval_seconds)
                    continue

                logger.info(
                    f"Worker 领取任务: {queued_job.job.task_id} | 类型: {queued_job.task_kind.value}"
                )
                task = self.build_task(queued_job)
                await self.task_manager.register(task)
                await self.task_manager.run_task(task.id, self.semaphore)
        finally:
            await self.shutdown()


async def main() -> None:
    runtime = WorkerRuntime()
    await runtime.run_forever()


if __name__ == "__main__":
    asyncio.run(main())
