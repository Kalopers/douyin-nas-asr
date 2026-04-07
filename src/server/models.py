# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : models.py
# @Desc     : Pydantic 数据模型和枚举类型

import time
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


class MessageCode(str, Enum):
    DOWNLOAD_PENDING = "download_pending"
    DOWNLOAD_RUNNING = "download_running"
    DOWNLOAD_SUCCESS = "download_success"
    DOWNLOAD_FAILED = "download_failed"
    DOWNLOAD_INVALID_INPUT = "download_invalid_input"
    DOWNLOAD_NOT_FOUND = "download_not_found"
    DOWNLOAD_UPSTREAM_ERROR = "download_upstream_error"
    DOWNLOAD_UNSUPPORTED_MEDIA = "download_unsupported_media"

    TRANSCRIBE_PENDING = "transcribe_pending"
    TRANSCRIBE_RUNNING = "transcribe_running"
    TRANSCRIBE_SUCCESS = "transcribe_success"
    TRANSCRIBE_EMPTY = "transcribe_empty"
    TRANSCRIBE_FAILED = "transcribe_failed"

    INTERNAL_ERROR = "internal_error"


MESSAGE_TEMPLATES: Dict[MessageCode, str] = {
    MessageCode.DOWNLOAD_PENDING: "Task created, waiting to download.",
    MessageCode.DOWNLOAD_RUNNING: "Downloading video...",
    MessageCode.DOWNLOAD_SUCCESS: "Download success.",
    MessageCode.DOWNLOAD_FAILED: "Download failed or no video found.",
    MessageCode.DOWNLOAD_INVALID_INPUT: "Invalid video id or share url.",
    MessageCode.DOWNLOAD_NOT_FOUND: "Video not found.",
    MessageCode.DOWNLOAD_UPSTREAM_ERROR: "TikHub API request failed.",
    MessageCode.DOWNLOAD_UNSUPPORTED_MEDIA: "Unsupported media type.",
    MessageCode.TRANSCRIBE_PENDING: "Task created, waiting to transcribe.",
    MessageCode.TRANSCRIBE_RUNNING: "Transcribing (please wait)...",
    MessageCode.TRANSCRIBE_SUCCESS: "Transcription success.",
    MessageCode.TRANSCRIBE_EMPTY: "Transcription returned empty.",
    MessageCode.TRANSCRIBE_FAILED: "Transcription failed.",
    MessageCode.INTERNAL_ERROR: "Internal error occurred.",
}


class ErrorCode(str, Enum):
    INTERNAL_ERROR = "internal_error"
    DOWNLOAD_FAILED = "download_failed"
    NO_VIDEO_FOUND = "no_video_found"
    INVALID_VIDEO_INPUT = "invalid_video_input"
    TIKHUB_API_ERROR = "tikhub_api_error"
    UNSUPPORTED_MEDIA = "unsupported_media"
    TRANSCRIBE_FAILED = "transcribe_failed"
    TRANSCRIBE_EMPTY = "transcribe_empty"


class ErrorInfo(BaseModel):
    code: ErrorCode
    message: str
    detail: Optional[str] = None


class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class TaskKind(str, Enum):
    DOWNLOAD = "download"
    DOWNLOAD_AND_TRANSCRIBE = "download_and_transcribe"


class JobInfo(BaseModel):
    task_id: str
    status: TaskStatus
    video_id: str
    message_code: Optional[MessageCode] = None
    download_urls: Optional[List[str]] = None
    message: Optional[str] = ""
    result: Optional[Any] = None
    created_at: float = Field(default_factory=time.time)
    error: Optional[ErrorInfo] = None


class DownloadRequest(BaseModel):
    video_id: str


class TaskResponse(BaseModel):
    status: str
    task_id: str
    message: str
