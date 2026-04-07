# -*- coding: utf-8 -*-
# @Date     : 2025/11/21
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : tasks.py
# @Desc     : 任务抽象 & 任务管理


from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Awaitable, Callable, Optional
from loguru import logger

from src.server.models import (
    JobInfo,
    TaskStatus,
    TaskKind,
    ErrorCode,
    ErrorInfo,
    MessageCode,
    MESSAGE_TEMPLATES,
)
from src.server.downloader import (
    DouyinDownloader,
    DownloadError,
)
from src.server.transcriber import Transcriber


class BaseTask(ABC):
    """
    所有任务的抽象基类
    - 持有一个 JobInfo，用于对外暴露状态
    - run() 里实现具体业务逻辑
    """

    def __init__(self, job: JobInfo):
        self.job = job
        self._persist_hook: Optional[
            Callable[[JobInfo, TaskKind], Awaitable[None]]
        ] = None

    @property
    def id(self) -> str:
        return self.job.task_id

    def attach_persist_hook(
        self, hook: Callable[[JobInfo, TaskKind], Awaitable[None]]
    ) -> None:
        self._persist_hook = hook

    async def persist_state(self) -> None:
        if self._persist_hook is not None:
            await self._persist_hook(self.job, self.task_kind)

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

    def fail_from_download_error(self, exc: DownloadError) -> None:
        self.fail(
            code=exc.error_code,
            msg_code=exc.message_code,
            exc=exc,
        )

    @abstractmethod
    async def run(self) -> None:
        """执行任务主体逻辑"""
        ...


class DownloadTask(BaseTask):
    """
    仅下载任务
    """
    task_kind = TaskKind.DOWNLOAD

    def __init__(self, job: JobInfo, video_id: str, downloader: DouyinDownloader):
        super().__init__(job)
        self.video_id = video_id
        self.downloader = downloader

    async def run(self) -> None:
        try:
            self.job.status = TaskStatus.PROCESSING
            self.set_message(MessageCode.DOWNLOAD_RUNNING)
            await self.persist_state()

            download_result = await self.downloader.download(self.video_id)
            logger.debug(
                f"DownloadTask got files: {download_result.files}, "
                f"urls: {download_result.download_urls}"
            )

            self.job.status = TaskStatus.COMPLETED
            self.job.result = [str(f) for f in download_result.files]
            self.job.download_urls = download_result.download_urls
            self.set_message(MessageCode.DOWNLOAD_SUCCESS)
            await self.persist_state()

        except DownloadError as e:
            logger.warning(f"Task {self.id} failed with business error: {e}")
            self.fail_from_download_error(e)
            await self.persist_state()
        except Exception as e:
            logger.exception(f"Task {self.id} failed")
            self.fail(
                code=ErrorCode.INTERNAL_ERROR,
                msg_code=MessageCode.INTERNAL_ERROR,
                exc=e,
            )
            await self.persist_state()


class DownloadAndTranscribeTask(BaseTask):
    """
    下载 + 转写 的组合任务
    """
    task_kind = TaskKind.DOWNLOAD_AND_TRANSCRIBE

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
            await self.persist_state()

            download_result = await self.downloader.download(self.video_id)
            files = download_result.files

            # 2. 转写
            self.set_message(MessageCode.TRANSCRIBE_RUNNING)
            await self.persist_state()
            transcript_result = ""

            for file_path in files:
                if file_path.suffix.lower() in [".mp4", ".mov", ".mkv"]:
                    try:
                        transcription = await self.transcriber.transcribe(file_path)
                        transcript_result = transcription.text
                    except Exception as e:
                        logger.exception(f"Transcribe error in task {self.id}")
                        self.fail(
                            code=ErrorCode.TRANSCRIBE_FAILED,
                            msg_code=MessageCode.TRANSCRIBE_FAILED,
                            exc=e,
                        )
                        await self.persist_state()
                        return
                    break

            if transcript_result:
                self.job.status = TaskStatus.COMPLETED
                self.job.result = transcript_result
                self.job.download_urls = download_result.download_urls
                self.set_message(MessageCode.TRANSCRIBE_SUCCESS)
                await self.persist_state()
            else:
                self.fail(
                    code=ErrorCode.TRANSCRIBE_EMPTY,
                    msg_code=MessageCode.TRANSCRIBE_EMPTY,
                )
                await self.persist_state()

        except DownloadError as e:
            logger.warning(f"Task {self.id} failed with business error: {e}")
            self.fail_from_download_error(e)
            await self.persist_state()
        except Exception as e:
            logger.exception(f"Task {self.id} failed")
            self.fail(
                code=ErrorCode.INTERNAL_ERROR,
                msg_code=MessageCode.INTERNAL_ERROR,
                exc=e,
            )
            await self.persist_state()
