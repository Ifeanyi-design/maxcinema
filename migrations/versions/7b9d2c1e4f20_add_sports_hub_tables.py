"""add sports hub tables

Revision ID: 7b9d2c1e4f20
Revises: f6ad08006f74
Create Date: 2026-05-31 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = '7b9d2c1e4f20'
down_revision = 'f6ad08006f74'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'sports_sport',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('slug', sa.String(length=80), nullable=False),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('display_order', sa.Integer(), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
        sa.UniqueConstraint('slug')
    )
    op.create_index(op.f('ix_sports_sport_display_order'), 'sports_sport', ['display_order'], unique=False)
    op.create_index(op.f('ix_sports_sport_enabled'), 'sports_sport', ['enabled'], unique=False)
    op.create_index(op.f('ix_sports_sport_slug'), 'sports_sport', ['slug'], unique=False)

    op.create_table(
        'sports_competition',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('slug', sa.String(length=180), nullable=False),
        sa.Column('country', sa.String(length=80), nullable=True),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('current_season', sa.String(length=40), nullable=True),
        sa.Column('provider_name', sa.String(length=80), nullable=True),
        sa.Column('provider_competition_id', sa.String(length=120), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('featured', sa.Boolean(), nullable=True),
        sa.Column('hidden', sa.Boolean(), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports_sport.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sport_id', 'slug', name='uq_sports_competition_sport_slug')
    )
    for column in ['sport_id', 'slug', 'country', 'current_season', 'provider_name', 'provider_competition_id', 'enabled', 'featured', 'hidden']:
        op.create_index(op.f(f'ix_sports_competition_{column}'), 'sports_competition', [column], unique=False)

    op.create_table(
        'sports_team',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('slug', sa.String(length=180), nullable=False),
        sa.Column('short_name', sa.String(length=80), nullable=True),
        sa.Column('country', sa.String(length=80), nullable=True),
        sa.Column('logo_url', sa.String(length=500), nullable=True),
        sa.Column('provider_name', sa.String(length=80), nullable=True),
        sa.Column('provider_team_id', sa.String(length=120), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['sport_id'], ['sports_sport.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('sport_id', 'slug', name='uq_sports_team_sport_slug')
    )
    for column in ['sport_id', 'slug', 'country', 'provider_name', 'provider_team_id']:
        op.create_index(op.f(f'ix_sports_team_{column}'), 'sports_team', [column], unique=False)

    op.create_table(
        'sports_provider_cache',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_name', sa.String(length=80), nullable=False),
        sa.Column('cache_key', sa.String(length=240), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=True),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('stale_until', sa.DateTime(), nullable=True),
        sa.Column('last_error', sa.Text(), nullable=True),
        sa.Column('last_fetched_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_name', 'cache_key', name='uq_sports_provider_cache_key')
    )
    for column in ['provider_name', 'cache_key', 'status', 'expires_at', 'stale_until', 'last_fetched_at']:
        op.create_index(op.f(f'ix_sports_provider_cache_{column}'), 'sports_provider_cache', [column], unique=False)

    op.create_table(
        'sports_provider_mapping',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('provider_name', sa.String(length=80), nullable=False),
        sa.Column('entity_type', sa.String(length=40), nullable=False),
        sa.Column('local_id', sa.Integer(), nullable=True),
        sa.Column('provider_entity_id', sa.String(length=120), nullable=False),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('provider_name', 'entity_type', 'provider_entity_id', name='uq_sports_provider_mapping_external')
    )
    for column in ['provider_name', 'entity_type', 'local_id', 'provider_entity_id']:
        op.create_index(op.f(f'ix_sports_provider_mapping_{column}'), 'sports_provider_mapping', [column], unique=False)

    op.create_table(
        'sports_season',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('competition_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('provider_name', sa.String(length=80), nullable=True),
        sa.Column('provider_season_id', sa.String(length=120), nullable=True),
        sa.Column('starts_at', sa.DateTime(), nullable=True),
        sa.Column('ends_at', sa.DateTime(), nullable=True),
        sa.Column('current', sa.Boolean(), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['competition_id'], ['sports_competition.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    for column in ['competition_id', 'provider_name', 'provider_season_id', 'starts_at', 'ends_at', 'current']:
        op.create_index(op.f(f'ix_sports_season_{column}'), 'sports_season', [column], unique=False)

    op.create_table(
        'sports_match',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('sport_id', sa.Integer(), nullable=False),
        sa.Column('competition_id', sa.Integer(), nullable=True),
        sa.Column('season_id', sa.Integer(), nullable=True),
        sa.Column('home_team_id', sa.Integer(), nullable=True),
        sa.Column('away_team_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=240), nullable=False),
        sa.Column('slug', sa.String(length=260), nullable=False),
        sa.Column('kickoff_at', sa.DateTime(), nullable=True),
        sa.Column('status', sa.String(length=40), nullable=True),
        sa.Column('provider_status', sa.String(length=80), nullable=True),
        sa.Column('provider_clock', sa.String(length=40), nullable=True),
        sa.Column('minute', sa.Integer(), nullable=True),
        sa.Column('home_score', sa.Integer(), nullable=True),
        sa.Column('away_score', sa.Integer(), nullable=True),
        sa.Column('provider_name', sa.String(length=80), nullable=True),
        sa.Column('provider_match_id', sa.String(length=120), nullable=True),
        sa.Column('external_match_id', sa.String(length=120), nullable=True),
        sa.Column('featured', sa.Boolean(), nullable=True),
        sa.Column('pinned', sa.Boolean(), nullable=True),
        sa.Column('archived', sa.Boolean(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.Column('stale_after', sa.DateTime(), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['away_team_id'], ['sports_team.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['competition_id'], ['sports_competition.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['home_team_id'], ['sports_team.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['season_id'], ['sports_season.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['sport_id'], ['sports_sport.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    for column in ['sport_id', 'competition_id', 'season_id', 'home_team_id', 'away_team_id', 'slug', 'kickoff_at', 'status', 'provider_status', 'minute', 'provider_name', 'provider_match_id', 'external_match_id', 'featured', 'pinned', 'archived', 'last_synced_at', 'stale_after']:
        op.create_index(op.f(f'ix_sports_match_{column}'), 'sports_match', [column], unique=False)

    op.create_table(
        'sports_standing',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('competition_id', sa.Integer(), nullable=False),
        sa.Column('season_id', sa.Integer(), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('position', sa.Integer(), nullable=True),
        sa.Column('played', sa.Integer(), nullable=True),
        sa.Column('won', sa.Integer(), nullable=True),
        sa.Column('drawn', sa.Integer(), nullable=True),
        sa.Column('lost', sa.Integer(), nullable=True),
        sa.Column('goals_for', sa.Integer(), nullable=True),
        sa.Column('goals_against', sa.Integer(), nullable=True),
        sa.Column('goal_difference', sa.Integer(), nullable=True),
        sa.Column('points', sa.Integer(), nullable=True),
        sa.Column('group_name', sa.String(length=80), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('last_synced_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['competition_id'], ['sports_competition.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['season_id'], ['sports_season.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['team_id'], ['sports_team.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    for column in ['competition_id', 'season_id', 'team_id', 'position', 'points', 'group_name', 'last_synced_at']:
        op.create_index(op.f(f'ix_sports_standing_{column}'), 'sports_standing', [column], unique=False)

    op.create_table(
        'sports_stream_source',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=True),
        sa.Column('sport_id', sa.Integer(), nullable=True),
        sa.Column('competition_id', sa.Integer(), nullable=True),
        sa.Column('source_type', sa.String(length=40), nullable=True),
        sa.Column('provider_name', sa.String(length=80), nullable=True),
        sa.Column('title', sa.String(length=160), nullable=False),
        sa.Column('embed_url', sa.String(length=700), nullable=True),
        sa.Column('external_url', sa.String(length=700), nullable=True),
        sa.Column('url_pattern', sa.String(length=700), nullable=True),
        sa.Column('enabled', sa.Boolean(), nullable=True),
        sa.Column('priority', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('last_checked_at', sa.DateTime(), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['competition_id'], ['sports_competition.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['match_id'], ['sports_match.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['sport_id'], ['sports_sport.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    for column in ['match_id', 'sport_id', 'competition_id', 'source_type', 'provider_name', 'enabled', 'priority', 'last_checked_at']:
        op.create_index(op.f(f'ix_sports_stream_source_{column}'), 'sports_stream_source', [column], unique=False)

    op.create_table(
        'sports_match_event',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('match_id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('minute', sa.Integer(), nullable=True),
        sa.Column('clock', sa.String(length=40), nullable=True),
        sa.Column('team_id', sa.Integer(), nullable=True),
        sa.Column('player_name', sa.String(length=160), nullable=True),
        sa.Column('related_player_name', sa.String(length=160), nullable=True),
        sa.Column('summary', sa.String(length=300), nullable=True),
        sa.Column('provider_name', sa.String(length=80), nullable=True),
        sa.Column('provider_event_id', sa.String(length=120), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=True),
        sa.Column('provider_payload', sa.JSON(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['match_id'], ['sports_match.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['team_id'], ['sports_team.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    for column in ['match_id', 'event_type', 'minute', 'team_id', 'provider_name', 'provider_event_id', 'sort_order', 'occurred_at']:
        op.create_index(op.f(f'ix_sports_match_event_{column}'), 'sports_match_event', [column], unique=False)


def downgrade():
    for table, columns in [
        ('sports_match_event', ['occurred_at', 'sort_order', 'provider_event_id', 'provider_name', 'team_id', 'minute', 'event_type', 'match_id']),
        ('sports_stream_source', ['last_checked_at', 'priority', 'enabled', 'provider_name', 'source_type', 'competition_id', 'sport_id', 'match_id']),
        ('sports_standing', ['last_synced_at', 'group_name', 'points', 'position', 'team_id', 'season_id', 'competition_id']),
        ('sports_match', ['stale_after', 'last_synced_at', 'archived', 'pinned', 'featured', 'external_match_id', 'provider_match_id', 'provider_name', 'minute', 'provider_status', 'status', 'kickoff_at', 'slug', 'away_team_id', 'home_team_id', 'season_id', 'competition_id', 'sport_id']),
        ('sports_season', ['current', 'ends_at', 'starts_at', 'provider_season_id', 'provider_name', 'competition_id']),
        ('sports_provider_mapping', ['provider_entity_id', 'local_id', 'entity_type', 'provider_name']),
        ('sports_provider_cache', ['last_fetched_at', 'stale_until', 'expires_at', 'status', 'cache_key', 'provider_name']),
        ('sports_team', ['provider_team_id', 'provider_name', 'country', 'slug', 'sport_id']),
        ('sports_competition', ['hidden', 'featured', 'enabled', 'provider_competition_id', 'provider_name', 'current_season', 'country', 'slug', 'sport_id']),
        ('sports_sport', ['slug', 'enabled', 'display_order']),
    ]:
        for column in columns:
            op.drop_index(op.f(f'ix_{table}_{column}'), table_name=table)

    op.drop_table('sports_match_event')
    op.drop_table('sports_stream_source')
    op.drop_table('sports_standing')
    op.drop_table('sports_match')
    op.drop_table('sports_season')
    op.drop_table('sports_provider_mapping')
    op.drop_table('sports_provider_cache')
    op.drop_table('sports_team')
    op.drop_table('sports_competition')
    op.drop_table('sports_sport')
