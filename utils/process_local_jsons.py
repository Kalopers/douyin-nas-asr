import json
from loguru import logger
from pathlib import Path
import shutil

from src.server.settings import settings

# --- 配置 ---
# 设置你的JSON数据根目录
# 脚本会读取此目录下的文件，并将它们移动到此目录下的子文件夹中
JSON_DIR = "/smb/douyin/json_files"


def run_migration():
    """
    执行从扁平化JSON存储到分级索引存储的迁移。
    """
    source_dir = Path(JSON_DIR)
    if not source_dir.is_dir():
        logger.error(f"错误：目录 '{JSON_DIR}' 不存在。请检查路径配置。")
        return

    logger.info("=" * 50)
    logger.info("JSON 文件结构迁移脚本")
    logger.info(f"源目录: {source_dir.resolve()}")
    logger.info("此脚本将会移动目录下的 .json 文件到新的分级子目录中，")
    logger.info("并创建一个 index.json 文件。")
    logger.info("强烈建议在运行前备份您的数据！")
    logger.info("=" * 50)

    # 用户确认
    confirm = input("您确定要继续吗？ (y/n): ")
    if confirm.lower() != "y":
        logger.info("操作已取消。")
        return

    # 1. 查找所有位于根目录下的 .json 文件
    # 我们只处理顶级目录的文件，忽略任何已存在的子目录和 index.json
    files_to_migrate = [
        p for p in source_dir.glob("*.json") if p.is_file() and p.name != "index.json"
    ]

    if not files_to_migrate:
        logger.info("在根目录下未找到需要迁移的 JSON 文件。")
        return

    logger.info(f"发现 {len(files_to_migrate)} 个待迁移的 JSON 文件。")

    new_index = {}
    success_count = 0
    fail_count = 0

    # 2. 遍历并处理每个文件
    for file_path in files_to_migrate:
        key = file_path.stem  # 文件名（不含.json），作为索引的 key
        logger.info(f"--- 正在处理: {file_path.name} ---")

        try:
            # 2a. 读取 JSON 内容
            with file_path.open("r", encoding="utf-8") as f:
                content = json.load(f)

            # 2b. 提取分级ID (aweme_id)
            # 默认使用 aweme_id 作为分级目录名
            aweme_detail = content.get("data", {}).get("aweme_detail", {})
            if not aweme_detail:
                raise ValueError("JSON 文件中缺少 'data.aweme_detail' 结构。")

            # --- ID选择点 ---
            # 默认使用作品ID 'aweme_id'。
            # 如果您想按作者ID 'uid' 分级，请将下面这行取消注释，并注释掉下一行。
            directory_id = aweme_detail.get("author", {}).get("uid")
            # directory_id = aweme_detail.get("aweme_id")

            if not directory_id:
                raise ValueError(
                    "未能从 aweme_detail 中提取到有效的 'aweme_id' 或 'uid'。"
                )

            directory_id = str(directory_id)  # 确保是字符串
            name = settings.uid_to_name_map.get(directory_id, None)
            if name:
                logger.info(f"为 key='{key}' 使用映射名称: {name}")
                directory_id = name
            logger.info(f"提取到 Key: '{key}', 分级ID: '{directory_id}'")

            # 2c. 创建目标目录并移动文件
            target_dir = source_dir / directory_id
            target_dir.mkdir(parents=True, exist_ok=True)

            new_file_path = target_dir / file_path.name

            # 使用 shutil.move 更稳健，可以处理跨设备等情况
            shutil.move(str(file_path), str(new_file_path))
            logger.info(f"文件已移动到 -> {new_file_path}")

            # 2d. 更新索引字典
            new_index[key] = directory_id
            success_count += 1

        except json.JSONDecodeError:
            logger.error(f"文件 '{file_path.name}' 格式错误，无法解析。已跳过。")
            fail_count += 1
        except (ValueError, KeyError) as e:
            logger.error(f"处理文件 '{file_path.name}' 失败: {e}。已跳过。")
            fail_count += 1
        except Exception as e:
            logger.error(f"处理文件 '{file_path.name}' 时发生未知错误: {e}。已跳过。")
            fail_count += 1

    # 3. 保存新的 index.json 文件
    if new_index:
        index_path = source_dir / "index.json"
        logger.info(f"正在将 {len(new_index)} 条记录写入到 {index_path}...")
        try:
            with index_path.open("w", encoding="utf-8") as f:
                json.dump(new_index, f, ensure_ascii=False, indent=4)
            logger.info("index.json 文件创建成功。")
        except Exception as e:
            logger.error(f"写入 index.json 文件时失败: {e}")
            fail_count += success_count  # 如果索引写入失败，所有移动都算失败
            success_count = 0

    # 4. 打印最终报告
    logger.info("=" * 50)
    logger.info("迁移完成！")
    logger.info(f"总处理文件数: {len(files_to_migrate)}")
    logger.info(f"成功迁移: {success_count}")
    logger.info(f"失败跳过: {fail_count}")
    logger.info("=" * 50)


if __name__ == "__main__":
    run_migration()
