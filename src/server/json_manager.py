# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : json_manager.py
# @Desc     : 管理JSON数据的存储，并使用PostgreSQL数据库来高效、安全地管理索引。

import json
from loguru import logger
from pathlib import Path
from typing import Dict, Any, Optional

from sqlalchemy import create_engine, text, MetaData, Table, Column, String
from sqlalchemy.orm import sessionmaker, scoped_session
from sqlalchemy.exc import SQLAlchemyError

from src.server.settings import settings

DATABASE_URL = f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
logger.info(f"使用的数据库连接字符串: {DATABASE_URL}")


# --- 类定义区 ---
class DataManager:
    """
    管理JSON数据的存储，并使用PostgreSQL数据库来高效、安全地管理索引。
    注意：此类目前是同步的 (Synchronous)，在 Asyncio 环境中使用时可能会阻塞事件循环。
    如果数据库响应慢，建议在调用层使用 run_in_threadpool。
    """

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            self.engine = create_engine(
                DATABASE_URL,
                pool_pre_ping=True,  # 自动检测断开的连接并重连
                pool_recycle=3600,  # 1小时回收连接
                pool_size=10,  # 连接池大小
                max_overflow=20,  # 溢出连接数
            )
            # 使用 scoped_session 在多线程环境下更安全
            self.Session = scoped_session(sessionmaker(bind=self.engine))

            self._create_table_if_not_exists()
            logger.info("DataManager 初始化成功，已连接到PostgreSQL数据库。")
        except SQLAlchemyError as e:
            logger.error(f"数据库连接失败: {e}")
            # 这里不 raise，允许程序在无数据库情况下启动（虽然功能会受限），或者根据需求 raise
            raise

    def _create_table_if_not_exists(self):
        """如果索引表不存在，则创建它。"""
        try:
            metadata = MetaData()
            Table(
                "video_index",
                metadata,
                Column("key", String(255), primary_key=True),  # 建议指定长度，利于索引
                Column("file_id", String(255), nullable=False),
            )
            metadata.create_all(self.engine)
            logger.info("表 'video_index' 检查完毕。")
        except Exception as e:
            logger.error(f"创建表失败: {e}")
            raise

    def get_data_path(self, key: str) -> Optional[Path]:
        """
        根据 key 从数据库检查索引，如果存在则返回完整文件路径。
        """
        session = self.Session()
        try:
            stmt = text("SELECT file_id FROM video_index WHERE key = :key")
            result = session.execute(stmt, {"key": key}).scalar_one_or_none()

            if result:
                # 核心修复：直接使用数据库中存储的 file_id (即目录名)。
                # 不要在读取时再次查 UID_TO_NAME_MAP，否则如果 Mapping 更新了，
                # 会导致程序去错误的（新的）文件夹找旧文件，引发 FileNotFoundError。
                stored_folder_name = result

                file_path = self.base_dir / stored_folder_name / f"{key}.json"

                # 可选：增加一层物理文件检查，确保文件真的还在
                if file_path.exists():
                    return file_path
                else:
                    logger.warning(
                        f"数据库索引存在 key='{key}'，但物理文件缺失: {file_path}"
                    )
                    return None
            return None
        except SQLAlchemyError as e:
            logger.error(f"查询索引失败: {e}")
            return None
        finally:
            session.close()  # 务必关闭 session

    def save_new_data(self, key: str, json_data: Dict[str, Any]) -> Path:
        """保存JSON文件，并使用原子性的 "UPSERT" 操作更新数据库索引。"""

        # 1. 提取 ID
        try:
            aweme_detail = json_data.get("data", {}).get("aweme_detail", {})
            author_id = aweme_detail.get("author", {}).get("uid", "")

            # 修复错误信息变量名
            if not author_id:
                # 尝试从其他字段作为 fallback，或者报错
                author_id = "unknown_author"
                logger.warning(f"数据中未找到 author uid，归档至 {author_id}")

            # 在保存阶段进行映射：将 UID 转为 Name (如果存在)
            # 这是确定物理存储路径的唯一时刻
            folder_name = str(author_id)
            if folder_name in settings.uid_to_name_map:
                folder_name = settings.uid_to_name_map[folder_name]

        except Exception as e:
            raise ValueError(f"处理 JSON 数据提取 ID 时出错: {e}")

        # 2. 保存文件 (物理存储)
        target_dir = self.base_dir / folder_name
        target_dir.mkdir(parents=True, exist_ok=True)
        file_path = target_dir / f"{key}.json"

        try:
            with file_path.open("w", encoding="utf-8") as f:
                json.dump(json_data, f, ensure_ascii=False, indent=4)
            logger.info(f"JSON 文件已保存至: {file_path}")
        except OSError as e:
            logger.error(f"写入文件失败: {e}")
            raise

        # 3. 更新数据库 (索引)
        # PostgreSQL 专用的 UPSERT 语法
        upsert_stmt = text(
            """
            INSERT INTO video_index (key, file_id)
            VALUES (:key, :file_id)
            ON CONFLICT (key)
            DO UPDATE SET file_id = EXCLUDED.file_id;
            """
        )

        session = self.Session()
        try:
            session.execute(upsert_stmt, {"key": key, "file_id": folder_name})
            session.commit()
            logger.info(f"数据库索引已更新: key='{key}' -> folder='{folder_name}'")
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"数据库索引更新失败: {e}")
            raise
        finally:
            session.close()

        return file_path


# --- 主程序入口 (用于测试) ---
if __name__ == "__main__":
    # 1. 创建 DataManager 实例
    manager = DataManager(base_dir=settings.json_dir)

    # 2. 准备一些模拟数据
    mock_key = "73105678912345"
    mock_data = {
        "data": {
            "aweme_detail": {
                "aweme_id": mock_key,
                "desc": "这是一个测试视频",
                "author": {"uid": "10086", "nickname": "测试用户"},  # 模拟 UID
            }
        }
    }

    # 3. 保存新数据
    logger.info("--- 开始保存新数据 ---")
    try:
        saved_path = manager.save_new_data(key=mock_key, json_data=mock_data)
        logger.info(f"保存成功: {saved_path}")
    except Exception as e:
        logger.error(f"保存失败: {e}")

    # 4. 尝试获取刚刚保存的数据路径
    logger.info("--- 开始查询数据路径 ---")
    retrieved_path = manager.get_data_path(key=mock_key)
    if retrieved_path:
        logger.info(f"查询成功！获取到的路径是: {retrieved_path}")
        logger.info(f"文件是否存在: {retrieved_path.exists()}")
    else:
        logger.error(f"查询失败！未找到 key='{mock_key}' 的记录。")
