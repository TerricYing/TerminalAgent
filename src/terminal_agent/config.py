from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from terminal_agent.paths import AGENT_MODELS_DIR, AGENT_SECURITY_DIR, ensure_runtime_layout


@dataclass(frozen=True)
class ValidationIssue:
    level: str
    message: str


@dataclass(frozen=True)
class ConfigValidationResult:
    issues: list[ValidationIssue]

    @property
    def is_valid(self) -> bool:
        return all(issue.level != "error" for issue in self.issues)


def _load_yaml(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def validate_config() -> ConfigValidationResult:
    ensure_runtime_layout()
    issues: list[ValidationIssue] = []

    providers_path = AGENT_MODELS_DIR / "providers.yaml"
    profiles_path = AGENT_MODELS_DIR / "profiles.yaml"
    roles_path = AGENT_SECURITY_DIR / "roles.yaml"
    users_path = AGENT_SECURITY_DIR / "users.yaml"

    providers = _load_yaml(providers_path)
    profiles = _load_yaml(profiles_path)
    roles = _load_yaml(roles_path)
    users = _load_yaml(users_path)

    provider_entries = providers.get("providers", [])
    if not provider_entries:
        issues.append(ValidationIssue("error", "models/providers.yaml has no providers"))
    else:
        names = {item.get("name") for item in provider_entries if isinstance(item, dict)}
        if None in names:
            issues.append(ValidationIssue("error", "provider entry missing name"))

    profile_entries = profiles.get("profiles", [])
    if not profile_entries:
        issues.append(ValidationIssue("error", "models/profiles.yaml has no profiles"))
    else:
        for profile in profile_entries:
            if not isinstance(profile, dict):
                issues.append(ValidationIssue("error", "profile entry must be a mapping"))
                continue
            if "provider" not in profile:
                issues.append(ValidationIssue("error", f"profile {profile.get('name')} missing provider"))

    role_entries = roles.get("roles", [])
    if not role_entries:
        issues.append(ValidationIssue("error", "security/roles.yaml has no roles"))

    user_entries = users.get("users", [])
    if not user_entries:
        issues.append(ValidationIssue("warning", "security/users.yaml has no users"))

    role_names = {
        role.get("name")
        for role in role_entries
        if isinstance(role, dict) and role.get("name") is not None
    }
    for user in user_entries:
        if not isinstance(user, dict):
            issues.append(ValidationIssue("error", "user entry must be a mapping"))
            continue
        role = user.get("role")
        if role not in role_names:
            issues.append(ValidationIssue("error", f"user {user.get('id')} has unknown role {role}"))

    return ConfigValidationResult(issues=issues)


def load_role_permissions() -> dict[str, set[str]]:
    ensure_runtime_layout()
    roles_path = AGENT_SECURITY_DIR / "roles.yaml"
    roles = _load_yaml(roles_path).get("roles", [])
    mapping: dict[str, set[str]] = {}
    for role in roles:
        if not isinstance(role, dict):
            continue
        name = role.get("name")
        tools = role.get("tools", [])
        if isinstance(name, str) and isinstance(tools, list):
            mapping[name] = {t for t in tools if isinstance(t, str)}
    return mapping
