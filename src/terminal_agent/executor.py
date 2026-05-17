from __future__ import annotations

import os
import subprocess
import uuid
from pathlib import Path

from terminal_agent.paths import AGENT_RUNTIME_TMP_DIR, AGENT_RUNTIME_WORKSPACES_DIR, ensure_runtime_layout


class ToolPermissionError(RuntimeError):
    pass


def _decode_output(data: bytes | bytearray | memoryview | str | None) -> str:
    if data is None:
        return ""
    if isinstance(data, str):
        return data
    blob = bytes(data)

    for enc in ("utf-8", "gbk"):
        try:
            return blob.decode(enc)
        except UnicodeDecodeError:
            continue
    return blob.decode("utf-8", errors="replace")


def _workspace(user_id: str, task_session_id: str) -> Path:
    ensure_runtime_layout()
    path = AGENT_RUNTIME_WORKSPACES_DIR / user_id / task_session_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def run_shell_command(
    *,
    user_id: str,
    role: str,
    allowed_tools: set[str],
    command: str,
    workspace_id: str | None = None,
) -> tuple[int, str, str, str]:
    """
    以 *user_id* 身份执行 *command*。

    *workspace_id* 用于固定工作目录，使同一计划中的多条命令
    共享同一份文件系统状态；如果省略，则仅为本次命令创建
    一个新的工作区。

    返回 (exit_code, stdout, stderr, task_session_id)。
    其中返回的 *task_session_id* 始终是新的唯一值，仅用于日志记录，
    它不是 workspace_id。
    """
    if "shell" not in allowed_tools and "powershell" not in allowed_tools and "cmd" not in allowed_tools:
        raise ToolPermissionError(f"role {role} cannot execute shell commands")

    task_session_id = uuid.uuid4().hex
    effective_workspace = workspace_id if workspace_id else task_session_id
    cwd = _workspace(user_id, effective_workspace)
    tmp_dir = AGENT_RUNTIME_TMP_DIR / task_session_id
    tmp_dir.mkdir(parents=True, exist_ok=True)

    # 透传 LLM API key 相关环境变量，使子进程（如 schtasks 触发的 agent 任务）能正常调用 LLM。
    _api_key_passthrough = {
        k: v
        for k in (
            "OPENAI_API_KEY",
            "DEEPSEEK_API_KEY",
            "ANTHROPIC_API_KEY",
            "AZURE_OPENAI_API_KEY",
            "PYTHONPATH",
        )
        if (v := os.environ.get(k))
    }

    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "COMSPEC": os.environ.get("COMSPEC", ""),
        "TEMP": str(tmp_dir),
        "TMP": str(tmp_dir),
        "AGENT_USER_ID": user_id,
        "AGENT_TASK_SESSION_ID": task_session_id,
        **_api_key_passthrough,
    }

    try:
        proc = subprocess.run(
            command,
            shell=True,
            cwd=str(cwd),
            env=env,
            capture_output=True,
            timeout=60,
            text=False,
        )
    except subprocess.TimeoutExpired as ex:
        out = _decode_output(getattr(ex, "stdout", None))[-10000:]
        err = _decode_output(getattr(ex, "stderr", None))
        if err:
            err = (err + "\n")[-10000:]
        err = (err + "command timed out after 60 seconds")[-10000:]
        return 124, out, err, task_session_id

    stdout = _decode_output(proc.stdout)[-10000:]
    stderr = _decode_output(proc.stderr)[-10000:]
    return proc.returncode, stdout, stderr, task_session_id
