# -*- coding: utf-8 -*-
# @Date     : 2025/11/20
# @Author   : Kaloper (ausitm2333@gmail.com)
# @File     : migrate.py
# @Desc     :

import json
from loguru import logger
import os
import dotenv
from pathlib import Path
from time import time

from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import SQLAlchemyError

from src.server.settings import settings

# --- 2. 配置区 ---
# 请务必修改这里，指向您存放JSON文件的根目录
JSON_ROOT_DIR = settings.json_dir.resolve()

dotenv.load_dotenv()  # 加载环境变量

DB_USER = os.getenv("DB_USER", "myuser")
DB_PASSWORD = os.getenv("DB_PASSWORD", "mysecretpassword")
DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = os.getenv("DB_PORT", "5432")

DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:{DB_PORT}/app_data"
logger.info(f"使用的数据库连接字符串: {DATABASE_URL}")

# 批量处理的大小，可以根据您的内存和文件数量调整
BATCH_SIZE = 500


# --- 3. 核心功能 ---
def get_db_session():
    """创建并返回一个数据库会话。"""
    try:
        engine = create_engine(DATABASE_URL)
        Session = sessionmaker(bind=engine)
        # 简单的连接测试
        with engine.connect() as connection:
            logger.info("数据库连接成功！")
        return Session()
    except SQLAlchemyError as e:
        logger.error(
            f"数据库连接失败，请检查DATABASE_URL配置和Docker容器状态。错误: {e}"
        )
        return None


def insert_batch(session, data_batch: list):
    """将一个批次的数据插入数据库。"""
    if not data_batch:
        return 0

    try:
        # 使用 ON CONFLICT (key) DO NOTHING 确保脚本可重复运行
        # 如果key已存在，则什么也不做。
        stmt = text(
            """
            INSERT INTO video_index (key, file_id)
            VALUES (:key, :file_id)
            ON CONFLICT (key) DO NOTHING
        """
        )

        result = session.execute(stmt, data_batch)
        session.commit()

        inserted_count = result.rowcount
        logger.info(
            f"成功提交一个批次，插入了 {inserted_count} 条新记录 (共 {len(data_batch)} 条)。"
        )
        return inserted_count
    except SQLAlchemyError as e:
        logger.error(f"批量插入时发生数据库错误: {e}")
        session.rollback()
        return 0
    except Exception as e:
        logger.error(f"批量插入时发生未知错误: {e}")
        session.rollback()
        return 0


def migrate_jsons_to_db(directory: str):
    """
    扫描指定目录下的所有JSON文件，解析并批量存入数据库。
    """
    root_path = Path(directory)
    if not root_path.is_dir():
        logger.error(f"错误：目录 '{directory}' 不存在或不是一个有效的目录。")
        return

    session = get_db_session()
    if not session:
        return

    logger.info(f"开始扫描目录: {root_path.resolve()}")

    # 使用 rglob 递归查找所有 .json 文件
    json_files = list(root_path.rglob("*.json"))
    total_files = len(json_files)
    logger.info(f"共找到 {total_files} 个JSON文件。开始处理...")

    data_to_insert = []
    total_processed = 0
    total_inserted = 0
    total_errors = 0
    start_time = time()

    for file_path in json_files:
        total_processed += 1

        # 打印进度
        if total_processed % 100 == 0 or total_processed == total_files:
            logger.info(f"处理进度: {total_processed}/{total_files}...")

        try:
            # 从文件路径中提取 key。假设文件名为 key.json
            key = file_path.stem

            # 从文件内容中解析出 file_id
            with file_path.open("r", encoding="utf-8") as f:
                content = json.load(f)
                author_id = (
                    content.get("data", {})
                    .get("aweme_detail", {})
                    .get("author", {})
                    .get("uid", "")
                )

            if not author_id:
                logger.warning(f"文件 '{file_path}' 中未找到 'uid'，已跳过。")
                total_errors += 1
                continue

            if author_id in settings.uid_to_name_map:
                author_id = settings.uid_to_name_map[author_id]

            data_to_insert.append({"key": key, "file_id": str(author_id)})

            # 如果达到批次大小，则提交到数据库
            if len(data_to_insert) >= BATCH_SIZE:
                total_inserted += insert_batch(session, data_to_insert)
                data_to_insert = []  # 清空批次

        except json.JSONDecodeError:
            logger.warning(f"文件 '{file_path}' 不是有效的JSON格式，已跳过。")
            total_errors += 1
        except Exception as e:
            logger.error(f"处理文件 '{file_path}' 时发生未知错误: {e}")
            total_errors += 1

    # 处理最后一批不足 BATCH_SIZE 的数据
    if data_to_insert:
        total_inserted += insert_batch(session, data_to_insert)

    session.close()

    end_time = time()
    duration = end_time - start_time

    logger.info("--- 迁移完成 ---")
    logger.info(f"总耗时: {duration:.2f} 秒")
    logger.info(f"共处理文件: {total_processed}")
    logger.info(f"成功插入新记录: {total_inserted}")
    logger.info(f"发现错误/跳过: {total_errors}")


if __name__ == "__main__":
    migrate_jsons_to_db(JSON_ROOT_DIR)
