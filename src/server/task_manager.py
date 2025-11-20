# -*- coding: utf-8 -*-
# @Date     : 2025/11/21
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : task_manager.py
# @Desc     : 任务管理器

import time
import asyncio
from loguru import logger
from typing import Dict, Optional, List

from src.server.tasks import BaseTask
from src.server.models import JobInfo
from src.server.settings import settings


class TaskManager:
    """
    统一管理任务：
    - 注册任务
    - 查询任务 (返回 JobInfo)
    - 执行任务
    - 清理过期任务
    """

    def __init__(self):
        self._tasks: Dict[str, BaseTask] = {}

    def register(self, task: BaseTask) -> None:
        self._tasks[task.id] = task

    def get_job(self, task_id: str) -> Optional[JobInfo]:
        task = self._tasks.get(task_id)
        return task.job if task else None

    def exists(self, task_id: str) -> bool:
        return task_id in self._tasks

    async def run_task(self, task_id: str, semaphore: asyncio.Semaphore) -> None:
        task = self._tasks.get(task_id)
        if not task:
            logger.warning(f"Task {task_id} not found when trying to run")
            return

        async with semaphore:
            logger.info(f"Task {task_id} acquired semaphore, starting...")
            await task.run()
        self.cleanup_old_jobs()

    def cleanup_old_jobs(self) -> None:
        now = time.time()
        expired_ids: List[str] = []
        for tid, task in self._tasks.items():
            if now - task.job.created_at > settings.JOB_RETENTION_SECONDS:
                expired_ids.append(tid)

        for tid in expired_ids:
            self._tasks.pop(tid, None)

        if expired_ids:
            logger.info(f"清理了 {len(expired_ids)} 个过期任务: {expired_ids}")
