# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : settings.py
# @Desc     : 全局配置（环境变量、路径、外部服务 URL、ASR 配置）

from pathlib import Path
from typing import Dict

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录，用于定位 .env
CURRENT_DIR = Path(__file__).resolve().parent  # src/server
PROJECT_ROOT = CURRENT_DIR.parent.parent  # 项目根目录
DEFAULT_SENSEVOICE_MODEL = "iic/SenseVoiceSmall"
DEFAULT_FASTER_WHISPER_MODEL = "medium"
LEGACY_FASTER_WHISPER_MODELS = {
    "tiny",
    "tiny.en",
    "base",
    "base.en",
    "small",
    "small.en",
    "medium",
    "medium.en",
    "large",
    "large-v1",
    "large-v2",
    "large-v3",
    "distil-small.en",
    "distil-medium.en",
    "distil-large-v2",
    "distil-large-v3",
    "turbo",
}


class AppSettings(BaseSettings):
    """
    全局配置，统一从环境变量 / .env 读取。
    """

    # --- 应用监听 ---
    app_host: str = Field(
        default="0.0.0.0",
        validation_alias=AliasChoices("APP_HOST"),
    )
    app_port: int = Field(
        default=17650,
        validation_alias=AliasChoices("APP_PORT"),
    )

    # --- 存储路径 ---
    json_dir: Path = Field(
        default=Path("data/json"),
        validation_alias=AliasChoices("NAS_JSON_DIR", "JSON_DIR"),
    )
    video_dir: Path = Field(
        default=Path("data/videos"),
        validation_alias=AliasChoices("NAS_VIDEO_DIR", "VIDEO_DIR"),
    )
    image_dir: Path = Field(
        default=Path("data/images"),
        validation_alias=AliasChoices("NAS_IMAGE_DIR", "IMAGE_DIR"),
    )

    # --- 抖音解析 API ---
    id_api_url: str = "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_one_video"
    url_api_url: str = (
        "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_one_video_by_share_url"
    )

    # --- ASR 配置 ---
    asr_backend: str = Field(
        default="sensevoice",
        validation_alias=AliasChoices("ASR_BACKEND"),
    )
    asr_model: str = Field(
        default=DEFAULT_SENSEVOICE_MODEL,
        validation_alias=AliasChoices("ASR_MODEL"),
    )  # 通用 ASR 模型名，默认指向 SenseVoice
    faster_whisper_model: str = Field(
        default=DEFAULT_FASTER_WHISPER_MODEL,
        validation_alias=AliasChoices("FASTER_WHISPER_MODEL", "WHISPER_MODEL_SIZE"),
    )  # faster-whisper fallback 模型名
    asr_device: str = Field(
        default="cpu",
        validation_alias=AliasChoices("WHISPER_DEVICE", "ASR_DEVICE"),
    )
    asr_compute_type: str = Field(
        default="int8",
        validation_alias=AliasChoices(
            "WHISPER_COMPUTE_TYPE",
            "ASR_COMPUTE_TYPE",
        ),
    )  # float16/int8
    asr_cpu_threads: int = Field(
        default=4,
        validation_alias=AliasChoices("WHISPER_CPU_THREADS", "ASR_CPU_THREADS"),
    )
    asr_max_concurrency: int = Field(
        default=1,
        validation_alias=AliasChoices("ASR_MAX_CONCURRENCY"),
    )

    # --- 鉴权与密钥 ---
    tikhub_auth_key: str = Field(
        default="Not set! Change me!",
        validation_alias=AliasChoices("DY_TIKHUB_AUTH_KEY", "TIKHUB_AUTH_KEY"),
    )  # TikHub API Key
    dy_api_key: str = Field(
        default="Not set! Change me!",
        validation_alias=AliasChoices("DY_API_KEY"),
    )  # 自定义抖音 API Key
    api_key_header_name: str = Field(
        default="X-API-KEY",
        validation_alias=AliasChoices("API_KEY_HEADER_NAME"),
    )  # 自定义 API

    # --- DB 配置 ---
    DB_USER: str = Field(
        default="myuser",
        validation_alias=AliasChoices("POSTGRES_USER", "DB_USER"),
    )
    DB_PASSWORD: str = Field(
        default="Not set! Change me!",
        validation_alias=AliasChoices("POSTGRES_PASSWORD", "DB_PASSWORD"),
    )
    DB_HOST: str = Field(
        default="localhost",
        validation_alias=AliasChoices("POSTGRES_HOST", "DB_HOST"),
    )
    DB_PORT: str = Field(
        default="5432",
        validation_alias=AliasChoices("POSTGRES_PORT", "DB_PORT"),
    )
    DB_NAME: str = Field(
        default="app_data",
        validation_alias=AliasChoices("POSTGRES_DB", "DB_NAME"),
    )

    # --- 用户 ID 映射配置 ---
    # 格式: {"uid_string": "Folder_Name"}
    uid_to_name_map: Dict[str, str] = {}

    # --- 任务配置 ---
    JOB_RETENTION_SECONDS: int = 86400  # 任务保留时间，单位秒，默认1天
    worker_poll_interval_seconds: float = Field(
        default=2.0,
        validation_alias=AliasChoices(
            "WORKER_POLL_INTERVAL_SECONDS",
        ),
    )
    worker_concurrency: int = Field(
        default=1,
        validation_alias=AliasChoices("WORKER_CONCURRENCY"),
    )

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context):
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)

    @property
    def resolved_sensevoice_model(self) -> str:
        if self.asr_model in LEGACY_FASTER_WHISPER_MODELS:
            return DEFAULT_SENSEVOICE_MODEL
        return self.asr_model

    @property
    def resolved_faster_whisper_model(self) -> str:
        if (
            self.faster_whisper_model == DEFAULT_FASTER_WHISPER_MODEL
            and self.asr_model in LEGACY_FASTER_WHISPER_MODELS
        ):
            return self.asr_model
        return self.faster_whisper_model


settings = AppSettings()
