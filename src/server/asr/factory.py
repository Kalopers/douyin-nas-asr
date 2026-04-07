# -*- coding: utf-8 -*-
# @Date     : 2026/04/08
# @Author   : Codex
# @File     : factory.py
# @Desc     : ASR backend 工厂

from src.server.asr.base import ASREngine
from src.server.settings import settings


def create_asr_engine() -> ASREngine:
    backend = settings.asr_backend

    if backend == "sensevoice":
        from src.server.asr.sensevoice_backend import SenseVoiceEngine

        return SenseVoiceEngine()

    if backend == "faster_whisper":
        from src.server.asr.faster_whisper_backend import FasterWhisperEngine

        return FasterWhisperEngine()

    raise ValueError(f"Unsupported ASR backend: {backend}")
