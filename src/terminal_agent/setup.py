from __future__ import annotations

import os
import getpass
import sys
from enum import Enum, auto

from terminal_agent.config import _load_yaml
from terminal_agent.local_llm import LocalLLM, ensure_model_available, load_local_config
from terminal_agent.paths import AGENT_MODELS_DIR, ensure_runtime_layout
from terminal_agent.secret_store import save_api_key


class SetupState(Enum):
    WELCOME = auto()
    PROVIDER_SELECT = auto()
    ENTER_KEY = auto()
    VALIDATE = auto()
    DONE = auto()


DEFAULT_SYSTEM_PROMPT = """你是一个终端智能体配置助手。你的任务是帮助用户配置 API Key。
请保持回复简洁、友好，使用中文。每个回复控制在2-3句话以内。
不要编造功能，只提供与配置 API Key 相关的帮助。"""


class SetupWizard:
    def __init__(self) -> None:
        self._state = SetupState.WELCOME
        self._provider_type = ""
        self._api_key = ""
        self._api_key_env = "OPENAI_API_KEY"
        self._base_url = ""
        self._retries = 0
        self._llm: LocalLLM | None = None

    def run(self) -> int:
        print("=" * 44)
        print("  TerminalAgent Setup Wizard")
        print("=" * 44)
        print()

        try:
            self._init_llm()
        except Exception as ex:
            print(f"本地模型加载失败: {ex}")
            print("将使用纯文本模式继续配置。")
            print()
            self._llm = None

        while self._state != SetupState.DONE:
            self._step()

        print("=" * 44)
        print("Setup 完成！运行 agent task run --help 开始使用。")
        print("=" * 44)
        return 0

    def _say(self, text: str) -> None:
        if self._llm is None:
            print(text)
            return
        try:
            response = self._llm.generate(
                system_prompt=DEFAULT_SYSTEM_PROMPT,
                user_prompt=text,
                max_tokens=256,
            )
            print(response)
        except Exception:
            print(text)

    def _init_llm(self) -> None:
        config = load_local_config()
        status = ensure_model_available(config)
        if status is None:
            raise RuntimeError(
                "本地模型启动失败。请检查网络连接后重试。"
                f"需要下载模型文件 {config.model_name}。"
            )
        print(status)
        self._llm = LocalLLM(config)
        print()

    def _step(self) -> None:
        if self._state == SetupState.WELCOME:
            self._handle_welcome()
        elif self._state == SetupState.PROVIDER_SELECT:
            self._handle_provider_select()
        elif self._state == SetupState.ENTER_KEY:
            self._handle_enter_key()
        elif self._state == SetupState.VALIDATE:
            self._handle_validate()
        elif self._state == SetupState.DONE:
            pass

    def _handle_welcome(self) -> None:
        prompt = (
            "用户刚刚启动了配置向导。请用中文欢迎用户，"
            "并告诉他们你将帮助他们设置 API Key 来启用 AI 能力。"
            "介绍下一步：选择 AI 服务提供商。"
        )
        self._say(prompt)
        self._state = SetupState.PROVIDER_SELECT

    def _handle_provider_select(self) -> None:
        print()
        print("可用的提供商类型:")
        print("  1. OpenAI (api.openai.com)")
        print("  2. 其他 OpenAI 兼容的 API (自定义 base URL)")
        print()

        while True:
            try:
                choice = input("请输入数字 [1-2]: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消。")
                sys.exit(0)

            if choice == "1":
                self._provider_type = "openai"
                self._base_url = "https://api.openai.com/v1"
                self._api_key_env = "OPENAI_API_KEY"
                break
            elif choice == "2":
                self._provider_type = "openai-compatible"
                self._base_url = input("请输入 Base URL: ").strip()
                if not self._base_url:
                    print("Base URL 不能为空。")
                    continue

                default_env_name = (
                    "DEEPSEEK_API_KEY"
                    if "deepseek" in self._base_url.lower()
                    else "CUSTOM_OPENAI_API_KEY"
                )

                env_name = input(
                    f"请输入 API Key 环境变量名（默认 {default_env_name}）: "
                ).strip()
                self._api_key_env = env_name or default_env_name
                break
            else:
                prompt = "用户输入了无效的选项。请用中文请用户输入 1 或 2。"
                self._say(prompt)

        self._state = SetupState.ENTER_KEY

    def _handle_enter_key(self) -> None:
        if self._provider_type == "openai":
            prompt = (
                "用户已选择 OpenAI。请用中文请用户提供他们的 OpenAI API Key（以 sk- 开头）。"
                "提示可以在 https://platform.openai.com/api-keys 创建。"
            )
        else:
            prompt = (
                "用户选择了自定义 OpenAI 兼容 API。请用中文请用户提供他们的 API Key。"
            )
        self._say(prompt)
        print()

        while True:
            try:
                key = getpass.getpass("API Key: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n已取消。")
                sys.exit(0)

            if not key:
                self._say("用户没有输入 API Key。请用中文请他们重新输入。")
                continue
            self._api_key = key
            break

        self._state = SetupState.VALIDATE

    def _handle_validate(self) -> None:
        self._say("正在验证你的 API Key，请稍候...")
        print()

        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key, base_url=self._base_url, timeout=15.0)
            client.models.list()
        except Exception as ex:
            self._retries += 1
            if self._retries >= 3:
                self._say(
                    "API Key 验证已失败 3 次。API Key 似乎无效。"
                    "请检查后重新运行 agent setup。"
                )
                self._state = SetupState.DONE
                return

            msg = str(ex)
            prompt = (
                f"API Key 验证失败。错误信息: {msg}。"
                f"这是第 {self._retries} 次尝试（最多3次）。"
                "请用中文告知用户验证失败，并请他们重新输入 API Key。"
            )
            self._say(prompt)
            self._state = SetupState.ENTER_KEY
            return

        self._say("API Key 验证成功！正在保存配置...")
        self._save_config()
        self._retries = 0
        self._state = SetupState.DONE

    def _save_config(self) -> None:
        ensure_runtime_layout()
        os.environ[self._api_key_env] = self._api_key
        save_api_key(self._api_key_env, self._api_key)

        providers_file = AGENT_MODELS_DIR / "providers.yaml"
        providers = _load_yaml(providers_file).get("providers", [])
        if not isinstance(providers, list):
            providers = []

        target_name = "default-openai" if self._provider_type == "openai" else "default-custom"
        env_key_name = self._api_key_env

        updated = False
        for p in providers:
            if isinstance(p, dict) and p.get("name") == target_name:
                p["api_key_env"] = env_key_name
                p.pop("api_key", None)
                if self._base_url:
                    p["base_url"] = self._base_url
                updated = True
                break

        if not updated:
            providers.append({
                "name": target_name,
                "type": "openai-compatible",
                "base_url": self._base_url,
                "api_key_env": env_key_name,
            })

        import yaml

        providers_file.write_text(
            yaml.safe_dump({"providers": providers}, allow_unicode=True, default_flow_style=False),
            encoding="utf-8",
        )

        prompt = (
            f"配置已保存。请用中文告知用户:\n"
            f"- API Key 已验证有效\n"
            f"- 配置已写入 {providers_file}\n"
            f"- 密钥已写入本机 DPAPI 加密 keyring（.agent/security/keyring.json）\n"
            f"- 读取键名: {env_key_name}\n"
            f"- 下一步可以运行: agent task run --task '你的任务' --user <用户名> --role admin"
        )
        self._say(prompt)
