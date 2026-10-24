from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .adapters.qqnt_9_9_27 import QQNT9927Adapter
from .adapters.registry import select_adapter
from .conversations import build_conversation_index, iter_selected_messages, resolve_conversation
from .errors import SafeFailure
from .exporters import export_conversation
from .models import DatabaseSource, ExportResult
from .paths import system_drive, validate_non_system_directory
from .reports import write_safe_report
from .recovery import recover_selected_conversation
from .services import open_working_database
from .source_selection import find_sources
from .workspace import Workspace, cleanup_marked_workspace


EXIT_CODES = {
    "usage": 2, "paths": 16, "workspace": 16, "discovery": 10,
    "compatibility": 11, "snapshot": 12, "decrypt": 13,
    "schema": 14, "parse": 14, "conversation": 15,
    "output": 16, "cleanup": 17,
}


class SafeParser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise SafeFailure("usage", "invalid_arguments", "参数无效，请运行 qqnt-export --help")


def build_parser() -> argparse.ArgumentParser:
    parser = SafeParser(prog="qqnt-export", description="本地只读导出 QQNT 聊天记录")
    sub = parser.add_subparsers(dest="command", required=True, parser_class=SafeParser)

    def add_source_options(command: argparse.ArgumentParser) -> None:
        command.add_argument("--source", type=Path, help="自定义 nt_msg.db 路径")
        command.add_argument("--data-root", type=Path, help="自定义 Tencent Files 目录")
        command.add_argument("--account", help="多个账号时选择此账号")
        command.add_argument("--pid", type=int, help="多个 QQ 进程时选择此进程")

    doctor = sub.add_parser("doctor", help="检查 QQ 版本和数据目录，不复制聊天数据")
    add_source_options(doctor)
    doctor.add_argument("--output", type=Path, help="可选的脱敏报告目录")

    conversations = sub.add_parser("conversations", help="生成本地会话索引")
    add_source_options(conversations)
    conversations.add_argument("--output", type=Path, required=True)
    conversations.add_argument("--work-dir", type=Path)
    conversations.add_argument("--keep-workdir", action="store_true")

    export = sub.add_parser("export", help="一条命令导出选中的会话")
    add_source_options(export)
    selector = export.add_mutually_exclusive_group(required=True)
    selector.add_argument("--peer", help="私聊对象 QQ 号")
    selector.add_argument("--group", help="群号")
    export.add_argument("--output", type=Path, required=True)
    export.add_argument("--work-dir", type=Path)
    export.add_argument("--keep-workdir", action="store_true")

    recover = sub.add_parser("recover", help="整库校验失败时按号码读取单条会话")
    add_source_options(recover)
    recover_selector = recover.add_mutually_exclusive_group(required=True)
    recover_selector.add_argument("--peer", help="私聊对象 QQ 号")
    recover_selector.add_argument("--group", help="群号")
    recover.add_argument("--output", type=Path, required=True)
    recover.add_argument("--work-dir", type=Path)

    cleanup = sub.add_parser("cleanup", help="删除工具创建的工作目录")
    cleanup.add_argument("--work-dir", type=Path, required=True)
    return parser


def _source_from_args(args: argparse.Namespace) -> DatabaseSource:
    candidates = find_sources(args.source, args.data_root, args.pid)
    if args.account is not None:
        candidates = [item for item in candidates if item.account == args.account]
    if not candidates:
        raise SafeFailure("discovery", "account_not_found", "指定账号与数据库路径不一致")
    if len(candidates) > 1:
        if len({item.account for item in candidates}) > 1:
            raise SafeFailure("discovery", "ambiguous_account", "找到多个 QQ 数据目录，请使用 --account 选择")
        raise SafeFailure("discovery", "ambiguous_process", "找到多个 QQ 进程，请使用 --pid 选择")
    return candidates[0]


def _select_adapter(source: DatabaseSource, output: Path | None = None) -> QQNT9927Adapter:
    try:
        return select_adapter(source, [QQNT9927Adapter()])
    except SafeFailure:
        if output is not None:
            write_safe_report(output / "compatibility_report.json", {
                "stage": "compatibility", "code": "unsupported_version", "qq_version": source.qq_version,
                "adapter": "qqnt_9_9_27_windows", "status": "unsupported",
            })
        raise


def run_doctor(args: argparse.Namespace) -> int:
    source = _source_from_args(args)
    output = validate_non_system_directory(args.output, source_root=source.db_path.parents[2]) if args.output is not None else None
    adapter = _select_adapter(source, output)
    if output is not None:
        write_safe_report(output / "doctor_report.json", {
            "stage": "discovery", "code": "compatible", "qq_version": source.qq_version,
            "adapter": adapter.name, "status": "supported",
        })
    print("找到受支持的 QQNT 数据库。")
    return 0


def _prepare(args: argparse.Namespace):
    source = _source_from_args(args)
    source_root = source.db_path.parents[2]
    output = validate_non_system_directory(args.output, source_root=source_root)
    adapter = _select_adapter(source, output)
    workspace = Workspace.create(output, args.work_dir, keep=args.keep_workdir, source_root=source_root)
    return output, source, adapter, workspace


def _open_working_database(source: DatabaseSource, adapter: QQNT9927Adapter, workspace: Workspace):
    def show_stage(stage: str) -> None:
        if stage == "wait_qq_exit":
            print("密钥已验证。请正常退出 QQ，程序会自动继续；按 Ctrl+C 可取消。", file=sys.stderr, flush=True)

    return open_working_database(source, adapter, workspace, on_stage=show_stage)


def run_conversations(args: argparse.Namespace) -> int:
    output, source, adapter, workspace = _prepare(args)
    try:
        connection = _open_working_database(source, adapter, workspace)
        try:
            index = build_conversation_index(connection, adapter)
        finally:
            connection.close()
        destination = output / "conversation_index.json"
        if destination.exists():
            raise SafeFailure("output", "already_exists", "会话索引已存在，请另选输出目录")
        with destination.open("x", encoding="utf-8") as handle:
            json.dump([{"kind": item.kind, "selector": item.selector, "title": item.title, "message_count": item.message_count} for item in index], handle, ensure_ascii=False, indent=2)
        print(f"已生成 {len(index)} 个会话的索引：conversation_index.json")
        return 0
    finally:
        workspace.close(success=True)


def run_export(args: argparse.Namespace) -> ExportResult:
    output, source, adapter, workspace = _prepare(args)
    try:
        connection = _open_working_database(source, adapter, workspace)
        try:
            index = build_conversation_index(connection, adapter)
            conversation = resolve_conversation(index, args.peer, args.group)
            messages = iter_selected_messages(connection, adapter, conversation, source.account)
            result = export_conversation(output, conversation, messages)
        finally:
            connection.close()
        write_safe_report(result.json_path.parent / "export_report.json", {
            "stage": "output", "code": "complete", "qq_version": source.qq_version,
            "adapter": adapter.name, "status": "complete", "message_count": result.message_count,
            "quick_check": "ok",
        })
        print(f"已导出 {result.message_count} 条消息。目录：{result.json_path.parent.name}")
        return result
    finally:
        workspace.close(success=True)


def run_recover(args: argparse.Namespace) -> int:
    source = _source_from_args(args)
    kind, selector = ("c2c", args.peer) if args.peer else ("group", args.group)

    def show_stage(stage: str) -> None:
        if stage == "wait_qq_exit":
            print("密钥已验证。请正常退出 QQ，程序会继续读取稳定副本；按 Ctrl+C 可取消。", file=sys.stderr, flush=True)

    result = recover_selected_conversation(
        source, args.work_dir or args.output, args.output, kind, selector,
        should_cancel=lambda: False, on_stage=show_stage,
    )
    print(f"已按号码导出 {result.message_count} 条消息。目录：{result.json_path.parent.name}")
    print("注意：仅验证了所选会话可读取，未验证整库完整性。", file=sys.stderr)
    return 0


def run_cleanup(args: argparse.Namespace) -> int:
    path = args.work_dir.expanduser()
    if path.resolve().drive.casefold() == system_drive().drive.casefold():
        raise SafeFailure("cleanup", "system_drive", "工作目录不能位于系统盘")
    cleanup_marked_workspace(path)
    print("工作目录已清理。")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    try:
        args = build_parser().parse_args(argv)
        if args.command == "doctor":
            return run_doctor(args)
        if args.command == "conversations":
            return run_conversations(args)
        if args.command == "cleanup":
            return run_cleanup(args)
        if args.command == "recover":
            return run_recover(args)
        run_export(args)
        return 0
    except SafeFailure as failure:
        print(f"{failure.stage}: {failure.public_message}", file=sys.stderr)
        return EXIT_CODES.get(failure.stage, 70)
    except SystemExit as exit_signal:
        return int(exit_signal.code)
    except Exception:
        print("internal: 操作未完成；请运行 doctor 生成安全诊断", file=sys.stderr)
        return 70


if __name__ == "__main__":
    raise SystemExit(main())
