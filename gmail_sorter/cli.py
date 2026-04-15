"""Command-line interface for gmail-sorter."""

from __future__ import annotations

import asyncio
import contextlib
import signal
from dataclasses import dataclass
from datetime import datetime
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
@click.pass_obj
def validate_config(options: RuntimeOptions) -> None:
    """Validate configuration file and exit."""

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
@click.pass_obj
def stats(options: RuntimeOptions) -> None:
    """Print classification statistics from the local SQLite database."""

    config = _load_runtime_config(options)
    db = Database(config.database.path)
    db.initialize()
    try:
        all_time_stats = db.get_stats()
        total_processed = int(all_time_stats.get("total_processed", 0))
        by_category = dict(all_time_stats.get("by_category", {}))
        dlq_total = len(db.get_dlq_entries(limit=1_000_000_000))
    finally:
        db.close()

    error_rate = (dlq_total / total_processed * 100.0) if total_processed else 0.0
    date_range = "all time"

    click.echo("Classification Statistics")
    click.echo(f"- Total processed: {total_processed}")
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

        metrics.start_http_server()
        health_server = HealthServer(port=8080)
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
                await listener_task
                break

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
