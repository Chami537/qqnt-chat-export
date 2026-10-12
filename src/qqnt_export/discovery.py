from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Callable, Iterable, Mapping

from .errors import SafeFailure
from .models import DatabaseSource


_INSTALL_VERSION = re.compile(r"^(\d+\.\d+\.\d+)(?:-[0-9]+)?$")


def infer_qq_version(executable: Path, wrapper_path: Path | None, fallback: str) -> str:
    if wrapper_path is not None:
        parts = wrapper_path.parts
        for index, part in enumerate(parts[:-1]):
            if part.casefold() == "versions":
                match = _INSTALL_VERSION.fullmatch(parts[index + 1])
                if match:
                    return match.group(1)
    versions = executable.parent / "versions"
    if versions.is_dir():
        found = [match.group(1) for item in versions.iterdir() if item.is_dir() if (match := _INSTALL_VERSION.fullmatch(item.name))]
        if len(found) == 1:
            return found[0]
    return fallback


def windows_qq_processes() -> list[dict[str, object]]:
    if os.name != "nt":
        raise SafeFailure("discovery", "windows_only", "此版本仅支持 Windows")
    script = (
        "Get-CimInstance Win32_Process -Filter \"Name = 'QQ.exe'\" | "
        "ForEach-Object { $p=$_.ExecutablePath; "
        "$v=if($p){(Get-Item -LiteralPath $p -ErrorAction SilentlyContinue).VersionInfo.ProductVersion}else{''}; "
        "$m=$null; try{$m=(Get-Process -Id $_.ProcessId -ErrorAction Stop).Modules | Where-Object {$_.ModuleName -eq 'wrapper.node'} | Select-Object -First 1}catch{}; "
        "$w=$null -ne $m; $mp=if($m){$m.FileName}else{''}; "
        "[pscustomobject]@{pid=$_.ProcessId;path=$p;version=$v;has_wrapper=$w;wrapper_path=$mp} } | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=20,
            check=True,
        )
        if not result.stdout.strip():
            return []
        parsed = json.loads(result.stdout)
        records = parsed if isinstance(parsed, list) else [parsed]
        for record in records:
            if record.get("path"):
                wrapper = Path(str(record["wrapper_path"])) if record.get("wrapper_path") else None
                record["version"] = infer_qq_version(Path(str(record["path"])), wrapper, str(record.get("version", "")))
        return records
    except (OSError, subprocess.SubprocessError, ValueError):
        raise SafeFailure("discovery", "process_query_failed", "无法读取本机 QQ 进程信息") from None


def default_data_roots() -> list[Path]:
    roots = [Path.home() / "Documents" / "Tencent Files"]
    configured = os.environ.get("QQNT_DATA_ROOT")
    if configured:
        roots.insert(0, Path(configured))
    return list(dict.fromkeys(root.resolve() for root in roots))


def discover_qq_installations(
    process_provider: Callable[[], Iterable[Mapping[str, object]]] = windows_qq_processes,
    data_roots: Iterable[Path] | None = None,
) -> list[DatabaseSource]:
    try:
        processes = list(process_provider())
    except SafeFailure:
        raise
    except Exception:
        raise SafeFailure("discovery", "process_query_failed", "无法读取本机 QQ 进程信息") from None
    if not processes:
        raise SafeFailure("discovery", "qq_not_running", "请先打开并登录 QQ")
    candidates: dict[str, tuple[DatabaseSource, bool]] = {}
    for root in data_roots if data_roots is not None else default_data_roots():
        if not root.is_dir():
            continue
        try:
            accounts = sorted(root.iterdir())
        except OSError:
            continue
        for account in accounts:
            db = account / "nt_qq" / "nt_db" / "nt_msg.db"
            if not account.is_dir() or not db.is_file():
                continue
            for process in processes:
                try:
                    pid = int(process["pid"])
                except (KeyError, TypeError, ValueError):
                    continue
                source = DatabaseSource(
                    db.resolve(), account.name, str(process.get("version", "")), pid,
                    Path(str(process["path"])) if process.get("path") else None,
                )
                key = str(db.resolve()).casefold()
                has_wrapper = bool(process.get("has_wrapper"))
                if key not in candidates or (has_wrapper, pid) > (candidates[key][1], candidates[key][0].process_id):
                    candidates[key] = (source, has_wrapper)
    if not candidates:
        raise SafeFailure("discovery", "database_not_found", "未找到 QQNT 数据库，请指定数据目录")
    return sorted((item[0] for item in candidates.values()), key=lambda item: (item.account, str(item.db_path)))


def choose_source(candidates: Iterable[DatabaseSource], account_hint: str | None) -> DatabaseSource:
    matching = [item for item in candidates if account_hint is None or item.account == account_hint]
    if not matching:
        raise SafeFailure("discovery", "account_not_found", "未找到指定 QQ 数据目录")
    if len(matching) != 1:
        raise SafeFailure("discovery", "ambiguous_account", "找到多个 QQ 数据目录，请使用 --account 选择")
    return matching[0]
