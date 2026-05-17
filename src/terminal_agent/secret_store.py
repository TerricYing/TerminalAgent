from __future__ import annotations

import base64
import ctypes
import json
from ctypes import POINTER, Structure, byref, c_char, c_void_p, c_wchar_p, cast
from pathlib import Path

from terminal_agent.paths import AGENT_SECURITY_DIR, ensure_runtime_layout


class _DataBlob(Structure):
    _fields_ = [("cbData", ctypes.c_uint32), ("pbData", POINTER(c_char))]


def _to_blob(data: bytes) -> _DataBlob:
    buffer = ctypes.create_string_buffer(data)
    return _DataBlob(len(data), cast(buffer, POINTER(c_char)))


def _from_blob(blob: _DataBlob) -> bytes:
    return ctypes.string_at(blob.pbData, blob.cbData)


def _crypt_protect(data: bytes) -> bytes:
    in_blob = _to_blob(data)
    out_blob = _DataBlob()
    if not ctypes.windll.crypt32.CryptProtectData(  # type: ignore[attr-defined]
        byref(in_blob),
        c_wchar_p("TerminalAgentKey"),
        c_void_p(),
        c_void_p(),
        c_void_p(),
        0,
        byref(out_blob),
    ):
        raise RuntimeError("DPAPI 加密失败")
    try:
        return _from_blob(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)  # type: ignore[attr-defined]


def _crypt_unprotect(data: bytes) -> bytes:
    in_blob = _to_blob(data)
    out_blob = _DataBlob()
    if not ctypes.windll.crypt32.CryptUnprotectData(  # type: ignore[attr-defined]
        byref(in_blob),
        c_void_p(),
        c_void_p(),
        c_void_p(),
        c_void_p(),
        0,
        byref(out_blob),
    ):
        raise RuntimeError("DPAPI 解密失败")
    try:
        return _from_blob(out_blob)
    finally:
        ctypes.windll.kernel32.LocalFree(out_blob.pbData)  # type: ignore[attr-defined]


def _keyring_file() -> Path:
    ensure_runtime_layout()
    return AGENT_SECURITY_DIR / "keyring.json"


def save_api_key(key_name: str, key_value: str) -> None:
    if not key_name or not key_value:
        raise ValueError("key_name 和 key_value 不能为空")

    path = _keyring_file()
    data: dict[str, object]
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    keys = data.get("keys")
    if not isinstance(keys, dict):
        keys = {}

    encrypted = _crypt_protect(key_value.encode("utf-8"))
    keys[key_name] = base64.b64encode(encrypted).decode("ascii")
    data["version"] = 1
    data["keys"] = keys

    path.write_text(json.dumps(data, ensure_ascii=True, indent=2), encoding="utf-8")


def load_api_key(key_name: str) -> str:
    path = _keyring_file()
    if not path.exists():
        return ""

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return ""

    keys = data.get("keys")
    if not isinstance(keys, dict):
        return ""

    raw = keys.get(key_name)
    if not isinstance(raw, str) or not raw:
        return ""

    try:
        encrypted = base64.b64decode(raw.encode("ascii"), validate=True)
        plain = _crypt_unprotect(encrypted)
        return plain.decode("utf-8").strip()
    except Exception:
        return ""
