from __future__ import annotations

import argparse
import getpass
import json
import uuid
from pathlib import Path
from typing import Any

from terminal_agent.config import _load_yaml, load_role_permissions, validate_config
from terminal_agent.paths import AGENT_MODELS_DIR, AGENT_PLANS_DIR, AGENT_SESSIONLOGS_DIR, ensure_runtime_layout
from terminal_agent.skill_loader import list_skills
from terminal_agent.storage import (
    create_task,
    finish_task,
    list_tasks,
    start_task,
)
from terminal_agent.tools import ToolContext, execute_tool
from terminal_agent.secret_store import load_api_key, save_api_key


def _cmd_config_validate(_: argparse.Namespace) -> int:
    result = validate_config()
    if not result.issues:
        print("config valid")
        return 0
    for issue in result.issues:
        print(f"[{issue.level}] {issue.message}")
    return 0 if result.is_valid else 2


def _cmd_logs_tail(args: argparse.Namespace) -> int:
    ensure_runtime_layout()
    log_file = AGENT_SESSIONLOGS_DIR / args.user / f"{args.session}.log"
    if not log_file.exists():
        print("log not found")
        return 1
    lines = log_file.read_text(encoding="utf-8").splitlines()
    for line in lines[-args.lines :]:
        print(line)
    return 0


def _append_session_log(user: str, session: str, payload: dict[str, Any]) -> None:
    folder = AGENT_SESSIONLOGS_DIR / user
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / f"{session}.log").open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=True) + "\n")


def _run_llm_plan(
    *,
    user: str,
    role: str,
    session: str,
    plan_text: str,
    workspace_id: str,
    force_local: bool = False,
    payload_base: dict[str, Any] | None = None,
) -> int:
    from terminal_agent.llm import run_plan

    # 加载所有可用的 skill
    all_skills = list_skills()
    if not all_skills:
        print("错误：未找到任何 skill")
        return 1

    # 收集所有 skill 的工具定义
    all_tools: dict[str, dict[str, Any]] = {}
    skills_guides: list[tuple[str, str]] = []
    
    for skill in all_skills:
        # 收集该 skill 的所有工具（去重）
        for tool in skill.tools:
            if isinstance(tool, dict):
                func = tool.get("function", {})
                tool_name = func.get("name")
                if tool_name and tool_name not in all_tools:
                    all_tools[tool_name] = tool
        
        # 记录 skill 的说明
        skills_guides.append((skill.name, skill.guide_text))

    # 转换为列表格式（用于 OpenAI API）
    tools_list = list(all_tools.values())

    # 构建工具名称集合用于权限检查
    all_tool_names = set(all_tools.keys())

    role_permissions = load_role_permissions()
    allowed = role_permissions.get(role, set())
    base_payload = payload_base or {}
    ctx = ToolContext(user=user, role=role, allowed_tools=allowed, workspace_id=workspace_id)

    def execute(tool_name: str, args: dict[str, Any]) -> dict[str, Any]:
        if tool_name not in all_tool_names:
            result = {"error": f"工具 {tool_name!r} 不可用", "exit_code": 2}
            payload = dict(base_payload)
            payload.update(
                {
                    "tool": tool_name,
                    "args": args,
                    "workspace_id": workspace_id,
                    "result": result,
                }
            )
            _append_session_log(user, session, payload)
            return result

        result = execute_tool(tool_name, args, ctx)
        payload = dict(base_payload)
        payload.update(
            {
                "tool": tool_name,
                "args": args,
                "workspace_id": workspace_id,
                "result": result,
            }
        )
        _append_session_log(user, session, payload)
        return result

    try:
        return run_plan(plan_text, execute, tools_list, skills_guides, force_local=force_local)
    except RuntimeError as ex:
        print(f"error: {ex}")
        return 1


def _cmd_task_run(args: argparse.Namespace) -> int:
    task_id = uuid.uuid4().hex[:16]
    session_id = f"task-{task_id}"
    plan_workspace_id = uuid.uuid4().hex

    ensure_runtime_layout()
    plan_file = AGENT_PLANS_DIR / f"{task_id}.md"
    plan_file.write_text(args.task, encoding="utf-8")

    create_task(
        task_id=task_id,
        user_id=args.user,
        role=args.role,
        description=args.task,
        plan_file=str(plan_file),
        session_id=session_id,
        workspace_id=plan_workspace_id,
    )

    print(f"task_id={task_id}")
    print(f"session={session_id}")
    print(f"plan={plan_file}")

    start_task(task_id)
    rc = _run_llm_plan(
        user=args.user,
        role=args.role,
        session=session_id,
        plan_text=args.task,
        workspace_id=plan_workspace_id,
        force_local=bool(getattr(args, "local", False)),
        payload_base={"task_id": task_id},
    )

    finish_task(task_id, rc)
    print(f"status={'done' if rc == 0 else 'failed'} exit_code={rc}")
    return rc


def _cmd_task_list(args: argparse.Namespace) -> int:
    user_filter: str | None = getattr(args, "user", None)
    items = list_tasks(user_id=user_filter)
    if not items:
        print("no tasks")
        return 0
    for item in items:
        preview = item.description[:60].replace("\n", " ")
        print(
            f"{item.task_id}\t{item.user_id}\t{item.status}\t"
            f"{item.created_at}\t{preview}"
        )
    return 0


def _cmd_setup(_: argparse.Namespace) -> int:
    from terminal_agent.setup import SetupWizard

    wizard = SetupWizard()
    return wizard.run()


def _active_api_key_name() -> str:
    profiles = _load_yaml(AGENT_MODELS_DIR / "profiles.yaml").get("profiles", [])
    providers = _load_yaml(AGENT_MODELS_DIR / "providers.yaml").get("providers", [])

    if not isinstance(profiles, list) or not profiles:
        return "OPENAI_API_KEY"
    profile = profiles[0] if isinstance(profiles[0], dict) else {}
    provider_name = profile.get("provider")
    if not isinstance(provider_name, str) or not provider_name:
        return "OPENAI_API_KEY"

    if not isinstance(providers, list):
        return "OPENAI_API_KEY"
    provider = next(
        (
            p
            for p in providers
            if isinstance(p, dict) and p.get("name") == provider_name
        ),
        None,
    )
    if not isinstance(provider, dict):
        return "OPENAI_API_KEY"
    api_key_env = provider.get("api_key_env")
    return api_key_env if isinstance(api_key_env, str) and api_key_env.strip() else "OPENAI_API_KEY"


def _cmd_key_set(args: argparse.Namespace) -> int:
    key_name = str(args.name).strip() if args.name else _active_api_key_name()
    if not key_name:
        print("error: key name is required")
        return 2

    try:
        value = getpass.getpass(f"{key_name}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print("\ncancelled")
        return 1

    if not value:
        print("error: empty key")
        return 2

    save_api_key(key_name, value)
    print(f"saved key: {key_name}")
    return 0


def _cmd_key_check(args: argparse.Namespace) -> int:
    key_name = str(args.name).strip() if args.name else _active_api_key_name()
    if not key_name:
        print("error: key name is required")
        return 2
    exists = bool(load_api_key(key_name))
    print(f"{key_name}={str(exists).lower()}")
    return 0 if exists else 1


def _cmd_key_current(_: argparse.Namespace) -> int:
    key_name = _active_api_key_name()
    print(f"active_key_name={key_name}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="agent")
    sub = p.add_subparsers(dest="command", required=True)

    setup = sub.add_parser("setup", help="运行配置向导（使用本地小模型，无需 API key）")
    setup.set_defaults(func=_cmd_setup)

    key = sub.add_parser("key", help="管理本机加密 keyring 中的 API key")
    key_sub = key.add_subparsers(dest="key_command", required=True)

    key_set = key_sub.add_parser("set", help="写入 API key 到本机加密 keyring")
    key_set.add_argument("--name", default=None, help="Key name (默认跟随当前 provider 的 api_key_env)")
    key_set.set_defaults(func=_cmd_key_set)

    key_check = key_sub.add_parser("check", help="检查 API key 是否存在于本机加密 keyring")
    key_check.add_argument("--name", default=None, help="Key name (默认跟随当前 provider 的 api_key_env)")
    key_check.set_defaults(func=_cmd_key_check)

    key_current = key_sub.add_parser("current", help="显示当前 profile/provider 使用的 key 名称")
    key_current.set_defaults(func=_cmd_key_current)

    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command", required=True)
    validate = config_sub.add_parser("validate")
    validate.set_defaults(func=_cmd_config_validate)

    logs = sub.add_parser("logs")
    logs_sub = logs.add_subparsers(dest="logs_command", required=True)
    l_tail = logs_sub.add_parser("tail")
    l_tail.add_argument("--user", required=True)
    l_tail.add_argument("--session", required=True)
    l_tail.add_argument("--lines", type=int, default=50)
    l_tail.set_defaults(func=_cmd_logs_tail)

    task = sub.add_parser("task")
    task_sub = task.add_subparsers(dest="task_command", required=True)

    t_run = task_sub.add_parser("run")
    t_run.add_argument("--task", required=True, help="Natural language task description")
    t_run.add_argument("--user", required=True)
    t_run.add_argument("--role", required=True)
    t_run.add_argument("--local", action="store_true", help="Force use local llama-server model")
    t_run.set_defaults(func=_cmd_task_run)

    t_list = task_sub.add_parser("list")
    t_list.add_argument("--user", required=False, help="Filter by user")
    t_list.set_defaults(func=_cmd_task_list)

    return p


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    code = args.func(args)
    raise SystemExit(code)
