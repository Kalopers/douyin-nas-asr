# -*- coding: utf-8 -*-
# @Date     : 2026/04/08
# @Author   : Codex
# @File     : sensevoice_backend.py
# @Desc     : SenseVoice backend 封装

from __future__ import annotations

from typing import Any

from loguru import logger

from src.server.asr.base import ASREngine
from src.server.asr.types import TranscriptionResult, TranscriptionSegment
from src.server.settings import settings


class SenseVoiceEngine(ASREngine):
    backend_name = "sensevoice"

    def __init__(self):
        self.model_name = settings.resolved_sensevoice_model

        try:
            from funasr import AutoModel
        except ImportError as exc:
            raise RuntimeError(
                "SenseVoice backend requires the optional 'funasr' dependency. "
                "Install requirements.txt or switch ASR_BACKEND=faster_whisper."
            ) from exc

        init_kwargs = {
            "model": self.model_name,
            "device": settings.asr_device,
            "trust_remote_code": True,
        }

        logger.info(
            f"Loading ASR backend={self.backend_name}, model={self.model_name}..."
        )

        try:
            self.model = AutoModel(**init_kwargs)
        except TypeError:
            init_kwargs.pop("trust_remote_code", None)
            self.model = AutoModel(**init_kwargs)

        logger.info(
            f"ASR backend loaded successfully: {self.backend_name}/{self.model_name}"
        )

    def _generate(self, audio_path: str) -> Any:
        generate_variants = [
            {
                "input": audio_path,
                "cache": {},
                "language": "zh",
                "use_itn": True,
            },
            {
                "input": audio_path,
                "language": "zh",
                "use_itn": True,
            },
            {
                "input": audio_path,
                "cache": {},
            },
            {
                "input": audio_path,
            },
        ]

        last_error: Exception | None = None
        for kwargs in generate_variants:
            try:
                return self.model.generate(**kwargs)
            except TypeError as exc:
                last_error = exc

        if last_error is not None:
            raise last_error

        raise RuntimeError("SenseVoice generate() failed without a concrete error.")

    def _coerce_float(self, value: Any) -> float | None:
        if value is None:
            return None

        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _extract_segments(self, item: Any) -> list[TranscriptionSegment]:
        if not isinstance(item, dict):
            return []

        candidate_keys = ("sentence_info", "segments")
        for key in candidate_keys:
            raw_segments = item.get(key)
            if not isinstance(raw_segments, list):
                continue

            segments: list[TranscriptionSegment] = []
            for segment in raw_segments:
                if not isinstance(segment, dict):
                    continue

                text = str(segment.get("text", "")).strip()
                if not text:
                    continue

                start = self._coerce_float(
                    segment.get("start", segment.get("start_ms"))
                )
                end = self._coerce_float(segment.get("end", segment.get("end_ms")))
                segments.append(
                    TranscriptionSegment(
                        start=start,
                        end=end,
                        text=text,
                    )
                )

            if segments:
                return segments

        return []

    def _extract_text(self, item: Any) -> str:
        if isinstance(item, str):
            return item.strip()

        if isinstance(item, dict):
            for key in ("text", "value", "preds"):
                value = item.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

            for key in ("sentence_info", "segments"):
                nested = item.get(key)
                if isinstance(nested, list):
                    parts: list[str] = []
                    for segment in nested:
                        segment_text = self._extract_text(segment)
                        if segment_text:
                            parts.append(segment_text)
                    nested_text = "".join(parts)
                    if nested_text:
                        return nested_text

        if isinstance(item, list):
            return "".join(self._extract_text(part) for part in item)

        return ""

    def _normalize_items(self, raw_result: Any) -> list[Any]:
        if raw_result is None:
            return []
        if isinstance(raw_result, list):
            return raw_result
        if isinstance(raw_result, tuple):
            return list(raw_result)
        return [raw_result]

    def transcribe(self, audio_path: str) -> TranscriptionResult:
        raw_result = self._generate(audio_path)
        items = self._normalize_items(raw_result)

        text_parts: list[str] = []
        result_segments: list[TranscriptionSegment] = []

        for item in items:
            text = self._extract_text(item)
            if text:
                text_parts.append(text)

            segments = self._extract_segments(item)
            if segments:
                result_segments.extend(segments)

        return TranscriptionResult(
            text="".join(text_parts).strip(),
            backend=self.backend_name,
            model=self.model_name,
            segments=result_segments,
        )
