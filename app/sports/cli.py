from __future__ import annotations

import click
from flask.cli import with_appcontext

from .services import (
    get_enabled_competitions,
    sync_competition_standings,
    sync_live_matches,
    sync_provider_catalog,
    sync_provider_fixtures,
)
from .providers import get_provider


@click.group()
def sports_cli():
    """Sports data synchronization commands."""


@sports_cli.command("sync")
@with_appcontext
def sync_cmd():
    """Full sync: catalog + fixtures + standings for every competition."""
    provider = get_provider()
    click.echo(f"[sports] full sync via provider '{provider.name}'")
    catalog = sync_provider_catalog(provider)
    fixtures = sync_provider_fixtures(provider)
    competitions = get_enabled_competitions()
    standings_errors = 0
    for comp in competitions:
        try:
            sync_competition_standings(comp, provider)
        except Exception as exc:  # noqa: BLE001
            standings_errors += 1
            click.echo(f"[sports] standings failed for {comp.name}: {exc}")
    click.echo(
        "[sports] sync done | "
        f"sports_stale={catalog['sports_stale']} "
        f"competitions_stale={catalog['competitions_stale']} "
        f"teams_stale={catalog['teams_stale']} "
        f"fixtures_stale={fixtures.stale} "
        f"competitions={len(competitions)} "
        f"standings_errors={standings_errors}"
    )


@sports_cli.command("sync-live")
@with_appcontext
def sync_live_cmd():
    """Sync only currently live matches (cheap, run frequently)."""
    provider = get_provider()
    result = sync_live_matches(provider)
    click.echo(f"[sports] live sync done | stale={result.stale} error={result.error}")


@sports_cli.command("sync-fixtures")
@with_appcontext
def sync_fixtures_cmd():
    """Sync upcoming fixtures for every competition."""
    provider = get_provider()
    result = sync_provider_fixtures(provider)
    click.echo(f"[sports] fixtures sync done | stale={result.stale} error={result.error}")
