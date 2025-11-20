# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : downloader.py
# @Desc     : 抖音下载器模块

import re
import os
import json
import asyncio
import aiohttp
import traceback
import pillow_heif

from PIL import Image
from loguru import logger
from pathlib import Path
from typing import Dict, Any, Tuple, List, Optional

from src.server.json_manager import DataManager
from src.server.settings import (
    settings,
)

# --- 辅助函数 ---


def _extract_douyin_code_regex(text: str) -> Optional[str]:
    """从文本中提取抖音分享码"""
    pattern = r"v\.douyin\.com/([a-zA-Z0-9]+)"
    match = re.search(pattern, text)
    if match:
        return match.group(1)
    else:
        return None


def _get_safe_filename(text: str, max_length: int = 60) -> str:
    """清理字符串，使其可以作为安全的文件名"""
    if not text:
        return "Untitled"
    text = re.sub(r'[\\/*?:"<>|]', "_", text).strip()
    return text.strip().strip(".")[:max_length]


def heic_to_jpg(img_path: Path):
    """将 heic 格式图片转换为 jpg 并删除原文件"""
    if not img_path.exists() or img_path.suffix.lower() != ".heic":
        return
    try:
        save_dir = img_path.parent
        name = img_path.stem
        heif_file = pillow_heif.read_heif(img_path)
        image = Image.frombytes(heif_file.mode, heif_file.size, heif_file.data, "raw")
        jpg_path = save_dir / f"{name}.jpg"
        image.save(jpg_path, "JPEG", quality=95)
        img_path.unlink()
        logger.info(f"已将 {img_path.name} 转换为 {jpg_path.name}")
    except Exception as e:
        logger.error(f"转换 HEIC 失败: {img_path.name}, 错误: {e}")


# --- 主下载器类 ---
class DouyinDownloader:
    def __init__(
        self,
        api_key: str,
        session: aiohttp.ClientSession,
        data_manager: DataManager,
    ):
        if not api_key.startswith("Bearer "):
            api_key = f"Bearer {api_key}"
        self._api_key = api_key
        self._session = session
        self._headers = {"accept": "application/json", "Authorization": self._api_key}
        self.data_manager = data_manager

    def _parse_input(self, text: str) -> Tuple[str, dict, str]:
        """
        统一解析输入文本。
        解析失败直接抛出异常，避免上层进行 None 检查。
        """
        text = text.strip()

        # 模式1: 纯数字 ID
        if re.fullmatch(r"\d{18,20}", text):
            return settings.id_api_url, {"aweme_id": text}, text

        # 模式2: 链接/文本 (尝试提取短码)
        short_code = _extract_douyin_code_regex(text)
        if short_code:
            return settings.url_api_url, {"share_url": text}, short_code

        # 失败直接抛出，由 download 统一捕获
        raise ValueError(f"无法解析输入文本，请检查格式: {text}")

    async def _fetch_aweme_data(
        self, api_url: str, params: dict, cache_key: str
    ) -> Dict[str, Any]:
        """简化后的数据获取方法：只负责 读缓存 OR 请求 API"""
        # 1. 查缓存
        json_path = await asyncio.to_thread(self.data_manager.get_data_path, cache_key)
        if json_path and json_path.exists():
            logger.info(f"使用本地分级 JSON 缓存: {json_path}")
            with json_path.open("r", encoding="utf-8") as f:
                return json.load(f)

        # 2. 请求 API
        logger.info(f"本地缓存未命中，正在从 API 获取 '{cache_key}' 的数据...")
        try:
            async with self._session.get(
                api_url, params=params, headers=self._headers, timeout=60
            ) as response:
                response.raise_for_status()
                data = await response.json()

                # 简单校验
                if data.get("code") == 200 or data.get("status_code") == 0:
                    # 3. 存缓存
                    if data.get("data"):
                        await asyncio.to_thread(
                            self.data_manager.save_new_data, cache_key, data
                        )
                    return data

                raise ValueError(f"API Error: {data.get('message')}")

        except Exception as e:
            logger.error(f"数据获取失败: {e}")
            raise

    def _extract_metadata(self, aweme_detail: Dict[str, Any]) -> Tuple[str, str]:
        author_info = aweme_detail.get("author", {})
        uid = author_info.get("uid", "UnknownUserID")
        nickname = author_info.get("nickname", "UnknownAuthor")
        author_name = settings.uid_to_name_map.get(uid, nickname)
        desc = aweme_detail.get("desc") or aweme_detail.get("aweme_id", "untitled")
        return author_name, desc

    async def _download_with_retry(self, url_list: List[str], save_path: Path):
        """尝试从 URL 列表中下载文件，直到成功或所有链接都失败"""
        if save_path.exists():
            logger.info(f"文件已存在，跳过下载: {save_path.name}")
            # 检查是否遗留未转换的 heic
            if (
                save_path.suffix.lower() == ".heic"
                and not Path(save_path.with_suffix(".jpg")).exists()
            ):
                logger.info(
                    f"发现残留的.heic记录但文件不存在，尝试重新下载: {save_path.name}"
                )
                pass
            else:
                return

        if not url_list:
            raise ValueError(f"没有提供可下载的 URL: {save_path.name}")

        for i, url in enumerate(url_list):
            try:
                logger.info(
                    f"正在尝试下载链接 #{i + 1}/{len(url_list)}: {save_path.name}"
                )
                await self._download_file(url, save_path)
                return
            except Exception as e:
                logger.warning(f"下载链接 #{i + 1} 失败 (URL: {url}). 错误: {e}")

        logger.error(f"所有下载链接均失败: {save_path.name}")
        raise ConnectionError(f"无法从任何可用链接下载文件: {save_path.name}")

    async def _download_file(self, url: str, save_path: Path):
        """下载单个文件"""
        try:
            async with self._session.get(url, timeout=300) as response:
                response.raise_for_status()
                save_path.parent.mkdir(parents=True, exist_ok=True)
                with save_path.open("wb") as f:
                    f.write(await response.read())
                logger.info(f"文件成功下载至: {save_path}")

                if save_path.suffix.lower() == ".heic":
                    heic_to_jpg(save_path)
        except Exception as e:
            logger.error(f"下载失败 (URL: {url}): {e}")
            if save_path.exists():
                save_path.unlink()
            raise

    async def _batch_download(
        self, tasks_data: List[Tuple[List[str], Path]]
    ) -> List[Path]:
        """
        通用并发下载执行器
        Args:
            tasks_data: List of (url_list, save_path)
        Returns:
            List of saved paths (including those successfully downloaded or already existing)
        """
        if not tasks_data:
            return []

        tasks = []
        downloaded_paths = []

        for url_list, save_path in tasks_data:
            # 记录预期路径
            downloaded_paths.append(save_path)
            # 创建任务
            tasks.append(self._download_with_retry(url_list, save_path))

        # 并发执行
        if tasks:
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for save_path, result in zip(downloaded_paths, results):
                if isinstance(result, Exception):
                    logger.error(f"下载失败: {save_path.name}, error={result}")

        # 只返回实际存在的文件
        return [p for p in downloaded_paths if p.exists()]

    # --- 核心修改：所有 _process_* 方法现在都返回 List[Path] ---
    async def _process_single_video(self, aweme_detail: Dict[str, Any]) -> List[Path]:
        """处理类型 4: 单视频"""
        author_name, desc = self._extract_metadata(aweme_detail)

        # 获取 URL
        play_addr = aweme_detail.get("video", {}).get("play_addr", {})
        url_list = play_addr.get("url_list")
        if not url_list:
            raise ValueError("未找到视频播放地址")

        # 构建路径
        filename = f"{_get_safe_filename(desc)}.mp4"
        save_path = Path(settings.video_dir) / author_name / filename

        # 委托给通用下载器
        return await self._batch_download([(url_list, save_path)])

    # --- 3. 合并后的图集/混合处理 (The Unifier) ---
    async def _process_gallery(
        self, aweme_detail: Dict[str, Any], is_mixed: bool = False
    ) -> List[Path]:
        """
        统一处理类型 2 (纯图文) 和 42 (混合媒体)
        本质上都是遍历 images 列表，只是混合模式下需要判断每个 item 是视频还是图片。
        """
        author_name, desc = self._extract_metadata(aweme_detail)
        media_list = aweme_detail.get("images")
        if not media_list:
            raise ValueError("未找到媒体列表 (images)")

        # 确定保存目录 (混合放 video_dir，纯图放 image_dir，或者你可以统一)
        base_root = settings.video_dir if is_mixed else settings.image_dir
        folder_name = _get_safe_filename(desc)
        save_dir = Path(base_root) / author_name / folder_name

        # 构建下载任务列表
        download_tasks = []

        for i, item in enumerate(media_list):
            # 尝试提取视频 (混合模式特有)
            video_item = item.get("video", {})
            video_urls = video_item.get("play_addr_h264", {}).get(
                "url_list"
            ) or video_item.get("play_addr", {}).get("url_list")

            if is_mixed and video_urls:
                # 是视频
                file_name = f"video_{i + 1:02d}.mp4"
                download_tasks.append((video_urls, save_dir / file_name))
            else:
                # 是图片 (兜底)
                img_urls = item.get("url_list")
                if img_urls:
                    file_name = f"image_{i + 1:02d}.heic"
                    download_tasks.append((img_urls, save_dir / file_name))

        logger.info(
            f"正在处理{'混合' if is_mixed else '图文'}作品: {folder_name}, 共 {len(download_tasks)} 个文件"
        )

        # 委托执行
        return await self._batch_download(download_tasks)

    async def download(self, text: str) -> List[Path]:
        """
        根据作品 ID/链接 下载的主入口函数 (Refactored)
        """
        try:
            # 1. 解析输入：获取请求所需的全部元数据
            api_url, params, cache_key = self._parse_input(text)

            # 2. 获取数据：(网络请求 或 读取缓存)
            data = await self._fetch_aweme_data(api_url, params, cache_key)
            aweme_detail = data.get("data", {}).get("aweme_detail")
            if not aweme_detail:
                logger.warning(f"未获取到作品详情数据: {cache_key}")
                return []

            # 3. 路由分发：决定使用哪个处理函数
            media_type = aweme_detail.get("media_type")
            has_images = bool(aweme_detail.get("images"))
            has_video = bool(aweme_detail.get("video"))

            is_images = media_type in [2, 68] or (has_images and not has_video)
            is_mixed = media_type == 42 or (has_images and has_video)
            is_video = media_type == 4 or (has_video and not has_images)
            logger.info(f"处理作品: {cache_key} | 类型: {media_type}")

            # 优先匹配明确的类型，Fallback 逻辑放在最后
            if is_images:
                return await self._process_gallery(aweme_detail, is_mixed=False)
            elif is_mixed:
                return await self._process_gallery(aweme_detail, is_mixed=True)
            elif is_video:
                return await self._process_single_video(aweme_detail)
            else:
                logger.error(f"不支持的媒体类型或数据结构未知: {media_type}")
                return []

        except Exception as e:
            # 依然捕获顶层异常，防止单个任务崩溃影响整个队列（如果是批量下载的话）
            logger.error(f"下载任务异常 [{text}]: {e}")
            logger.debug(traceback.format_exc())
            return []


if __name__ == "__main__":
    # 本地测试代码
    async def main():
        TIKHUB_AUTH_KEY = os.getenv("DY_TIKHUB_AUTH_KEY", "你的Key")
        async with aiohttp.ClientSession() as session:
            downloader = DouyinDownloader(api_key=TIKHUB_AUTH_KEY, session=session)
            # 测试链接
            await downloader.download("https://v.douyin.com/xxxx/")

    asyncio.run(main())
