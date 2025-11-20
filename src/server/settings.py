# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : settings.py
# @Desc     : 全局配置（环境变量、路径、外部服务 URL、ASR 配置）

from pathlib import Path
from typing import Dict

from pydantic_settings import BaseSettings, SettingsConfigDict


# 项目根目录，用于定位 .env
CURRENT_DIR = Path(__file__).resolve().parent  # src/server
PROJECT_ROOT = CURRENT_DIR.parent.parent  # 项目根目录


class AppSettings(BaseSettings):
    """
    全局配置，统一从环境变量 / .env 读取。
    """

    # --- 存储路径 ---
    json_dir: Path = Path("data/json")
    video_dir: Path = Path("data/videos")
    image_dir: Path = Path("data/images")

    # --- 抖音解析 API ---
    id_api_url: str = "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_one_video"
    url_api_url: str = (
        "https://api.tikhub.io/api/v1/douyin/app/v3/fetch_one_video_by_share_url"
    )

    # --- ASR 配置 ---
    asr_model: str = "medium"  # tiny/base/small/medium/large
    asr_device: str = "cpu"
    asr_compute_type: str = "int8"  # float16/int8
    asr_cpu_threads: int = 4

    # --- 鉴权与密钥 ---
    tikhub_auth_key: str = "Not set! Change me!"  # TikHub API Key
    dy_api_key: str = "Not set! Change me!"  # 自定义抖音 API Key
    api_key_header_name: str = "X-API-KEY"  # 自定义 API

    # --- DB 配置 ---
    DB_USER: str = "myuser"
    DB_PASSWORD: str = "Not set! Change me!"
    DB_HOST: str = "localhost"
    DB_PORT: str = "5432"
    DB_NAME: str = "app_data"

    # --- 用户 ID 映射配置 ---
    # 格式: {"uid_string": "Folder_Name"}
    uid_to_name_map: Dict[str, str] = {}

    # --- 任务配置 ---
    JOB_RETENTION_SECONDS: int = 86400  # 任务保留时间，单位秒，默认1天

    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    def model_post_init(self, __context):
        self.json_dir.mkdir(parents=True, exist_ok=True)
        self.video_dir.mkdir(parents=True, exist_ok=True)
        self.image_dir.mkdir(parents=True, exist_ok=True)


settings = AppSettings()
