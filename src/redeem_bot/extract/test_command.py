"""CLI helpers for `redeem-bot extract test`."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import typer

from redeem_bot.config import Settings
from redeem_bot.extract.extractor import codes_with_authors, extract_from_messages, unique_codes
from redeem_bot.extract.models import ExtractReport, MessageExtraction
from redeem_bot.timeparse import parse_since


def _extraction_to_dict(extraction: MessageExtraction) -> dict:
    return {
        "message_id": extraction.message_id,
        "channel_id": extraction.channel_id,
        "timestamp": extraction.timestamp.isoformat(),
        "author": extraction.author,
        "message_snippet": extraction.message_snippet,
        "extracted_codes": [
            {
                "raw_text": code.raw_text,
                "normalized_code": code.normalized_code,
                "hints": code.hints_dict,
            }
            for code in extraction.extracted_codes
        ],
        "rejected_candidates": extraction.rejected_candidates,
    }


def report_to_dict(report: ExtractReport) -> dict:
    return {
        "messages_processed": report.messages_processed,
        "extractions": [_extraction_to_dict(item) for item in report.extractions],
    }


def write_codes_list(report: ExtractReport, reports_dir: Path) -> Path:
    """Write one code per line with author: ``CODE<TAB>author``."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = reports_dir / f"extract-codes-{date_label}.txt"
    lines = [f"{code}\t{author}" for code, author in codes_with_authors(report)]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    return path


def write_extract_report(report: ExtractReport, reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    date_label = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = reports_dir / f"extract-{date_label}.json"
    path.write_text(
        json.dumps(report_to_dict(report), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def print_extract_table(report: ExtractReport) -> None:
    if not report.extractions:
        typer.echo("No messages matched the since filter.")
        return

    typer.echo(
        f"{'timestamp':<26} {'author':<16} {'codes':<28} snippet"
    )
    typer.echo("-" * 100)
    for extraction in report.extractions:
        codes = ", ".join(code.normalized_code for code in extraction.extracted_codes) or "(none)"
        rejected = ", ".join(extraction.rejected_candidates)
        if rejected:
            codes = f"{codes} [rejected: {rejected}]" if codes != "(none)" else f"(rejected: {rejected})"
        typer.echo(
            f"{extraction.timestamp.isoformat():<26} "
            f"{extraction.author:<16} "
            f"{codes:<28} "
            f"{extraction.message_snippet}"
        )


def run_extract_test(
    settings: Settings,
    *,
    since: str | None,
    channel_id: str | None,
    from_cache: bool,
) -> ExtractReport:
    settings.ensure_data_dirs()
    since_dt = parse_since(since, settings)
    messages = load_messages(
        settings,
        since=since_dt,
        channel_id=channel_id,
        from_cache=from_cache,
    )
    report = extract_from_messages(messages, since=since_dt)
    print_extract_table(report)
    reports_dir = settings.data_dir / "reports"
    report_path = write_extract_report(report, reports_dir)
    codes_path = write_codes_list(report, reports_dir)
    typer.echo(f"\nReport written to {report_path}")
    typer.echo(f"Codes list ({len(codes_with_authors(report))} entries, {len(unique_codes(report))} unique): {codes_path}")
    return report
