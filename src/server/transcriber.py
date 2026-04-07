# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : transcribe_cpu.py
# @Desc     : ASR 转录服务（封装 backend 抽象）

import asyncio
from pathlib import Path
from loguru import logger

from src.server.asr.base import ASREngine
from src.server.asr.factory import create_asr_engine
from src.server.asr.types import TranscriptionResult
from src.server.settings import settings


class Transcriber:
    def __init__(self, engine: ASREngine | None = None):
        self.engine = engine or create_asr_engine()
        self._semaphore = asyncio.Semaphore(settings.asr_max_concurrency)
        logger.info(
            "Transcriber ready with backend={} model={} asr_max_concurrency={}",
            self.engine.backend_name,
            self.engine.model_name,
            settings.asr_max_concurrency,
        )

    async def extract_audio(self, video_path: Path) -> Path:
        audio_path = video_path.with_suffix(".mp3")
        if audio_path.exists():
            return audio_path

        # 使用 -vn (无视频) -acodec libmp3lame -q:a 4 (VBR 质量，平衡速度和音质)
        cmd = (
            f'ffmpeg -i "{video_path}" -vn -acodec libmp3lame -q:a 4 "{audio_path}" -y'
        )
        logger.info(f"Extracting audio: {cmd}")

        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()

        if proc.returncode != 0:
            error_msg = stderr.decode()
            logger.error(f"FFmpeg error: {error_msg}")
            raise RuntimeError(f"FFmpeg failed: {error_msg}")

        return audio_path

    def _run_inference(self, audio_path: str) -> TranscriptionResult:
        """
        同步推理函数 (CPU 密集型)，将在线程池中运行。
        """
        try:
            return self.engine.transcribe(audio_path)
        except Exception as e:
            logger.error(f"Inference error while processing {audio_path}, details: {e}")
            raise e

    async def transcribe(self, file_path: Path) -> TranscriptionResult:
        """
        执行转录任务。
        如果成功返回结构化结果，如果失败抛出异常。
        """
        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        process_file = file_path
        temp_audio_created = False

        try:
            # 1. 提取音频 (如果需要)
            if file_path.suffix.lower() in [".mp4", ".mov", ".mkv", ".avi"]:
                logger.info(f"Extracting audio from {file_path.name}...")
                process_file = await self.extract_audio(file_path)
                temp_audio_created = True

            logger.info(f"Starting transcription for {process_file.name}...")

            # 2. 放入线程池运行
            async with self._semaphore:
                result = await asyncio.to_thread(self._run_inference, str(process_file))

            if not result.text:
                logger.warning(f"Transcription result is empty for {file_path.name}")
                return result

            # 3. 保存结果 (可选)
            try:
                txt_path = file_path.with_suffix(".txt")
                with open(txt_path, "w", encoding="utf-8") as f:
                    f.write(result.text)
                logger.success(f"Done. Saved result to {txt_path}")
            except Exception as write_err:
                logger.warning(
                    f"Failed to save text file, but returning result: {write_err}"
                )

            return result

        except Exception as e:
            # 记录错误并重新抛出，以便上层 API Server 可以捕获并标记为 FAILED
            logger.error(f"Transcription failed for {file_path.name}: {e}")
            raise e

        finally:
            # 4. 清理临时音频文件
            if (
                temp_audio_created
                and process_file.exists()
                and process_file != file_path
            ):
                try:
                    process_file.unlink()
                    logger.debug(f"Cleaned up temp audio: {process_file}")
                except Exception:
                    pass
