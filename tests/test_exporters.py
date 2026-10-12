import json
import hashlib
import os
import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from qqnt_export.conversations import ConversationIndexEntry
from qqnt_export.errors import SafeFailure
from qqnt_export.exporters import export_conversation
from qqnt_export.models import NormalizedMessage


TZ = timezone(timedelta(hours=8))


def conversation(title: str = "测试会话") -> ConversationIndexEntry:
    return ConversationIndexEntry("c2c", "255", title, 2)


def two_messages():
    yield NormalizedMessage(datetime(2026, 1, 1, 20, 30, tzinfo=TZ), "self", "text", "你好", message_id="1")
    yield NormalizedMessage(datetime(2026, 1, 2, 20, 31, tzinfo=TZ), "peer", "text", "晚上吃饭吗？", message_id="2")


def test_export_creates_json_and_date_grouped_markdown(tmp_path: Path) -> None:
    result = export_conversation(tmp_path, conversation(), two_messages())
    records = json.loads(result.json_path.read_text(encoding="utf-8"))
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert result.message_count == 2
    assert records[0]["time"] == "2026-01-01T20:30:00+08:00"
    assert records[0]["content"] == "你好"
    assert "## 2026-01-01" in markdown and "## 2026-01-02" in markdown
    assert "20:30 我：\n你好" in markdown


def test_title_cannot_escape_directory_or_add_heading(tmp_path: Path) -> None:
    result = export_conversation(tmp_path, conversation("../# injected\n# second"), two_messages())
    markdown = result.markdown_path.read_text(encoding="utf-8")
    assert result.markdown_path.parent.parent == tmp_path
    assert sum(line.startswith("# ") for line in markdown.splitlines()) == 1


def test_unknown_payload_has_metadata_and_marker_without_bytes(tmp_path: Path) -> None:
    message = NormalizedMessage(None, "peer", "unknown", None, {"byte_length": 4, "sha256_prefix": "abcd", "fields": []})
    result = export_conversation(tmp_path, conversation(), [message])
    records = json.loads(result.json_path.read_text(encoding="utf-8"))
    assert records[0]["content"] is None
    assert records[0]["raw_fallback"]["byte_length"] == 4
    assert "[未识别消息结构]" in result.markdown_path.read_text(encoding="utf-8")


def test_export_refuses_existing_destination(tmp_path: Path) -> None:
    export_conversation(tmp_path, conversation(), two_messages())
    with pytest.raises(SafeFailure, match="已存在"):
        export_conversation(tmp_path, conversation(), two_messages())


def test_export_refuses_linked_conversation_directory(tmp_path: Path) -> None:
    output = tmp_path / "output"
    target = tmp_path / "outside"
    output.mkdir()
    target.mkdir()
    digest = hashlib.sha256(b"255").hexdigest()[:12]
    link = output / f"c2c_{digest}"
    try:
        link.symlink_to(target, target_is_directory=True)
    except (OSError, NotImplementedError):
        if os.name != "nt":
            pytest.skip("directory links unavailable")
        result = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(target)], capture_output=True)
        if result.returncode:
            pytest.skip("directory junctions unavailable")
    with pytest.raises(SafeFailure):
        export_conversation(output, conversation(), two_messages())
    assert not list(target.iterdir())
