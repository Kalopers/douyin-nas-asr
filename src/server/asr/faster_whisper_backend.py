# -*- coding: utf-8 -*-
# @Date     : 2026/04/08
# @Author   : Codex
# @File     : faster_whisper_backend.py
# @Desc     : faster-whisper backend 封装

from loguru import logger
from faster_whisper import WhisperModel

from src.server.asr.base import ASREngine
from src.server.asr.types import TranscriptionResult, TranscriptionSegment
from src.server.settings import settings


class FasterWhisperEngine(ASREngine):
    backend_name = "faster_whisper"

    def __init__(self):
        self.model_name = settings.resolved_faster_whisper_model

        logger.info(
            f"Loading ASR backend={self.backend_name}, model={self.model_name}..."
        )
        self.model = WhisperModel(
            self.model_name,
            device=settings.asr_device,
            compute_type=settings.asr_compute_type,
            cpu_threads=settings.asr_cpu_threads,
        )
        logger.info(
            f"ASR backend loaded successfully: {self.backend_name}/{self.model_name}"
        )

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        prompt = "这是一个视频的音频转录，请使用正确的标点符号。"
        segments, _info = self.model.transcribe(
            audio_path,
            beam_size=5,
            language="zh",
            vad_filter=True,
            vad_parameters=dict(min_silence_duration_ms=500),
            initial_prompt=prompt,
        )

        result_segments = []
        text_parts = []
        for segment in segments:
            text_parts.append(segment.text)
            result_segments.append(
                TranscriptionSegment(
                    start=segment.start,
                    end=segment.end,
                    text=segment.text,
                )
            )

        return TranscriptionResult(
            text="".join(text_parts),
            backend=self.backend_name,
            model=self.model_name,
            segments=result_segments,
        )
