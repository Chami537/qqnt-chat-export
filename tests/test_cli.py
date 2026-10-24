import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from qqnt_export import cli, services
from qqnt_export.adapters.qqnt_9_9_27 import QQNT9927Adapter
from qqnt_export.errors import SafeFailure
from qqnt_export.models import DatabaseSource

from fixtures.synthetic_messages import text_body


def test_export_requires_one_conversation_selector(tmp_path: Path) -> None:
    assert cli.main(["export", "--output", str(tmp_path)]) == 2


def test_safe_failure_maps_to_stage_exit_code(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    def fail(_args):
        raise SafeFailure("snapshot", "source_changed", "请重试")

    monkeypatch.setattr(cli, "run_export", fail)
    assert cli.main(["export", "--peer", "123", "--output", str(tmp_path)]) == 12
    assert "123" not in capsys.readouterr().err


def test_help_lists_all_public_commands(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["--help"]) == 0
    output = capsys.readouterr().out
    assert all(command in output for command in ("doctor", "conversations", "export", "recover", "cleanup"))


def test_recover_requires_selector_and_dispatches(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    assert cli.main(["recover", "--output", str(tmp_path)]) == 2
    called = []
    monkeypatch.setattr(cli, "run_recover", lambda args: called.append(args.peer) or 0)
    assert cli.main(["recover", "--peer", "123", "--output", str(tmp_path)]) == 0
    assert called == ["123"]


def test_one_command_export_uses_snapshot_and_cleans_workspace(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source_path = tmp_path / "123456789" / "nt_qq" / "nt_db" / "nt_msg.db"
    source_path.parent.mkdir(parents=True)
    header = bytearray(1024)
    header[:16] = b"SQLite header 3\x00"
    header[32:40] = b"QQ_NT DB"
    source_path.write_bytes(header + b"X" * 4096)
    original = source_path.read_bytes()
    output = tmp_path / "exports"
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))
    monkeypatch.setattr(cli, "_source_from_args", lambda args: DatabaseSource(source_path, "123456789", "9.9.27", 7))

    class FixedKey:
        def get_key(self, source, encrypted):
            return bytearray(b"synthetic-password")

    monkeypatch.setattr(services, "ProcessMemoryKeyProvider", lambda config: FixedKey())

    def fake_cipher(encrypted, destination, key, config):
        assert encrypted.read_bytes() == b"X" * 4096
        with closing(sqlite3.connect(destination)) as connection:
            for table in ("c2c_msg_table", "group_msg_table"):
                connection.execute(f'CREATE TABLE {table} ("40001" INTEGER, "40013" INTEGER, "40021" INTEGER, "40030" INTEGER, "40033" INTEGER, "40050" INTEGER, "40800" BLOB)')
            connection.execute('INSERT INTO c2c_msg_table VALUES (1, 0, 0, 987654321, 123456789, 1767270600, ?)', (text_body("synthetic hello"),))
            connection.commit()

    from qqnt_export.decrypt import decrypt_snapshot as actual_decrypt
    monkeypatch.setattr(services, "decrypt_snapshot", lambda snapshot, source, workspace, adapter, provider: actual_decrypt(snapshot, source, workspace, adapter, provider, cipher_executor=fake_cipher))
    assert cli.main(["export", "--peer", "987654321", "--output", str(output)]) == 0
    folders = list(output.glob("c2c_*"))
    assert len(folders) == 1
    records = json.loads((folders[0] / "chat_export.json").read_text(encoding="utf-8"))
    assert len(records) == 1 and records[0]["content"] == "synthetic hello"
    assert source_path.read_bytes() == original
    assert not list(output.rglob("*.db"))
    terminal = capsys.readouterr().out
    assert "123456789" not in terminal and "987654321" not in terminal


def test_export_rejects_source_tree_output_without_creating_it(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    source_root = tmp_path / "synthetic-account"
    source_root.mkdir()
    source_path = source_root / "nt_qq" / "nt_db" / "nt_msg.db"
    output = source_root / "new-exports"
    monkeypatch.setattr("qqnt_export.paths.system_drive", lambda: Path("Z:/"))
    monkeypatch.setattr(cli, "_source_from_args", lambda args: DatabaseSource(source_path, "synthetic", "9.9.27", 7))
    monkeypatch.setattr(cli, "_select_adapter", lambda source, output: QQNT9927Adapter())
    assert cli.main(["export", "--peer", "123", "--output", str(output)]) == 16
    assert not output.exists()
