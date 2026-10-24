import json
from pathlib import Path

import pytest

from qqnt_export.models import DatabaseSource
from qqnt_export import recovery
from fixtures.synthetic_messages import text_body


def test_recover_selected_c2c_without_group_table(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    cipher = pytest.importorskip("sqlcipher3.dbapi2")
    encrypted = tmp_path / "encrypted.db"
    config = recovery.QQNT9927Adapter().decrypt_config()
    with cipher.connect(encrypted) as db:
        db.execute(f"PRAGMA cipher_page_size={config.page_size}")
        db.execute("PRAGMA key='test-password'")
        db.execute(f"PRAGMA kdf_iter={config.kdf_iter}")
        db.execute(f"PRAGMA cipher_hmac_algorithm={config.hmac_algorithm}")
        db.execute(f"PRAGMA cipher_kdf_algorithm={config.kdf_algorithm}")
        db.execute('CREATE TABLE c2c_msg_table ("40001" INTEGER, "40013" INTEGER, "40030" INTEGER, "40033" INTEGER, "40050" INTEGER, "40800" BLOB)')
        db.execute('INSERT INTO c2c_msg_table VALUES (1, 0, 987654321, 123456789, 1767270600, ?)', (text_body("hello"),))
        db.commit()
    source_db = tmp_path / "account" / "nt_qq" / "nt_db" / "nt_msg.db"
    source_db.parent.mkdir(parents=True)
    header = bytearray(1024)
    header[:16] = b"SQLite header 3\x00"
    header[32:40] = b"QQ_NT DB"
    source_db.write_bytes(header + encrypted.read_bytes())
    original = source_db.read_bytes()
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))
    monkeypatch.setattr(recovery, "acquire_key_before_exit", lambda *args: bytearray(b"test-password"))
    monkeypatch.setattr(recovery, "wait_for_qq_exit", lambda *args: None)
    stages = []

    result = recovery.recover_selected_conversation(
        DatabaseSource(source_db, "123456789", "9.9.27", 7),
        tmp_path / "work", tmp_path / "out", "c2c", "987654321",
        should_cancel=lambda: False, on_stage=stages.append,
    )

    records = json.loads(result.json_path.read_text(encoding="utf-8"))
    report = json.loads((result.json_path.parent / "export_report.json").read_text(encoding="utf-8"))
    assert len(records) == result.message_count == 1
    assert records[0]["content"] == "hello"
    assert report["code"] == "selected_only"
    assert report["status"] == "partial"
    assert report["quick_check"] == "not_run"
    assert source_db.read_bytes() == original
    assert not list((tmp_path / "work").rglob("*.db"))
    assert "wait_qq_exit" in stages


def test_recovery_rejects_invalid_selector_before_copy(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = DatabaseSource(tmp_path / "nt_msg.db", "123", "9.9.27", 7)
    with pytest.raises(Exception):
        recovery.recover_selected_conversation(
            source, tmp_path / "work", tmp_path / "out", "c2c", "not-a-number",
            should_cancel=lambda: False, on_stage=lambda stage: None,
        )
    assert not (tmp_path / "work").exists()
