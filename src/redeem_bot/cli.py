"""Typer CLI entry point for redeem-bot."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from typing import Optional

import typer

from redeem_bot.config import get_settings
from redeem_bot.discord import fetch_all_channels, fetch_channel
from redeem_bot.extract.test_command import run_extract_test
from redeem_bot.notify import fatal_error_handler
from redeem_bot.pipeline import (
    count_pending_codes,
    parse_code_list,
    redeem_manual_code,
    run_pipeline,
    skip_pending_backlog,
)
from redeem_bot.redeem.progress import format_redemption_status
from redeem_bot.storage.db import init_db
from redeem_bot.storage.status import (
    channel_cursors,
    count_successful_redemptions,
    count_tried_codes,
    last_run,
    tried_outcome_counts,
)
from redeem_bot.timeparse import parse_datetime

app = typer.Typer(
    name="redeem-bot",
    help="Cron-driven RisingHub promo code bot: fetch, extract, redeem.",
    no_args_is_help=True,
)
extract_app = typer.Typer(help="Code extraction commands.")
codes_app = typer.Typer(help="Tried-code management.")
app.add_typer(extract_app, name="extract")
app.add_typer(codes_app, name="codes")


def _bad_parameter(message: str) -> None:
    raise typer.BadParameter(message)


@app.command()
@fatal_error_handler
def fetch(
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="ISO date lower bound for message fetch.",
    ),
    channel_id: Optional[str] = typer.Option(
        None,
        "--channel-id",
        help="Fetch a single Discord channel ID.",
    ),
) -> None:
    """Pull Discord messages into the JSONL cache."""
    settings = get_settings()
    since_dt = parse_datetime(since) if since else None
    from_cursor = since is None

    if channel_id:
        result = fetch_channel(
            channel_id,
            since=since_dt,
            from_cursor=from_cursor,
            settings=settings,
        )
        results = [result]
    else:
        results = fetch_all_channels(
            since=since_dt,
            from_cursor=from_cursor,
            settings=settings,
        )

    for result in results:
        typer.echo(
            f"channel={result.channel_id} fetched={result.messages_fetched} "
            f"cached={result.messages_cached} pages={result.pages_fetched} "
            f"cursor={result.cursor_before}->{result.cursor_after} "
            f"stopped={result.stopped_reason}"
        )


@extract_app.command("test")
def extract_test(
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="ISO date lower bound for cached messages.",
    ),
    channel_id: Optional[str] = typer.Option(
        None,
        "--channel-id",
        help="Limit extraction to one channel.",
    ),
    from_cache: bool = typer.Option(
        False,
        "--from-cache",
        help="Read cached messages only (no Discord API).",
    ),
) -> None:
    """Print extraction report for manual review."""
    settings = get_settings()
    try:
        run_extract_test(
            settings,
            since=since,
            channel_id=channel_id,
            from_cache=from_cache,
        )
    except ValueError as exc:
        _bad_parameter(str(exc))


@app.command()
@fatal_error_handler
def redeem(
    code: str = typer.Option(
        ...,
        "--code",
        help="One promo code, or several comma-separated (no spaces required).",
    ),
    dry_run: bool = typer.Option(False, "--dry-run", help="Print actions without redeeming."),
    force: bool = typer.Option(
        False,
        "--force",
        help="Redeem even if this code was tried in a previous run.",
    ),
) -> None:
    """Manually redeem one or more promo codes."""
    settings = get_settings()
    codes = parse_code_list(code)
    if not codes:
        typer.echo("No codes provided.")
        raise typer.Exit(code=1)

    multi = len(codes) > 1

    def on_before(active_code: str, account: str, hero: str) -> None:
        prefix = f"[{active_code}] " if multi else ""
        typer.echo(f"{prefix}Trying {account} / {hero} ...")
        sys.stdout.flush()

    def on_result(result) -> None:
        typer.echo(f"  {format_redemption_status(result)}")
        sys.stdout.flush()

    any_failed = False

    for index, code_value in enumerate(codes):
        if multi:
            if index > 0:
                typer.echo("")
            typer.echo(f"--- {code_value} ---")

        outcome = redeem_manual_code(
            settings,
            code_value,
            dry_run=dry_run,
            force=force,
            on_before=on_before,
            on_result=on_result,
        )

        if outcome.skipped_reason == "already_tried":
            typer.echo(f"{outcome.code} already tried in a previous run (use --force to retry)")
            continue

        if outcome.probe is None:
            typer.echo(f"No hero worked for {outcome.code} ({outcome.skipped_reason})")
            if outcome.skipped_reason == "probe_failed":
                typer.echo(
                    "Hint: check RISINGHUB_BASE_URL, account credentials, and delete "
                    "stale data/sessions/<username>/cookies.json if login redirect loops persist."
                )
            any_failed = True
            continue

        if outcome.skipped_reason == "already_redeemed":
            typer.echo(f"{outcome.code}: already redeemed on all tried heroes")
            continue

        successes = [r for r in outcome.redemptions if r.success]
        typer.echo(
            f"{outcome.code}: redeemed on {len(successes)} hero/account combination(s)"
        )

    if any_failed:
        raise typer.Exit(code=1)


@codes_app.command("skip-backlog")
@fatal_error_handler
def codes_skip_backlog(
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="Same lower bound as run/extract (default: DISCORD_FETCH_SINCE).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="List pending codes without marking them tried.",
    ),
) -> None:
    """Mark all pending cache codes as tried so cron run skips the old backlog."""
    settings = get_settings()
    skipped = skip_pending_backlog(settings, since=since, dry_run=dry_run)

    if dry_run:
        typer.echo(f"Would skip {len(skipped)} pending code(s):")
    else:
        typer.echo(f"Marked {len(skipped)} pending code(s) as skipped_backlog.")

    for code in skipped:
        typer.echo(f"  {code}")

    if not dry_run:
        pending = count_pending_codes(settings)
        typer.echo(f"Pending codes remaining: {pending}")


@app.command()
@fatal_error_handler
def run(
    dry_run: bool = typer.Option(False, "--dry-run", help="Simulate redemption without HTTP."),
    from_cache: bool = typer.Option(
        False,
        "--from-cache",
        help="Skip Discord fetch; use cached messages.",
    ),
    since: Optional[str] = typer.Option(
        None,
        "--since",
        help="ISO date lower bound when reading cached messages.",
    ),
) -> None:
    """Full pipeline: fetch → extract → redeem everywhere."""
    settings = get_settings()

    def on_before(code: str, account: str, hero: str) -> None:
        typer.echo(f"Trying {code} on {account} / {hero} ...")
        sys.stdout.flush()

    def on_result(result) -> None:
        typer.echo(f"  {format_redemption_status(result)}")
        sys.stdout.flush()

    result = run_pipeline(
        settings,
        dry_run=dry_run,
        from_cache=from_cache,
        since=since,
        on_before=on_before,
        on_result=on_result,
    )

    typer.echo(result.summary)
    if result.skipped_already_tried:
        typer.echo(f"  skipped {result.skipped_already_tried} already-tried code(s)")
    if result.fetch_results:
        for fetch_result in result.fetch_results:
            typer.echo(
                f"  fetch channel={fetch_result.channel_id} "
                f"cached={fetch_result.messages_cached}"
            )

    for item in result.processed:
        if item.skipped_reason:
            typer.echo(f"  {item.code}: skipped ({item.skipped_reason})")
            continue
        hero = item.probe.hero_name if item.probe else "?"
        accounts = [item.probe.account_username] if item.probe else []
        accounts.extend(result_item.account_username for result_item in item.redemptions)
        typer.echo(f"  {item.code}: hero={hero} accounts={', '.join(accounts)}")

    for code in result.skipped_tried_codes:
        typer.echo(f"  {code}: skipped (already_tried)")


@app.command()
def status() -> None:
    """Show channel cursors, pending code counts, and last run time."""
    settings = get_settings()
    settings.ensure_data_dirs()
    init_db(settings.state_db_path)

    db_path = settings.state_db_path
    seen_count = count_tried_codes(db_path)
    outcomes = tried_outcome_counts(db_path)
    success_count = count_successful_redemptions(db_path)
    cursors = channel_cursors(db_path)
    last_run_row = last_run(db_path)
    pending = count_pending_codes(settings)

    typer.echo(f"State database: {db_path}")
    typer.echo(f"Tried codes: {seen_count}")
    typer.echo(f"Pending codes (cache, not tried): {pending}")
    typer.echo(f"Successful redemptions: {success_count}")
    if outcomes:
        typer.echo("Tried by outcome:")
        for row in outcomes:
            typer.echo(f"  {row.outcome}: {row.count}")
    typer.echo(f"Configured channels: {len(settings.channel_id_list)}")

    if cursors:
        typer.echo("\nChannel cursors:")
        for row in cursors:
            typer.echo(
                f"  {row.channel_id}: last_message_id={row.last_message_id or '(none)'} "
                f"updated_at={row.updated_at}"
            )
    else:
        typer.echo("\nChannel cursors: (none)")

    if last_run_row:
        typer.echo(
            f"\nLast run: command={last_run_row.command} status={last_run_row.status} "
            f"started={last_run_row.started_at} "
            f"finished={last_run_row.finished_at or '(running)'}"
        )
        if last_run_row.summary:
            typer.echo(f"  summary: {last_run_row.summary}")
    else:
        typer.echo(f"\nLast run: (none) — checked at {datetime.now(timezone.utc).isoformat()}")
