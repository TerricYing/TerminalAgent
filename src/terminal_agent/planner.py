from __future__ import annotations

import re

from terminal_agent.skill_loader import list_skills


_TOKEN_RE = re.compile(r"[a-zA-Z0-9_\-\u4e00-\u9fff]+")


def select_skill_for_task(task_text: str) -> str:
    skills = list_skills()
    if not skills:
        raise RuntimeError("未找到可用 skill")

    task_tokens = {t.lower() for t in _TOKEN_RE.findall(task_text)}
    best_name = skills[0].name
    best_score = -1.0

    for s in skills:
        bag = f"{s.name} {s.description} {s.guide_text}".lower()
        score = 0.0

        # 简单关键词匹配打分
        for tok in task_tokens:
            if tok and tok in bag:
                score += 1.0

        # 名称命中权重更高
        if s.name.lower() in task_text.lower():
            score += 3.0

        # 工具数加权：工具越多的 skill 越通用
        score += len(s.tools) * 0.5

        if score > best_score:
            best_score = score
            best_name = s.name

    return best_name
