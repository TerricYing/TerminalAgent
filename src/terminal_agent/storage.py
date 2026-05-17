from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path
from datetime import datetime, timezone

from terminal_agent.paths import AGENT_RUNTIME_DB_DIR, ensure_runtime_layout


SCHEDULE_DB = AGENT_RUNTIME_DB_DIR / "schedule.sqlite"


@dataclass(frozen=True)
class ScheduleItem:
    task_id: str
    user_id: str
    role: str
    run_at: str
    command: str
    status: str


def _connect() -> sqlite3.Connection:
    ensure_runtime_layout()
    conn = sqlite3.connect(SCHEDULE_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schedule_tasks (
            task_id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            role TEXT NOT NULL,
            run_at TEXT NOT NULL,
            command TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            last_run_at TEXT,
            last_exit_code INTEGER,
            created_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
        """
    )

    # 轻量迁移：兼容初版 MVP 结构下已存在的数据库。
    existing_cols = {
        row[1] for row in conn.execute("PRAGMA table_info(schedule_tasks)").fetchall()
    }
    if "user_id" not in existing_cols:
        conn.execute("ALTER TABLE schedule_tasks ADD COLUMN user_id TEXT NOT NULL DEFAULT 'runner'")
    if "role" not in existing_cols:
        conn.execute("ALTER TABLE schedule_tasks ADD COLUMN role TEXT NOT NULL DEFAULT 'operator'")
    if "status" not in existing_cols:
        conn.execute("ALTER TABLE schedule_tasks ADD COLUMN status TEXT NOT NULL DEFAULT 'pending'")
    if "last_run_at" not in existing_cols:
        conn.execute("ALTER TABLE schedule_tasks ADD COLUMN last_run_at TEXT")
    if "last_exit_code" not in existing_cols:
        conn.execute("ALTER TABLE schedule_tasks ADD COLUMN last_exit_code INTEGER")

    conn.commit()
    return conn


def add_schedule(task_id: str, user_id: str, role: str, run_at: str, command: str) -> None:
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO schedule_tasks(task_id, user_id, role, run_at, command, status, last_run_at, last_exit_code)
            VALUES(?, ?, ?, ?, ?, 'pending', NULL, NULL)
            """,
            (task_id, user_id, role, run_at, command),
        )
        conn.commit()


def remove_schedule(task_id: str) -> int:
    with _connect() as conn:
        cur = conn.execute("DELETE FROM schedule_tasks WHERE task_id = ?", (task_id,))
        conn.commit()
        return cur.rowcount


def list_schedule() -> list[ScheduleItem]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT task_id, user_id, role, run_at, command, status FROM schedule_tasks ORDER BY run_at ASC"
        ).fetchall()
    return [ScheduleItem(*row) for row in rows]


def due_schedule(now_iso: str | None = None) -> list[ScheduleItem]:
    if now_iso is None:
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT task_id, user_id, role, run_at, command, status
            FROM schedule_tasks
            WHERE status = 'pending' AND run_at <= ?
            ORDER BY run_at ASC
            """,
            (now_iso,),
        ).fetchall()
    return [ScheduleItem(*row) for row in rows]


def finish_schedule(task_id: str, exit_code: int) -> None:
    now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    status = "success" if exit_code == 0 else "failed"
    with _connect() as conn:
        conn.execute(
            "UPDATE schedule_tasks SET status = ?, last_run_at = ?, last_exit_code = ? WHERE task_id = ?",
            (status, now_iso, exit_code, task_id),
        )
        conn.commit()


def memory_file(user_id: str) -> Path:
    ensure_runtime_layout()
    mem_path = AGENT_RUNTIME_DB_DIR.parent.parent / "memory" / f"{user_id}.txt"
    mem_path.parent.mkdir(parents=True, exist_ok=True)
    return mem_path


# ---------------------------------------------------------------------------
# 任务存储：每个提交任务一条记录，并与 schedule 完全隔离。
# ---------------------------------------------------------------------------

TASKS_DB = AGENT_RUNTIME_DB_DIR / "tasks.sqlite"


@dataclass(frozen=True)
class TaskItem:
    task_id: str
    user_id: str
    role: str
    description: str
    plan_file: str
    session_id: str
    workspace_id: str
    status: str          # pending | running | done | failed（待执行 | 运行中 | 完成 | 失败）
    created_at: str
    started_at: str | None
    finished_at: str | None
    exit_code: int | None


def _connect_tasks() -> sqlite3.Connection:
    ensure_runtime_layout()
    conn = sqlite3.connect(TASKS_DB)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id     TEXT PRIMARY KEY,
            user_id     TEXT NOT NULL,
            role        TEXT NOT NULL,
            description TEXT NOT NULL,
            plan_file   TEXT NOT NULL,
            session_id  TEXT NOT NULL,
            workspace_id TEXT NOT NULL,
            status      TEXT NOT NULL DEFAULT 'pending',
            created_at  TEXT NOT NULL,
            started_at  TEXT,
            finished_at TEXT,
            exit_code   INTEGER
        )
        """
    )
    conn.commit()
    return conn


def create_task(
    task_id: str,
    user_id: str,
    role: str,
    description: str,
    plan_file: str,
    session_id: str,
    workspace_id: str,
) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with _connect_tasks() as conn:
        conn.execute(
            """
            INSERT INTO tasks(task_id, user_id, role, description, plan_file,
                              session_id, workspace_id, status, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?)
            """,
            (task_id, user_id, role, description, plan_file, session_id, workspace_id, now),
        )
        conn.commit()


def start_task(task_id: str) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    with _connect_tasks() as conn:
        conn.execute(
            "UPDATE tasks SET status = 'running', started_at = ? WHERE task_id = ?",
            (now, task_id),
        )
        conn.commit()


def finish_task(task_id: str, exit_code: int) -> None:
    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    status = "done" if exit_code == 0 else "failed"
    with _connect_tasks() as conn:
        conn.execute(
            "UPDATE tasks SET status = ?, finished_at = ?, exit_code = ? WHERE task_id = ?",
            (status, now, exit_code, task_id),
        )
        conn.commit()


def list_tasks(user_id: str | None = None) -> list[TaskItem]:
    with _connect_tasks() as conn:
        if user_id:
            rows = conn.execute(
                """SELECT task_id, user_id, role, description, plan_file,
                          session_id, workspace_id, status, created_at,
                          started_at, finished_at, exit_code
                   FROM tasks WHERE user_id = ? ORDER BY created_at DESC""",
                (user_id,),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT task_id, user_id, role, description, plan_file,
                          session_id, workspace_id, status, created_at,
                          started_at, finished_at, exit_code
                   FROM tasks ORDER BY created_at DESC"""
            ).fetchall()
    return [TaskItem(*row) for row in rows]
