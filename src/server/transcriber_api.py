import os
import aiohttp
import asyncio
from pathlib import Path
from loguru import logger
from src.server.settings import ASR_API_BASE, ASR_API_KEY, ASR_MODEL


class Transcriber:
    def __init__(self):
        self.api_base = ASR_API_BASE
        self.api_key = ASR_API_KEY
        self.model = ASR_MODEL

    async def extract_audio(self, video_path: Path) -> Path:
        # 使用 ffmpeg 提取音频
        audio_path = video_path.with_suffix(".mp3")
        if audio_path.exists():
            return audio_path

        # -vn: no video, -acodec libmp3lame: mp3 codec, -q:a 4: quality level 4 (good)
        cmd = (
            f'ffmpeg -i "{video_path}" -vn -acodec libmp3lame -q:a 4 "{audio_path}" -y'
        )
        logger.info(f"Extracting audio: {cmd}")
        proc = await asyncio.create_subprocess_shell(
            cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            raise RuntimeError(f"Failed to extract audio from {video_path}")
        return audio_path

    async def transcribe(self, file_path: Path) -> str:
        if not self.api_key or self.api_key == "your_openai_api_key":
            logger.warning("ASR API Key not set, skipping transcription.")
            return "ASR API Key not configured."

        file_to_upload = file_path
        # 如果是视频，先提取音频
        if file_path.suffix.lower() in [".mp4", ".mov", ".mkv"]:
            try:
                audio_path = await self.extract_audio(file_path)
                file_to_upload = audio_path
            except Exception as e:
                logger.error(f"Audio extraction failed: {e}")
                return f"Audio extraction failed: {e}"

        url = f"{self.api_base}/audio/transcriptions"
        headers = {"Authorization": f"Bearer {self.api_key}"}

        # 准备 multipart/form-data
        data = aiohttp.FormData()
        data.add_field("file", open(file_to_upload, "rb"))
        data.add_field("model", self.model)

        try:
            logger.info(f"Sending {file_to_upload.name} to ASR API...")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, headers=headers, data=data) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        logger.error(f"ASR API Error: {error_text}")
                        return f"ASR Error: {response.status} - {error_text}"

                    result = await response.json()
                    text = result.get("text", "")

                    # 保存转录文本
                    txt_path = file_path.with_suffix(".txt")
                    with open(txt_path, "w", encoding="utf-8") as f:
                        f.write(text)

                    logger.info(f"Transcription saved to {txt_path}")
                    return text
        except Exception as e:
            logger.error(f"Transcription failed: {e}")
            return f"Transcription failed: {e}"
        finally:
            # 清理临时音频文件
            if file_to_upload != file_path and file_to_upload.exists():
                try:
                    file_to_upload.unlink()
                except Exception as e:
                    logger.warning(f"Failed to delete temp file {file_to_upload}: {e}")
