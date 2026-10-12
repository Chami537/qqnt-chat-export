from pathlib import Path

import pytest

from qqnt_export.adapters.registry import select_adapter
from qqnt_export.errors import SafeFailure
from qqnt_export.models import CompatibilityResult, DatabaseSource


class StubAdapter:
    def __init__(self, name: str, supported: bool) -> None:
        self.name = name
        self.supported = supported

    def probe(self, source: DatabaseSource) -> CompatibilityResult:
        return CompatibilityResult(self.supported, self.name, "ok" if self.supported else "unsupported_version")


def source() -> DatabaseSource:
    return DatabaseSource(Path("E:/fake/nt_msg.db"), "abc", "9.9.27", 3)


def test_select_adapter_rejects_unsupported_version() -> None:
    with pytest.raises(SafeFailure, match="暂不支持"):
        select_adapter(source(), [StubAdapter("old", False)])


def test_select_adapter_rejects_multiple_compatible_adapters() -> None:
    with pytest.raises(SafeFailure, match="多个适配器"):
        select_adapter(source(), [StubAdapter("first", True), StubAdapter("second", True)])


def test_select_adapter_returns_single_match() -> None:
    assert select_adapter(source(), [StubAdapter("first", True)]).name == "first"
