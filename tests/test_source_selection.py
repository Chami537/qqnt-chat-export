from pathlib import Path

import pytest

from qqnt_export import cli, source_selection
from qqnt_export.errors import SafeFailure
from qqnt_export.source_selection import find_sources


def _database(tmp_path: Path) -> Path:
    path = tmp_path / "Tencent Files" / "123456789" / "nt_qq" / "nt_db" / "nt_msg.db"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"synthetic")
    return path


def _processes() -> list[dict[str, object]]:
    return [
        {"pid": 7, "version": "9.9.27", "path": "D:/QQ/QQ.exe"},
        {"pid": 8, "version": "9.9.27", "path": "D:/QQ/QQ.exe"},
    ]


def test_manual_source_keeps_each_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _database(tmp_path)
    monkeypatch.setattr(source_selection, "windows_qq_processes", _processes)
    assert {item.process_id for item in find_sources(source_path=db)} == {7, 8}
    assert [item.process_id for item in find_sources(source_path=db, pid=8)] == [8]


def test_auto_discovery_keeps_each_process(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    db = _database(tmp_path)
    monkeypatch.setattr(source_selection, "windows_qq_processes", _processes)
    found = find_sources(data_root=db.parents[3])
    assert {(item.account, item.process_id) for item in found} == {
        ("123456789", 7), ("123456789", 8),
    }


def test_cli_requires_pid_for_ambiguous_process_without_exposing_account(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    db = _database(tmp_path)
    monkeypatch.setattr(source_selection, "windows_qq_processes", _processes)
    assert cli.main(["doctor", "--source", str(db)]) == 10
    error = capsys.readouterr().err
    assert "pid" in error.lower()
    assert "123456789" not in error


def test_missing_database_error_does_not_expose_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(source_selection, "windows_qq_processes", _processes)
    with pytest.raises(SafeFailure) as failure:
        find_sources(source_path=tmp_path / "private-name" / "nt_msg.db")
    assert "private-name" not in failure.value.public_message
