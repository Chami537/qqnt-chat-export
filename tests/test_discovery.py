from pathlib import Path

import pytest

from qqnt_export.discovery import choose_source, discover_qq_installations, infer_qq_version
from qqnt_export.errors import SafeFailure
from qqnt_export.models import DatabaseSource


def source(account: str) -> DatabaseSource:
    return DatabaseSource(Path("E:/fake") / account / "nt_qq/nt_db/nt_msg.db", account, "9.9.27", 12)


def test_choose_source_rejects_ambiguous_accounts() -> None:
    with pytest.raises(SafeFailure, match="多个 QQ 数据目录"):
        choose_source([source("alpha"), source("beta")], account_hint=None)


def test_account_hint_selects_one_candidate() -> None:
    assert choose_source([source("alpha"), source("beta")], "beta").account == "beta"


def test_discovery_reads_candidate_without_modifying_it(tmp_path: Path) -> None:
    root = tmp_path / "Tencent Files"
    db = root / "12345" / "nt_qq" / "nt_db" / "nt_msg.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"QQ_NT DB")
    before = db.stat().st_mtime_ns
    processes = lambda: [{"pid": 7, "version": "9.9.27", "path": "E:/QQ.exe"}]
    found = discover_qq_installations(processes, [root])
    assert [(item.account, item.process_id) for item in found] == [("12345", 7)]
    assert db.stat().st_mtime_ns == before


def test_discovery_prefers_process_with_wrapper_module(tmp_path: Path) -> None:
    root = tmp_path / "Tencent Files"
    db = root / "12345" / "nt_qq" / "nt_db" / "nt_msg.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"QQ_NT DB")
    processes = lambda: [
        {"pid": 90, "version": "9.9.27", "path": "E:/QQ.exe", "has_wrapper": False},
        {"pid": 40, "version": "9.9.27", "path": "E:/QQ.exe", "has_wrapper": True},
    ]
    assert discover_qq_installations(processes, [root])[0].process_id == 40


def test_version_comes_from_running_wrapper_installation(tmp_path: Path) -> None:
    exe = tmp_path / "QQ.exe"
    exe.touch()
    wrapper = tmp_path / "versions" / "9.9.27-45758" / "resources" / "wrapper.node"
    wrapper.parent.mkdir(parents=True)
    wrapper.touch()
    assert infer_qq_version(exe, wrapper, "9.9.19.35469-older") == "9.9.27"
