# -*- coding: utf-8 -*-
# @Date     : 2025/11/21
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : tasks.py
# @Desc     : 任务抽象 & 任务管理


from __future__ import annotations

from abc import ABC, abstractmethod
from loguru import logger

from src.server.models import (
    JobInfo,
    TaskStatus,
    ErrorCode,
    ErrorInfo,
    MessageCode,
    MESSAGE_TEMPLATES,
)
from src.server.downloader import DouyinDownloader
from src.server.transcriber import Transcriber


class BaseTask(ABC):
    """
    所有任务的抽象基类
    - 持有一个 JobInfo，用于对外暴露状态
    - run() 里实现具体业务逻辑
    """

    def __init__(self, job: JobInfo):
        self.job = job

    @property
    def id(self) -> str:
        return self.job.task_id

    def set_message(self, code: MessageCode, **fmt: object) -> None:
        """
        统一设置任务的消息:
        - message_code: 结构化消息码
        - message: 渲染后的字符串（给人看的）
        """
        self.job.message_code = code
        template = MESSAGE_TEMPLATES.get(code)
        if template:
            self.job.message = template.format(**fmt)
        else:
            self.job.message = code.value

    def fail(
        self,
        code: ErrorCode,
        msg_code: MessageCode,
        exc: Exception | None = None,
        **fmt: object,
    ) -> None:
        """
        统一设置任务失败:
        - 状态
        - 对人类友好的 message（通过 msg_code 渲染）
        - 结构化的 error 信息
        """
        self.job.status = TaskStatus.FAILED
        self.set_message(msg_code, **fmt)

        detail = repr(exc) if exc is not None else None

        self.job.error = ErrorInfo(
            code=code,
            message=self.job.message,
            detail=detail,
        )

    @abstractmethod
    async def run(self) -> None:
        """执行任务主体逻辑"""
        ...


class DownloadTask(BaseTask):
    """
    仅下载任务
    """

    def __init__(self, job: JobInfo, video_id: str, downloader: DouyinDownloader):
        super().__init__(job)
        self.video_id = video_id
        self.downloader = downloader

    async def run(self) -> None:
        try:
            self.job.status = TaskStatus.PROCESSING
            self.set_message(MessageCode.DOWNLOAD_RUNNING)

            files = await self.downloader.download(self.video_id)

            if files:
                self.job.status = TaskStatus.COMPLETED
                self.job.result = [str(f) for f in files]
                self.set_message(MessageCode.DOWNLOAD_SUCCESS)
            else:
                self.fail(
                    code=ErrorCode.DOWNLOAD_FAILED,
                    msg_code=MessageCode.DOWNLOAD_FAILED,
                )

        except Exception as e:
            logger.exception(f"Task {self.id} failed")
            self.fail(
                code=ErrorCode.INTERNAL_ERROR,
                msg_code=MessageCode.INTERNAL_ERROR,
                exc=e,
            )


class DownloadAndTranscribeTask(BaseTask):
    """
    下载 + 转写 的组合任务
    """

    def __init__(
        self,
        job: JobInfo,
        video_id: str,
        downloader: DouyinDownloader,
        transcriber: Transcriber,
    ):
        super().__init__(job)
        self.video_id = video_id
        self.downloader = downloader
        self.transcriber = transcriber

    async def run(self) -> None:
        try:
            # 1. 下载
            self.job.status = TaskStatus.PROCESSING
            self.set_message(MessageCode.DOWNLOAD_RUNNING)

            files = await self.downloader.download(self.video_id)

            if not files:
                self.fail(
                    code=ErrorCode.NO_VIDEO_FOUND,
                    msg_code=MessageCode.DOWNLOAD_FAILED,
                )
                return

            # 2. 转写
            self.set_message(MessageCode.TRANSCRIBE_RUNNING)
            transcript_result = ""

            for file_path in files:
                if file_path.suffix.lower() in [".mp4", ".mov", ".mkv"]:
                    try:
                        transcript_result = await self.transcriber.transcribe(file_path)
                    except Exception as e:
                        logger.exception(f"Transcribe error in task {self.id}")
                        self.fail(
                            code=ErrorCode.TRANSCRIBE_FAILED,
                            msg_code=MessageCode.TRANSCRIBE_FAILED,
                            exc=e,
                        )
                        return
                    break

            if transcript_result:
                self.job.status = TaskStatus.COMPLETED
                self.job.result = transcript_result
                self.set_message(MessageCode.TRANSCRIBE_SUCCESS)
            else:
                self.fail(
                    code=ErrorCode.TRANSCRIBE_EMPTY,
                    msg_code=MessageCode.TRANSCRIBE_EMPTY,
                )

        except Exception as e:
            logger.exception(f"Task {self.id} failed")
            self.fail(
                code=ErrorCode.INTERNAL_ERROR,
                msg_code=MessageCode.INTERNAL_ERROR,
                exc=e,
            )
