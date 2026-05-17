from __future__ import annotations

import subprocess
from typing import Any

from terminal_agent.executor import ToolPermissionError, run_shell_command


def run_git_command_tool(*, user: str, role: str, allowed_tools: set[str], workspace_id: str, args: dict[str, Any]) -> dict[str, Any]:
    raw_args = args.get("args")
    if isinstance(raw_args, list):
        argv = [str(x) for x in raw_args]
        git_args = subprocess.list2cmdline(argv)
    else:
        git_args = str(raw_args or "").strip()

    if not git_args:
        return {"error": "缺少 args 参数", "exit_code": 2, "stdout": "", "stderr": ""}

    cmd = f"git {git_args}"

    try:
        rc, out, err, task_session_id = run_shell_command(
            user_id=user,
            role=role,
            allowed_tools=allowed_tools,
            command=cmd,
            workspace_id=workspace_id,
        )
    except ToolPermissionError as ex:
        return {"error": str(ex), "exit_code": 3, "stdout": "", "stderr": str(ex)}

    return {
        "tool": "git_command",
        "command": cmd,
        "task_session_id": task_session_id,
        "exit_code": rc,
        "stdout": out,
        "stderr": err,
    }
