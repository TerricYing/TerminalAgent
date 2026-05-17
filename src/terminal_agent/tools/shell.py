from __future__ import annotations

from typing import Any

from terminal_agent.executor import ToolPermissionError, run_shell_command


def run_shell_command_tool(*, user: str, role: str, allowed_tools: set[str], workspace_id: str, args: dict[str, Any]) -> dict[str, Any]:
    command = str(args.get("command", "")).strip()
    if not command:
        return {"error": "缺少 command 参数", "exit_code": 2, "stdout": "", "stderr": ""}

    try:
        rc, out, err, task_session_id = run_shell_command(
            user_id=user,
            role=role,
            allowed_tools=allowed_tools,
            command=command,
            workspace_id=workspace_id,
        )
    except ToolPermissionError as ex:
        return {"error": str(ex), "exit_code": 3, "stdout": "", "stderr": str(ex)}

    return {
        "tool": "run_shell_command",
        "command": command,
        "task_session_id": task_session_id,
        "exit_code": rc,
        "stdout": out,
        "stderr": err,
    }
