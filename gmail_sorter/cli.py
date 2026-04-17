"""Command-line interface for gmail-sorter."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click

from gmail_sorter.config.loader import load_config
from gmail_sorter.config.models import AppConfig
from gmail_sorter.db.repository import Database

if TYPE_CHECKING:
    from gmail_sorter.classifier.engine import ClassificationEngine
    from gmail_sorter.gmail.client import GmailClient
    from gmail_sorter.llm.client import LlmClient
    from gmail_sorter.observability.metrics import MetricsCollector


@dataclass(slots=True)
class RuntimeOptions:
    """Global CLI options shared across subcommands."""

    config_path: Path
    dry_run: bool
    log_level: str | None


@click.group()
@click.option(
    "--config",
    "config_path",
    default="./config.yaml",
    show_default=True,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Path to the configuration file.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Override config to enable dry-run mode.",
)
@click.option(
    "--log-level",
    default=None,
    type=click.Choice(["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]),
    help="Override the configured log level.",
)
@click.version_option(version="1.0.0")
@click.pass_context
def main(ctx: click.Context, config_path: Path, dry_run: bool, log_level: str | None) -> None:
    """Run the gmail-sorter CLI."""

    ctx.obj = RuntimeOptions(config_path=config_path, dry_run=dry_run, log_level=log_level)


@main.command()
@click.option("--backfill", "run_backfill", is_flag=True, help="Run backfill alongside listener startup.")
@click.pass_obj
def run(options: RuntimeOptions, run_backfill: bool) -> None:
    """Start real-time Pub/Sub classification listener."""

    config = _load_runtime_config(options)
    from gmail_sorter.observability import configure_logging

    configure_logging(config.logging.level, config.logging.log_prompts)

    try:
        asyncio.run(_run_service(config, run_backfill=run_backfill))
    except KeyboardInterrupt:
        return


@main.command()
@click.pass_obj
def backfill(options: RuntimeOptions) -> None:
    """Run one-time full mailbox backfill and exit."""

    config = _load_runtime_config(options)
    from gmail_sorter.observability import configure_logging

    configure_logging(config.logging.level, config.logging.log_prompts)
    asyncio.run(_run_backfill_only(config))


@main.command("validate-config")
@click.option(
    "--config",
    "config_path_override",
    default=None,
    type=click.Path(path_type=Path, dir_okay=False),
    help="Override configuration file path for this command.",
)
@click.pass_obj
def validate_config(
    options: RuntimeOptions,
    config_path_override: Path | None,
) -> None:
    """Validate configuration file and exit."""

    if config_path_override is not None:
        options.config_path = config_path_override

    _ = _load_runtime_config(options)
    click.echo("Configuration is valid.")


@main.command()
@click.pass_obj
def auth(options: RuntimeOptions) -> None:
    """Run interactive Gmail OAuth authentication flow."""

    config = _load_runtime_config(options)
    from gmail_sorter.gmail.auth import GmailAuthenticator
    from gmail_sorter.observability import configure_logging

    configure_logging(config.logging.level, config.logging.log_prompts)
    authenticator = GmailAuthenticator(config.gmail)
    authenticator.authenticate()
    click.echo("Authentication completed.")


@main.command()
@click.option(
    "--since",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]),
    default=None,
    help="Include records on/after this UTC timestamp (ISO-8601 or YYYY-MM-DD).",
)
@click.option(
    "--until",
    type=click.DateTime(formats=["%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%SZ"]),
    default=None,
    help="Include records on/before this UTC timestamp (ISO-8601 or YYYY-MM-DD).",
)
@click.pass_obj
def stats(options: RuntimeOptions, since: datetime | None, until: datetime | None) -> None:
    """Print classification statistics from the local SQLite database."""

    config = _load_runtime_config(options)
    db = Database(config.database.path)
    db.initialize()
    try:
        db.enforce_retention(config.database.retention_days)
        filtered_stats = db.get_stats(since=_as_utc(since), until=_as_utc(until))
        total_processed = int(filtered_stats.get("total_processed", 0))
        by_category = dict(filtered_stats.get("by_category", {}))
        error_total = int(filtered_stats.get("error_total", 0))
        since_text = filtered_stats.get("since")
        until_text = filtered_stats.get("until")
    finally:
        db.close()

    denominator = total_processed + error_total
    error_rate = (error_total / denominator * 100.0) if denominator else 0.0
    date_range = f"{since_text or 'beginning'} to {until_text or 'now'}"

    click.echo("Classification Statistics")
    click.echo(f"- Total processed: {total_processed}")
    click.echo(f"- Total errors: {error_total}")
    click.echo(f"- Error rate: {error_rate:.2f}%")
    click.echo(f"- Date range: {date_range}")

    if not by_category:
        click.echo("- Categories: none")
        return

    click.echo("- By category:")
    for category, count in sorted(by_category.items(), key=lambda item: (-item[1], item[0])):
        click.echo(f"  {category}: {count}")


def _load_runtime_config(options: RuntimeOptions) -> AppConfig:
    """Load config and apply global CLI runtime overrides."""

    config = load_config(options.config_path)
    if options.dry_run:
        config.processing.dry_run = True
    if options.log_level is not None:
        config.logging.level = options.log_level
    return config


def _as_utc(value: datetime | None) -> datetime | None:
    """Normalize an optional datetime to UTC."""

    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _build_engine(config: AppConfig, db: Database) -> tuple[Any, Any, Any, Any]:
    """Create core runtime components required by run and backfill commands."""

    from gmail_sorter.classifier.engine import ClassificationEngine
    from gmail_sorter.classifier.idempotency import IdempotencyChecker
    from gmail_sorter.gmail.auth import GmailAuthenticator
    from gmail_sorter.gmail.client import GmailClient
    from gmail_sorter.gmail.labels import LabelManager
    from gmail_sorter.llm.client import LlmClient
    from gmail_sorter.observability.metrics import MetricsCollector
    from gmail_sorter.processor.prompt_builder import PromptBuilder

    authenticator = GmailAuthenticator(config.gmail)
    credentials = authenticator.get_credentials()
    gmail_client = GmailClient(credentials=credentials, dry_run=config.processing.dry_run)

    label_manager = LabelManager(gmail_client)
    label_map = label_manager.ensure_all_labels(config.categories)

    llm_client = LlmClient(config.llm, log_prompts=config.logging.log_prompts)
    prompt_builder = PromptBuilder(config.llm, config.categories)
    idempotency_checker = IdempotencyChecker(db=db, system_label_ids=set(label_map.values()))
    metrics = MetricsCollector()

    engine = ClassificationEngine(
        config=config,
        gmail_client=gmail_client,
        llm_client=llm_client,
        db=db,
        label_map=label_map,
        idempotency_checker=idempotency_checker,
        prompt_builder=prompt_builder,
        metrics=metrics,
    )

    return engine, gmail_client, llm_client, metrics


async def _run_service(config: AppConfig, run_backfill: bool) -> None:
    """Run listener service and optional concurrent backfill task."""

    db = Database(config.database.path)
    db.initialize()

    engine: Any | None = None
    gmail_client: Any | None = None
    llm_client: Any | None = None
    metrics: Any | None = None
    listener: Any | None = None
    watcher: Any | None = None
    health_server: Any | None = None
    backfill_task: asyncio.Task[None] | None = None
    listener_task: asyncio.Task[None] | None = None

    stop_event = asyncio.Event()
    listener_retry_delay_seconds = 2.0
    max_listener_retry_delay_seconds = 30.0
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        with contextlib.suppress(NotImplementedError):
            loop.add_signal_handler(sig, stop_event.set)

    try:
        from gmail_sorter.backfill.engine import BackfillEngine
        from gmail_sorter.observability import HealthServer
        from gmail_sorter.pubsub.listener import PubSubListener
        from gmail_sorter.pubsub.watcher import GmailWatcher

        engine, gmail_client, llm_client, metrics = _build_engine(config, db)

        db.enforce_retention(config.database.retention_days)
        metrics.start_http_server(port=config.observability.metrics_port)
        health_server = HealthServer(port=config.observability.health_port)
        health_server.start()
        health_server.set_healthy(last_message_at=datetime.utcnow().isoformat() + "Z")

        listener = PubSubListener(config=config.pubsub, engine=engine, metrics=metrics)
        watcher = GmailWatcher(gmail_client=gmail_client, config=config.pubsub)
        watcher.register()
        watcher.schedule_renewal()

        listener_task = asyncio.create_task(listener.start())

        if run_backfill:
            backfill_engine = BackfillEngine(
                gmail_client=gmail_client,
                engine=engine,
                db=db,
                config=config.processing,
                metrics=metrics,
            )
            backfill_task = asyncio.create_task(backfill_engine.run())

        while not stop_event.is_set():
            if listener_task.done():
                listener_error: Exception | None = None
                try:
                    await listener_task
                except Exception as exc:  # pragma: no cover - covered by unit tests
                    listener_error = exc

                if stop_event.is_set():
                    break

                if listener_error is None:
                    if health_server is not None:
                        health_server.set_unhealthy("listener exited unexpectedly")
                    break

                if health_server is not None:
                    health_server.set_unhealthy("pubsub listener disconnected")

                if listener is not None:
                    with contextlib.suppress(Exception):
                        await listener.stop()

                await asyncio.sleep(listener_retry_delay_seconds)
                listener_retry_delay_seconds = min(
                    listener_retry_delay_seconds * 2.0,
                    max_listener_retry_delay_seconds,
                )

                listener = PubSubListener(config=config.pubsub, engine=engine, metrics=metrics)
                listener_task = asyncio.create_task(listener.start())
                if health_server is not None:
                    health_server.set_healthy(last_message_at=datetime.utcnow().isoformat() + "Z")
                continue

            if backfill_task is not None and backfill_task.done():
                await backfill_task
                backfill_task = None

            await asyncio.sleep(0.2)
    finally:
        if backfill_task is not None and not backfill_task.done():
            backfill_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await backfill_task

        if listener is not None:
            await listener.stop()
        if listener_task is not None and not listener_task.done():
            with contextlib.suppress(asyncio.CancelledError):
                await listener_task

        if watcher is not None:
            watcher.stop()
        if health_server is not None:
            health_server.stop()
        if llm_client is not None:
            await llm_client.close()
        db.close()


async def _run_backfill_only(config: AppConfig) -> None:
    """Run only backfill flow and exit when finished."""

    db = Database(config.database.path)
    db.initialize()

    llm_client: Any | None = None
    try:
        from gmail_sorter.backfill.engine import BackfillEngine

        db.enforce_retention(config.database.retention_days)
        engine, gmail_client, llm_client, metrics = _build_engine(config, db)
        backfill_engine = BackfillEngine(
            gmail_client=gmail_client,
            engine=engine,
            db=db,
            config=config.processing,
            metrics=metrics,
        )
        await backfill_engine.run()
    finally:
        if llm_client is not None:
            await llm_client.close()
        db.close()


if __name__ == "__main__":
    main()
