from __future__ import annotations

import os
from pathlib import Path


def _resolve_agent_dir() -> Path:
    """
    解析当前运行时应使用的 .agent 目录。

    解析顺序：
    1. TERMINAL_AGENT_DIR 环境变量（绝对路径）：便于 CI/CD 或包装脚本
       显式指定配置根目录。
    2. 从当前工作目录向上查找已存在的 .agent/ 目录：保证 CLI 在项目
       任意子目录下都能正常工作。
    3. CWD/.agent：兜底为当前工作目录下创建 .agent。
    """
    env_override = os.environ.get("TERMINAL_AGENT_DIR")
    if env_override:
        return Path(env_override).resolve()

    cwd = Path.cwd().resolve()
    for candidate in [cwd, *cwd.parents]:
        if (candidate / ".agent").is_dir():
            return candidate / ".agent"

    return cwd / ".agent"


AGENT_DIR = _resolve_agent_dir()
DIST_DIR = Path.cwd() / "dist"
BUILD_DIR = Path.cwd() / "build"

AGENT_MODELS_DIR = AGENT_DIR / "models"
AGENT_SECURITY_DIR = AGENT_DIR / "security"
AGENT_SKILLS_DIR = AGENT_DIR / "skills"
AGENT_PROMPTS_DIR = AGENT_DIR / "prompts"
AGENT_MEMORY_DIR = AGENT_DIR / "memory"
AGENT_PLANS_DIR = AGENT_DIR / "plans"
AGENT_SESSIONLOGS_DIR = AGENT_DIR / "sessionlogs"
AGENT_RUNTIME_DIR = AGENT_DIR / "runtime"
AGENT_RUNTIME_DB_DIR = AGENT_RUNTIME_DIR / "db"
AGENT_RUNTIME_WORKSPACES_DIR = AGENT_RUNTIME_DIR / "workspaces"
AGENT_RUNTIME_TMP_DIR = AGENT_RUNTIME_DIR / "tmp"


def ensure_runtime_layout() -> None:
    for folder in (
        AGENT_MODELS_DIR,
        AGENT_SECURITY_DIR,
        AGENT_SKILLS_DIR,
        AGENT_PROMPTS_DIR,
        AGENT_MEMORY_DIR,
        AGENT_PLANS_DIR,
        AGENT_SESSIONLOGS_DIR,
        AGENT_RUNTIME_DB_DIR,
        AGENT_RUNTIME_WORKSPACES_DIR,
        AGENT_RUNTIME_TMP_DIR,
    ):
        folder.mkdir(parents=True, exist_ok=True)
