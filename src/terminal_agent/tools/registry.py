from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from terminal_agent.tools.files import find_files_tool, read_file_tool, write_file_tool
from terminal_agent.tools.git import run_git_command_tool
from terminal_agent.tools.shell import run_shell_command_tool


@dataclass(frozen=True)
class ToolContext:
    user: str
    role: str
    allowed_tools: set[str]
    workspace_id: str


ToolHandler = Callable[[ToolContext, dict[str, Any]], dict[str, Any]]


def _shell_handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return run_shell_command_tool(
        user=ctx.user,
        role=ctx.role,
        allowed_tools=ctx.allowed_tools,
        workspace_id=ctx.workspace_id,
        args=args,
    )


def _read_file_handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return read_file_tool(ctx, args)


def _write_file_handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return write_file_tool(ctx, args)


def _find_files_handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return find_files_tool(ctx, args)


def _git_handler(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return run_git_command_tool(
        user=ctx.user,
        role=ctx.role,
        allowed_tools=ctx.allowed_tools,
        workspace_id=ctx.workspace_id,
        args=args,
    )


TOOL_HANDLERS: dict[str, ToolHandler] = {
    "run_shell_command": _shell_handler,
    "read_file": _read_file_handler,
    "write_file": _write_file_handler,
    "find_files": _find_files_handler,
    "git_command": _git_handler,
}


def execute_tool(tool_name: str, args: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    handler = TOOL_HANDLERS.get(tool_name)
    if not handler:
        return {"error": f"工具 {tool_name!r} 不可用", "exit_code": 2, "stdout": "", "stderr": ""}
    return handler(ctx, args)
