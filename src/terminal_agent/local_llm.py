from __future__ import annotations

import atexit
import json
import os
import socket
import subprocess
import sys
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from terminal_agent.config import _load_yaml
from terminal_agent.paths import AGENT_MODELS_DIR, AGENT_RUNTIME_DIR

LLAMA_SERVER_DIR = AGENT_RUNTIME_DIR / "llama-server"
LLAMA_SERVER_EXE = LLAMA_SERVER_DIR / "llama-server.exe"

DEFAULT_MODEL_REPO = "unsloth/Qwen3-0.6B-GGUF"
DEFAULT_MODEL_FILE = "Qwen3-0.6B-Q4_K_M.gguf"
DEFAULT_MODEL_URL = (
    f"https://huggingface.co/{DEFAULT_MODEL_REPO}/resolve/main/{DEFAULT_MODEL_FILE}"
)

_server_process: subprocess.Popen | None = None
_server_port: int = 0
_server_model_name: str = ""


def _register_cleanup() -> None:
    atexit.register(_stop_server)


def _stop_server() -> None:
    global _server_process
    if _server_process is not None:
        try:
            _server_process.terminate()
            _server_process.wait(timeout=5)
        except Exception:
            try:
                _server_process.kill()
            except Exception:
                pass
        _server_process = None


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _download(url: str, dest: Path, desc: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    print(f"正在下载 {desc}...")
    print(f"  {url}")

    tmp = Path(str(dest) + ".part")

    last_pct = [-1]

    def _progress(block_count: int, block_size: int, total_size: int) -> None:
        if total_size <= 0:
            return
        downloaded = min(block_count * block_size, total_size)
        pct = min(downloaded * 100 // total_size, 100)
        if pct >= last_pct[0] + 10:
            last_pct[0] = pct
            print(f"  {pct}% ({downloaded / (1024*1024):.1f}/{total_size / (1024*1024):.1f} MB)")

    try:
        urllib.request.urlretrieve(url, str(tmp), _progress)
        tmp.rename(dest)
        print(f"  完成: {dest.name}")
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise


def _get_llama_release() -> tuple[str, str]:
    """返回 (version_tag, download_url) 用于最新 llama.cpp Windows x64 CPU 版本。"""
    print("正在查询 llama.cpp 最新版本...")
    api_url = "https://api.github.com/repos/ggml-org/llama.cpp/releases/latest"
    try:
        with urllib.request.urlopen(api_url, timeout=15) as resp:
            data = json.loads(resp.read().decode())
    except Exception as ex:
        raise RuntimeError(f"无法获取 llama.cpp 版本信息: {ex}")

    tag = data.get("tag_name", "")
    if not tag:
        raise RuntimeError("无法解析 llama.cpp 版本标签")

    for asset in data.get("assets", []):
        name = asset.get("name", "")
        if "win" in name.lower() and "x64" in name.lower():
            low = name.lower()
            if "cuda" not in low and "vulkan" not in low and "sycl" not in low and "hip" not in low:
                return tag, asset["browser_download_url"]

    raise RuntimeError(f"未在 release {tag} 中找到 Windows x64 CPU 二进制文件")


def _ensure_llama_server() -> Path:
    LLAMA_SERVER_DIR.mkdir(parents=True, exist_ok=True)

    if not LLAMA_SERVER_EXE.exists():
        _tag, url = _get_llama_release()
        zip_path = LLAMA_SERVER_DIR / "llama-server.zip"
        _download(url, zip_path, "llama-server")

        print("正在解压...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(LLAMA_SERVER_DIR)

        zip_path.unlink()

        # 确认 llama-server.exe 存在
        found = None
        for p in LLAMA_SERVER_DIR.rglob("llama-server.exe"):
            found = p
            break
        if not found:
            raise RuntimeError("zip 文件中未找到 llama-server.exe")

        # 如果在子目录中，移动到顶层
        if found.parent != LLAMA_SERVER_DIR:
            import shutil
            for item in found.parent.iterdir():
                dest = LLAMA_SERVER_DIR / item.name
                if not dest.exists():
                    shutil.move(str(item), str(dest))
            shutil.rmtree(str(found.parent))

        print("llama-server 就绪。")

    return LLAMA_SERVER_EXE


def _ensure_model() -> Path:
    cfg = _load_yaml(AGENT_MODELS_DIR / "local.yaml").get("local", {})
    if not isinstance(cfg, dict):
        cfg = {}
    model_file = str(cfg.get("model_file", DEFAULT_MODEL_FILE))
    model_url = str(cfg.get("model_url", "")) or DEFAULT_MODEL_URL
    model_dir = AGENT_MODELS_DIR / "local"
    model_path = model_dir / model_file

    if not model_path.exists():
        _download(model_url, model_path, f"模型 ({model_file})")

    return model_path


def _start_server(model_path: Path) -> int:
    global _server_process, _server_port

    exe = _ensure_llama_server()
    port = _find_free_port()

    print(f"正在启动 llama-server (端口 {port})...")
    proc = subprocess.Popen(
        [
            str(exe),
            "-m", str(model_path),
            "--host", "127.0.0.1",
            "--port", str(port),
            "-c", "4096",
            "-t", "4",
            "-np", "4",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _server_process = proc
    _server_port = port
    _register_cleanup()

    # 等待模型加载完成，最多等 60 秒
    deadline = time.time() + 60
    models_url = f"http://127.0.0.1:{port}/v1/models"
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server 意外退出，退出码: {proc.returncode}")
        try:
            with urllib.request.urlopen(models_url, timeout=2) as resp:
                data = json.loads(resp.read().decode())
                models = data.get("data", [])
                if models:
                    global _server_model_name
                    _server_model_name = models[0].get("id", "local-model")
                    print("llama-server 就绪。")
                    return port
        except Exception:
            pass
        time.sleep(1)

    raise RuntimeError("llama-server 启动超时（60秒）")


@dataclass
class LocalLLMConfig:
    model_name: str = "local-model"
    temperature: float = 0.7
    host: str = "http://127.0.0.1"


def load_local_config() -> LocalLLMConfig:
    cfg = _load_yaml(AGENT_MODELS_DIR / "local.yaml").get("local", {})
    if not isinstance(cfg, dict):
        cfg = {}
    model_name = _server_model_name or str(cfg.get("model_name", "local-model"))
    return LocalLLMConfig(
        model_name=model_name,
        temperature=float(cfg.get("temperature", 0.7)),
        host=f"http://127.0.0.1:{_server_port}" if _server_port else "http://127.0.0.1:0",
    )


def ensure_model_available(config: LocalLLMConfig | None = None) -> str | None:
    """
    确保本地模型和 llama-server 可用。返回 None 表示失败。
    """
    try:
        model_path = _ensure_model()
        _start_server(model_path)
        return "本地模型就绪。"
    except Exception as ex:
        _stop_server()
        print(f"本地模型启动失败: {ex}", file=sys.stderr)
        return None


class LocalLLM:
    """通过 urllib 调用 llama-server 的 OpenAI 兼容 API。"""

    def __init__(self, config: LocalLLMConfig) -> None:
        if _server_port == 0:
            raise RuntimeError("llama-server 未启动")
        self._config = config
        self._api_url = f"http://127.0.0.1:{_server_port}/v1/chat/completions"

    def _post(self, body: dict) -> dict:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        req = urllib.request.Request(
            self._api_url,
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return json.loads(resp.read().decode())  # type: ignore[no-any-return]

    def generate(self, system_prompt: str, user_prompt: str, max_tokens: int = 512) -> str:
        body: dict = {
            "model": self._config.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": self._config.temperature,
            "max_tokens": max_tokens,
        }
        result = self._post(body)
        content = result["choices"][0]["message"]["content"]
        return str(content).strip() if content else ""


def _api_call(body: dict) -> dict:
    """直接调用 llama-server API，用于 function calling 循环。"""
    url = f"http://127.0.0.1:{_server_port}/v1/chat/completions"
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode())  # type: ignore[no-any-return]


class UrllibClient:
    """极简 OpenAI 兼容客户端，用于 function calling 循环。"""

    def __init__(self) -> None:
        self.chat = _UrllibChat()


class _UrllibChat:
    def __init__(self) -> None:
        self.completions = _UrllibCompletions()


class _UrllibCompletions:
    def create(self, **kwargs) -> _UrllibResponse:  # type: ignore[no-untyped-def]
        body = {k: v for k, v in kwargs.items() if v is not None}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        url = f"http://127.0.0.1:{_server_port}/v1/chat/completions"
        req = urllib.request.Request(
            url, data=data, headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=120) as resp:
            return _UrllibResponse(json.loads(resp.read().decode()))


class _UrllibResponse:
    def __init__(self, data: dict) -> None:
        self.choices = [_UrllibChoice(c) for c in data.get("choices", [])]


class _UrllibChoice:
    def __init__(self, data: dict) -> None:
        self.message = _UrllibMessage(data.get("message", {}))


class _UrllibMessage:
    def __init__(self, data: dict) -> None:
        self.content = data.get("content", "")
        self.tool_calls = None
        tcs = data.get("tool_calls")
        if tcs:
            self.tool_calls = [
                _UrllibToolCall(tc) for tc in tcs
            ]


class _UrllibToolCall:
    def __init__(self, data: dict) -> None:
        self.id = data.get("id", "")
        self.type = data.get("type", "")
        self.function = _UrllibFunction(data.get("function", {}))


class _UrllibFunction:
    def __init__(self, data: dict) -> None:
        self.name = data.get("name", "")
        self.arguments = data.get("arguments", "")
