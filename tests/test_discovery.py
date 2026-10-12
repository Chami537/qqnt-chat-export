from pathlib import Path

import pytest

from qqnt_export.discovery import choose_source, discover_qq_installations
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
