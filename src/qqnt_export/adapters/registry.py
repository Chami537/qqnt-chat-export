from __future__ import annotations

from collections.abc import Sequence

from qqnt_export.errors import SafeFailure
from qqnt_export.models import DatabaseSource

from .base import QQNTAdapter


def select_adapter(source: DatabaseSource, adapters: Sequence[QQNTAdapter]) -> QQNTAdapter:
    compatible = [adapter for adapter in adapters if adapter.probe(source).supported]
    if not compatible:
        raise SafeFailure("compatibility", "unsupported_version", "当前 QQ 版本或数据库格式暂不支持")
    if len(compatible) != 1:
        raise SafeFailure("compatibility", "ambiguous_adapter", "找到多个适配器，请报告兼容性问题")
    return compatible[0]
