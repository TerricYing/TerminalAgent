from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from terminal_agent.paths import AGENT_SKILLS_DIR


_META_BLOCK_RE = re.compile(r"```json\s*(\{[\s\S]*?\})\s*```", re.IGNORECASE)
_DESC_RE = re.compile(r"##\s*描述\s*\n([\s\S]*?)(?:\n##\s|\Z)", re.IGNORECASE)


@dataclass(frozen=True)
class SkillSpec:
    name: str
    description: str
    tools: list[dict[str, Any]]
    guide_text: str


def _resolve_skill_path(skill_name: str) -> Path:
    # 正式结构：.agent/skills/<name>/SKILL.md
    official = AGENT_SKILLS_DIR / skill_name / "SKILL.md"
    if official.exists():
        return official

    # 兼容旧结构：.agent/skills/<name>.md
    legacy = AGENT_SKILLS_DIR / f"{skill_name}.md"
    return legacy


def _parse_skill_text(text: str) -> dict[str, Any]:
    match = _META_BLOCK_RE.search(text)
    if not match:
        return {}
    try:
        data = json.loads(match.group(1))
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _extract_markdown_description(text: str) -> str:
    match = _DESC_RE.search(text)
    if not match:
        return ""
    return match.group(1).strip()


def load_skill(skill_name: str) -> SkillSpec:
    path = _resolve_skill_path(skill_name)
    if not path.exists():
        raise RuntimeError(f"skill 不存在：{path}")

    raw_text = path.read_text(encoding="utf-8")
    data = _parse_skill_text(raw_text)
    name = data.get("name") if isinstance(data.get("name"), str) else ""
    description = _extract_markdown_description(raw_text)
    if not description:
        description = data.get("description") if isinstance(data.get("description"), str) else ""
    tools = data.get("tools")

    if not isinstance(name, str) or not name:
        raise RuntimeError(f"skill 文件缺少 name：{path}")
    if name != skill_name:
        raise RuntimeError(f"skill 名称不匹配：期望 {skill_name!r}，实际 {name!r}")
    if not isinstance(tools, list) or not tools:
        raise RuntimeError(f"skill 文件缺少 tools：{path}")

    filtered = [t for t in tools if isinstance(t, dict)]
    if not filtered:
        raise RuntimeError(f"skill 文件中的 tools 无有效项：{path}")

    guide_text = _META_BLOCK_RE.sub("", raw_text).strip()
    if "## 调用流程" not in guide_text:
        raise RuntimeError(f"skill 文件缺少 '## 调用流程' 章节：{path}")
    if "## 注意事项" not in guide_text:
        raise RuntimeError(f"skill 文件缺少 '## 注意事项' 章节：{path}")

    return SkillSpec(name=name, description=description, tools=filtered, guide_text=guide_text)


def list_skills() -> list[SkillSpec]:
    specs: list[SkillSpec] = []

    # 正式结构：.agent/skills/<name>/SKILL.md
    for p in AGENT_SKILLS_DIR.glob("*/SKILL.md"):
        skill_name = p.parent.name
        try:
            specs.append(load_skill(skill_name))
        except RuntimeError:
            continue

    # 兼容旧结构：.agent/skills/<name>.md
    for p in AGENT_SKILLS_DIR.glob("*.md"):
        skill_name = p.stem
        if any(s.name == skill_name for s in specs):
            continue
        try:
            specs.append(load_skill(skill_name))
        except RuntimeError:
            continue

    return specs
