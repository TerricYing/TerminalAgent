from __future__ import annotations

import json
import os
from collections.abc import Callable
from typing import Any

from terminal_agent.config import _load_yaml
from terminal_agent.paths import AGENT_MODELS_DIR, AGENT_PROMPTS_DIR
from terminal_agent.secret_store import load_api_key


def _load_profile_and_provider() -> tuple[dict[str, Any], dict[str, Any]]:
    providers = _load_yaml(AGENT_MODELS_DIR / "providers.yaml").get("providers", [])
    profiles = _load_yaml(AGENT_MODELS_DIR / "profiles.yaml").get("profiles", [])
    if not profiles:
        raise RuntimeError(".agent/models/profiles.yaml 中未配置 LLM profile")
    profile = profiles[0]
    provider_name = profile.get("provider")
    provider = next((p for p in providers if p.get("name") == provider_name), None)
    if not provider:
        raise RuntimeError(
            f"在 .agent/models/providers.yaml 中未找到 provider {provider_name!r}"
        )
    return profile, provider


def _load_system_prompt() -> str:
    prompt_file = AGENT_PROMPTS_DIR / "system.md"
    if not prompt_file.exists():
        raise RuntimeError("缺少提示词文件：.agent/prompts/system.md")
    text = prompt_file.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError("提示词文件为空：.agent/prompts/system.md")
    return text


def _build_messages(plan_text: str, skills_guides: list[tuple[str, str]] | None = None) -> list[dict[str, Any]]:
    """
    构建消息列表。
    
    Args:
        plan_text: 用户任务描述
        skills_guides: [(skill_name, guide_text), ...] 可用的所有 skill 及其指南
    """
    system_prompt = _load_system_prompt()
    
    # 生成 skill 汇总
    skills_summary = ""
    if skills_guides:
        for skill_name, guide_text in skills_guides:
            skills_summary += f"\n### {skill_name}\n{guide_text}\n"
    
    # 替换系统提示词中的占位符
    system_prompt = system_prompt.replace("${skills_summary}", skills_summary)
    
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    messages.append({"role": "user", "content": plan_text})
    return messages


def _run_loop(
    client: Any,
    model: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
) -> int:
    """Function calling 循环，与具体后端无关。"""
    last_rc = 0

    while True:
        response = client.chat.completions.create(
            model=model,
            messages=messages,  # type: ignore[arg-type]
            tools=tools,  # type: ignore[arg-type]
            tool_choice="auto",
        )

        msg = response.choices[0].message

        assistant_entry: dict[str, Any] = {"role": "assistant", "content": msg.content or ""}
        reasoning = getattr(msg, "reasoning_content", None)
        if reasoning:
            assistant_entry["reasoning_content"] = reasoning
        if msg.tool_calls:
            assistant_entry["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": tc.type,
                    "function": {
                        "name": tc.function.name,
                        "arguments": tc.function.arguments,
                    },
                }
                for tc in msg.tool_calls
            ]
        messages.append(assistant_entry)

        if not msg.tool_calls:
            if msg.content:
                print(msg.content)
            break

        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments)
            except json.JSONDecodeError:
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "错误：无法解析工具参数",
                    }
                )
                continue

            if not isinstance(args, dict):
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": "错误：工具参数必须是 JSON 对象",
                    }
                )
                continue

            print(f"[llm] tool: {tc.function.name}")
            result = execute_tool(tc.function.name, args)
            if not isinstance(result, dict):
                result = {
                    "error": "工具返回结果格式错误",
                    "exit_code": 2,
                    "stdout": "",
                    "stderr": "",
                }

            rc = result.get("exit_code")
            if isinstance(rc, int):
                last_rc = rc

            result_text = json.dumps(result, ensure_ascii=False)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": result_text,
                }
            )

    return last_rc


def _prompt_local_fallback(reason: str) -> bool:
    """询问用户是否切换到本地模型。返回 True 表示同意。"""
    print()
    print(f"远程 API 不可用: {reason}")
    while True:
        try:
            answer = input("是否切换到本地模型？[y/N]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return False
        if answer in ("y", "yes"):
            return True
        if answer in ("", "n", "no"):
            return False


def _run_remote(
    plan_text: str,
    execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    tools: list[dict[str, Any]],
    skills_guides: list[tuple[str, str]] | None = None,
) -> int:
    """尝试远程 API。成功则返回 exit code，失败则 raise。"""
    from openai import OpenAI

    profile, provider = _load_profile_and_provider()
    api_key_env = provider.get("api_key_env", "OPENAI_API_KEY")
    api_key = os.environ.get(api_key_env, "")
    if not api_key:
        api_key = load_api_key(api_key_env)
    if not api_key:
        raise RuntimeError(
            f"未找到 API key：{api_key_env!r}。\n"
            "当前进程环境变量与本机 DPAPI keyring 中都没有该键。\n"
            "请运行: agent key current / agent key set / agent key check"
        )

    client = OpenAI(
        api_key=api_key,
        base_url=provider.get("base_url"),
        timeout=float(profile.get("timeout_seconds", 30)),
    )
    model: str = profile.get("model", "gpt-4.1-mini")
    if not tools:
        raise RuntimeError("当前没有可用的 skill 和工具")

    messages = _build_messages(plan_text, skills_guides)
    return _run_loop(client, model, messages, tools, execute_tool)


def _run_local(
    plan_text: str,
    execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    tools: list[dict[str, Any]],
    skills_guides: list[tuple[str, str]] | None = None,
) -> int:
    """使用本地 llama-server 模型。"""
    from terminal_agent.local_llm import (
        UrllibClient,
        ensure_model_available,
        load_local_config,
    )

    config = load_local_config()
    status = ensure_model_available(config)
    if status is None:
        raise RuntimeError(
            "本地模型不可用。首次运行会自动下载 llama-server 和模型文件，"
            "请检查网络连接后重试。"
        )

    client = UrllibClient()
    messages = _build_messages(plan_text, skills_guides)
    return _run_loop(client, config.model_name, messages, tools, execute_tool)


def run_plan(
    plan_text: str,
    execute_tool: Callable[[str, dict[str, Any]], dict[str, Any]],
    tools: list[dict[str, Any]],
    skills_guides: list[tuple[str, str]] | None = None,
    *,
    force_local: bool = False,
) -> int:
    """
    将 *plan_text* 发送给 LLM 执行。

    - 默认先尝试远程 API，失败时询问用户是否切换到本地模型。
    - *force_local=True* 则直接使用本地模型。
    - *skills_guides* 是 [(skill_name, guide_text), ...] 列表，包含所有可用的 skill
    """
    if force_local:
        print("[local] 强制使用本地模型")
        return _run_local(plan_text, execute_tool, tools, skills_guides)

    try:
        return _run_remote(plan_text, execute_tool, tools, skills_guides)
    except RuntimeError as ex:
        reason = str(ex)
        if _prompt_local_fallback(reason):
            try:
                return _run_local(plan_text, execute_tool, tools, skills_guides)
            except RuntimeError as local_ex:
                print(f"本地模型也失败: {local_ex}")
                return 1
        print("已取消。")
        return 1
