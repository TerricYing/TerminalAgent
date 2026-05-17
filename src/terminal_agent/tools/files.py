from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from terminal_agent.paths import AGENT_RUNTIME_WORKSPACES_DIR

if TYPE_CHECKING:
    from terminal_agent.tools.registry import ToolContext


def _workspace_root(ctx: ToolContext) -> Path:
    root = AGENT_RUNTIME_WORKSPACES_DIR / ctx.user / ctx.workspace_id
    root.mkdir(parents=True, exist_ok=True)
    return root.resolve()


def _resolve_workspace_path(ctx: ToolContext, raw_path: str) -> Path:
    root = _workspace_root(ctx)
    target = (root / raw_path).resolve()
    if target != root and root not in target.parents:
        raise ValueError("路径越界：仅允许访问当前任务工作区")
    return target


def read_file_tool(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if "file_read" not in ctx.allowed_tools:
        return {"error": "当前角色没有 file_read 权限", "exit_code": 3}

    raw_path = str(args.get("path", "")).strip()
    if not raw_path:
        return {"error": "缺少 path 参数", "exit_code": 2}

    try:
        target = _resolve_workspace_path(ctx, raw_path)
    except ValueError as ex:
        return {"error": str(ex), "exit_code": 2}

    if not target.exists() or not target.is_file():
        return {"error": f"文件不存在: {raw_path}", "exit_code": 1}

    text = target.read_text(encoding="utf-8", errors="replace")
    start_line = args.get("start_line")
    end_line = args.get("end_line")

    if start_line is not None or end_line is not None:
        if not isinstance(start_line, int) and start_line is not None:
            return {"error": "start_line 必须是整数", "exit_code": 2}
        if not isinstance(end_line, int) and end_line is not None:
            return {"error": "end_line 必须是整数", "exit_code": 2}

        lines = text.splitlines(keepends=True)
        s = 1 if start_line is None else max(1, start_line)
        e = len(lines) if end_line is None else min(len(lines), end_line)
        if e < s:
            return {"error": "end_line 不能小于 start_line", "exit_code": 2}
        text = "".join(lines[s - 1 : e])

    return {
        "tool": "read_file",
        "path": raw_path,
        "content": text,
        "exit_code": 0,
    }


def write_file_tool(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if "file_write" not in ctx.allowed_tools:
        return {"error": "当前角色没有 file_write 权限", "exit_code": 3}

    raw_path = str(args.get("path", "")).strip()
    if not raw_path:
        return {"error": "缺少 path 参数", "exit_code": 2}

    content = str(args.get("content", ""))
    mode = str(args.get("mode", "overwrite")).strip().lower()
    if mode not in {"overwrite", "append"}:
        return {"error": "mode 仅支持 overwrite 或 append", "exit_code": 2}

    try:
        target = _resolve_workspace_path(ctx, raw_path)
    except ValueError as ex:
        return {"error": str(ex), "exit_code": 2}

    target.parent.mkdir(parents=True, exist_ok=True)
    open_mode = "a" if mode == "append" else "w"
    with target.open(open_mode, encoding="utf-8") as f:
        f.write(content)

    return {
        "tool": "write_file",
        "path": raw_path,
        "mode": mode,
        "bytes_written": len(content.encode("utf-8")),
        "exit_code": 0,
    }


def find_files_tool(ctx: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    if "file_read" not in ctx.allowed_tools:
        return {"error": "当前角色没有 file_read 权限", "exit_code": 3}

    pattern = str(args.get("pattern", "**/*")).strip() or "**/*"
    max_results = args.get("max_results", 100)
    if not isinstance(max_results, int):
        return {"error": "max_results 必须是整数", "exit_code": 2}
    max_results = max(1, min(max_results, 1000))

    root = _workspace_root(ctx)
    results: list[str] = []

    for p in root.glob(pattern):
        rel = p.resolve().relative_to(root).as_posix()
        results.append(rel + ("/" if p.is_dir() else ""))
        if len(results) >= max_results:
            break

    return {
        "tool": "find_files",
        "pattern": pattern,
        "count": len(results),
        "results": sorted(results),
        "exit_code": 0,
    }
