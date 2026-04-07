# -*- coding: utf-8 -*-
# @Date     : 2026/04/08
# @Author   : Codex
# @File     : base.py
# @Desc     : ASR backend 抽象接口

from __future__ import annotations

from abc import ABC, abstractmethod

from src.server.asr.types import TranscriptionResult


class ASREngine(ABC):
    backend_name: str
    model_name: str

    @abstractmethod
    def transcribe(self, audio_path: str) -> TranscriptionResult:
        """
        同步执行转写，供外层通过 asyncio.to_thread 调用。
        """
        ...
