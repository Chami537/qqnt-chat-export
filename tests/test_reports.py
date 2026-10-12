import json
from pathlib import Path

from qqnt_export.reports import write_safe_report


def test_report_redacts_private_values(tmp_path: Path) -> None:
    output = tmp_path / "doctor.json"
    write_safe_report(output, {"account": "123456789", "message": "private text", "status": "ok"})
    report = json.loads(output.read_text(encoding="utf-8"))
    assert report == {"account": "[REDACTED]", "message": "[REDACTED]", "status": "ok"}


def test_report_rejects_private_text_in_safe_key(tmp_path: Path) -> None:
    output = tmp_path / "doctor.json"
    write_safe_report(output, {"status": "account 123456789 says private text"})
    assert "private text" not in output.read_text(encoding="utf-8")
