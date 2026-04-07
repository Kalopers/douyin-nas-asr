# -*- coding: utf-8 -*-
# @Date     : 2026/04/08
# @Author   : Codex
# @File     : job_store.py
# @Desc     : 任务状态持久化存储（PostgreSQL）

import time
from dataclasses import dataclass
from typing import Any, Optional

from loguru import logger
from sqlalchemy import JSON, Column, Float, MetaData, String, Table, Text, create_engine
from sqlalchemy import inspect, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import scoped_session, sessionmaker

from src.server.models import (
    ErrorCode,
    ErrorInfo,
    JobInfo,
    MessageCode,
    TaskKind,
    TaskStatus,
)
from src.server.settings import settings


DATABASE_URL = (
    f"postgresql://{settings.DB_USER}:{settings.DB_PASSWORD}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)


@dataclass(frozen=True)
class QueuedJob:
    job: JobInfo
    task_kind: TaskKind


class JobStore:
    """
    任务状态持久化仓储。
    - jobs 表是任务状态真值
    - 内存 TaskManager 仅保留运行句柄
    """

    def __init__(self):
        self.engine = create_engine(
            DATABASE_URL,
            pool_pre_ping=True,
            pool_recycle=3600,
            pool_size=10,
            max_overflow=20,
        )
        self.Session = scoped_session(sessionmaker(bind=self.engine))
        self.metadata = MetaData()
        self.jobs_table = Table(
            "jobs",
            self.metadata,
            Column("task_id", String(64), primary_key=True),
            Column("task_type", String(64), nullable=True),
            Column("status", String(32), nullable=False),
            Column("video_id", String(255), nullable=False),
            Column("message_code", String(64), nullable=True),
            Column("message", Text, nullable=True),
            Column("download_urls", JSON, nullable=True),
            Column("result", JSON, nullable=True),
            Column("error_code", String(64), nullable=True),
            Column("error_message", Text, nullable=True),
            Column("error_detail", Text, nullable=True),
            Column("created_at", Float, nullable=False),
            Column("updated_at", Float, nullable=False),
        )
        self._create_table_if_not_exists()

    def _create_table_if_not_exists(self) -> None:
        try:
            self.metadata.create_all(self.engine)
            self._migrate_table_if_needed()
            logger.info("表 'jobs' 检查完毕。")
        except Exception as e:
            logger.error(f"创建 jobs 表失败: {e}")
            raise

    def _migrate_table_if_needed(self) -> None:
        inspector = inspect(self.engine)
        columns = {column["name"] for column in inspector.get_columns("jobs")}
        if "task_type" in columns:
            return

        with self.engine.begin() as connection:
            connection.execute(text("ALTER TABLE jobs ADD COLUMN task_type VARCHAR(64)"))
        logger.info("jobs 表已补充 task_type 列。")

    def _serialize_job(self, job: JobInfo, task_kind: TaskKind) -> dict[str, Any]:
        error = job.error
        return {
            "task_id": job.task_id,
            "task_type": task_kind.value,
            "status": job.status.value,
            "video_id": job.video_id,
            "message_code": job.message_code.value if job.message_code else None,
            "message": job.message,
            "download_urls": job.download_urls,
            "result": job.result,
            "error_code": error.code.value if error else None,
            "error_message": error.message if error else None,
            "error_detail": error.detail if error else None,
            "created_at": job.created_at,
            "updated_at": time.time(),
        }

    def enqueue_job(self, job: JobInfo, task_kind: TaskKind) -> None:
        self.upsert_job(job, task_kind)

    def upsert_job(self, job: JobInfo, task_kind: TaskKind) -> None:
        payload = self._serialize_job(job, task_kind)
        stmt = insert(self.jobs_table).values(**payload)
        stmt = stmt.on_conflict_do_update(
            index_elements=[self.jobs_table.c.task_id],
            set_={
                "task_type": payload["task_type"],
                "status": payload["status"],
                "video_id": payload["video_id"],
                "message_code": payload["message_code"],
                "message": payload["message"],
                "download_urls": payload["download_urls"],
                "result": payload["result"],
                "error_code": payload["error_code"],
                "error_message": payload["error_message"],
                "error_detail": payload["error_detail"],
                "updated_at": payload["updated_at"],
            },
        )

        session = self.Session()
        try:
            session.execute(stmt)
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"持久化任务状态失败: {job.task_id}, error={e}")
            raise
        finally:
            session.close()

    def claim_next_pending_job(self) -> Optional[QueuedJob]:
        """
        使用 PostgreSQL 行锁原子地领取一个 pending 任务。
        不依赖 Redis，足够支撑当前的单 worker / 小规模场景。
        """
        session = self.Session()
        try:
            now = time.time()
            stmt = text(
                """
                WITH next_job AS (
                    SELECT task_id
                    FROM jobs
                    WHERE status = :pending
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE jobs
                SET status = :processing,
                    updated_at = :updated_at
                WHERE task_id IN (SELECT task_id FROM next_job)
                RETURNING
                    task_id,
                    task_type,
                    status,
                    video_id,
                    message_code,
                    message,
                    download_urls,
                    result,
                    error_code,
                    error_message,
                    error_detail,
                    created_at,
                    updated_at
                """
            )
            row = session.execute(
                stmt,
                {
                    "pending": TaskStatus.PENDING.value,
                    "processing": TaskStatus.PROCESSING.value,
                    "updated_at": now,
                },
            ).mappings().one_or_none()
            session.commit()

            if row is None:
                return None

            if not row["task_type"]:
                logger.error(f"任务 {row['task_id']} 缺少 task_type，无法被 worker 执行。")
                self.mark_job_failed(
                    task_id=row["task_id"],
                    message="Task type missing, worker cannot execute.",
                )
                return None

            return QueuedJob(
                job=self._deserialize_job(row),
                task_kind=TaskKind(row["task_type"]),
            )
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"领取 pending 任务失败: {e}")
            raise
        finally:
            session.close()

    def get_job(self, task_id: str) -> Optional[JobInfo]:
        session = self.Session()
        try:
            stmt = (
                select(self.jobs_table)
                .where(self.jobs_table.c.task_id == task_id)
                .limit(1)
            )
            row = session.execute(stmt).mappings().one_or_none()
            if row is None:
                return None
            return self._deserialize_job(row)
        except SQLAlchemyError as e:
            logger.error(f"读取任务状态失败: {task_id}, error={e}")
            raise
        finally:
            session.close()

    def mark_processing_jobs_as_failed(self) -> int:
        """
        worker 进程重启后，上次正在执行的 processing 任务已失去运行句柄。
        当前阶段先将其收敛为 failed，避免前端永久轮询一个不会再变化的状态。
        """
        session = self.Session()
        try:
            now = time.time()
            stmt = (
                update(self.jobs_table)
                .where(
                    self.jobs_table.c.status.in_(
                        [TaskStatus.PROCESSING.value]
                    )
                )
                .values(
                    status=TaskStatus.FAILED.value,
                    message_code=MessageCode.INTERNAL_ERROR.value,
                    message="Task interrupted by worker restart.",
                    error_code=ErrorCode.INTERNAL_ERROR.value,
                    error_message="Task interrupted by worker restart.",
                    error_detail=(
                        "Task was running when the worker process restarted."
                    ),
                    updated_at=now,
                )
            )
            result = session.execute(stmt)
            session.commit()
            affected = result.rowcount or 0
            if affected:
                logger.warning(
                    f"检测到 {affected} 个 processing 任务，已在 worker 启动时标记为 failed。"
                )
            return affected
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"恢复未完成任务状态失败: {e}")
            raise
        finally:
            session.close()

    def mark_job_failed(self, task_id: str, message: str) -> None:
        session = self.Session()
        try:
            session.execute(
                update(self.jobs_table)
                .where(self.jobs_table.c.task_id == task_id)
                .values(
                    status=TaskStatus.FAILED.value,
                    message_code=MessageCode.INTERNAL_ERROR.value,
                    message=message,
                    error_code=ErrorCode.INTERNAL_ERROR.value,
                    error_message=message,
                    updated_at=time.time(),
                )
            )
            session.commit()
        except SQLAlchemyError as e:
            session.rollback()
            logger.error(f"将任务标记为 failed 失败: {task_id}, error={e}")
            raise
        finally:
            session.close()

    def readiness_report(self) -> dict[str, dict[str, str | bool]]:
        report: dict[str, dict[str, str | bool]] = {
            "database": {"ok": False, "detail": "not checked"},
            "queue": {"ok": False, "detail": "not checked"},
        }

        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            report["database"] = {"ok": True, "detail": "database reachable"}
        except SQLAlchemyError as exc:
            report["database"] = {"ok": False, "detail": f"database error: {exc}"}
            return report

        try:
            has_jobs_table = inspect(self.engine).has_table("jobs")
            if has_jobs_table:
                report["queue"] = {"ok": True, "detail": "jobs table ready"}
            else:
                report["queue"] = {"ok": False, "detail": "jobs table missing"}
        except SQLAlchemyError as exc:
            report["queue"] = {"ok": False, "detail": f"queue error: {exc}"}

        return report

    def dispose(self) -> None:
        self.Session.remove()
        self.engine.dispose()

    def _deserialize_job(self, row: Any) -> JobInfo:
        error = None
        if row["error_code"]:
            error = ErrorInfo(
                code=ErrorCode(row["error_code"]),
                message=row["error_message"] or "",
                detail=row["error_detail"],
            )

        return JobInfo(
            task_id=row["task_id"],
            status=TaskStatus(row["status"]),
            video_id=row["video_id"],
            message_code=(
                MessageCode(row["message_code"]) if row["message_code"] else None
            ),
            download_urls=row["download_urls"],
            message=row["message"] or "",
            result=row["result"],
            created_at=row["created_at"],
            error=error,
        )
