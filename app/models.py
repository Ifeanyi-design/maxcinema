from flask_sqlalchemy import SQLAlchemy
from datetime import datetime
from slugify import slugify
from flask_login import UserMixin
from .extensions import db


video_genre = db.Table('video_genre',
    db.Column('video_id', db.Integer, db.ForeignKey('all_video.id'), primary_key=True),
    db.Column('genre_id', db.Integer, db.ForeignKey('genre.id'), primary_key=True)                       
                       )

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    date_created = db.Column(db.DateTime, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, default=datetime.utcnow)

class Genre(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), unique=True, nullable=False)

    # Many-to-many relationship with AllVideo
    videos = db.relationship('AllVideo', secondary=video_genre, back_populates='genres')

# AllVideos table (master table for movies and series)
class AllVideo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)
    image = db.Column(db.String(300))
    slug = db.Column(db.String(255), unique=True, nullable=True)
    download_link = db.Column(db.String(300))
    dub_download_link = db.Column(db.String(200))
    # 👇 NEW COLUMN
    backup_link = db.Column(db.String(500), nullable=True)
    type = db.Column(db.String(10), nullable=False)  # 'movie' or 'series'
    featured = db.Column(db.Boolean, default=False)
    trending = db.Column(db.Boolean, default=False)
    active = db.Column(db.Boolean, default=True)
    description = db.Column(db.Text)
    rating = db.Column(db.Float, default=0.0)
    num_votes = db.Column(db.Integer, default=0)
    date_added = db.Column(db.DateTime, default=db.func.current_timestamp())
    length = db.Column(db.String(20))  # e.g., "2h 10m"
    year_produced = db.Column(db.Integer)
    star_cast = db.Column(db.Text)
    released_date = db.Column(db.Date)
    country = db.Column(db.String(100))
    language = db.Column(db.String(50))
    subtitles = db.Column(db.String(200))
    source = db.Column(db.String(300))
    views = db.Column(db.Integer, default=0)
    downloads = db.Column(db.Integer, default=0)
    trailer_url = db.Column(db.String(300))
    total_comment = db.Column(db.Integer, default=0, nullable=True)
    video_360p = db.Column(db.String(500))  # path or URL
    video_480p = db.Column(db.String(500))
    video_720p = db.Column(db.String(500))
    video_1080p = db.Column(db.String(500))
    video_qualities = db.Column(db.JSON)
    coming_soon = db.Column(db.Boolean, default=False)

    thumb_360p = db.Column(db.String, nullable=True)
    thumb_480p = db.Column(db.String, nullable=True)
    thumb_720p = db.Column(db.String, nullable=True)
    thumb_1080p = db.Column(db.String, nullable=True)

    storage_server_id = db.Column(db.Integer, db.ForeignKey('storage_servers.id'), nullable=True)
    storage_server = db.relationship("StorageServer", back_populates="videos")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    genres = db.relationship('Genre', secondary=video_genre, back_populates='videos')
    movie = db.relationship('Movie', back_populates='all_video', uselist=False, cascade='all, delete-orphan')
    series = db.relationship('Series', back_populates='all_video', uselist=False, cascade='all, delete-orphan')
    ratings = db.relationship('Rating', back_populates='video', cascade='all, delete-orphan')
    recent_items = db.relationship(
        'RecentItem',
        back_populates='video',
        cascade='all, delete-orphan'
    )
    comments = db.relationship(
    'Comment',
    back_populates='video',
    cascade='all, delete-orphan'
    )

    def update_video_qualities(self):
        qualities = {}
        for q in ["360p", "480p", "720p", "1080p"]:
            url = getattr(self, f"video_{q}", None)
            if url:  # only include if not None/empty
                qualities[q] = url
        self.video_qualities = qualities

#Rating Table
class Rating(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('all_video.id'), nullable=False)
    ip_address = db.Column(db.String(50), nullable=False)
    rating = db.Column(db.Integer, nullable=False)  # 1 to 5
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    video = db.relationship('AllVideo', back_populates='ratings')

# Movie table
class Movie(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    all_video_id = db.Column(db.Integer, db.ForeignKey('all_video.id', ondelete='CASCADE'), nullable=False)
    all_video = db.relationship('AllVideo', back_populates='movie')
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

# Series table
class Series(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    all_video_id = db.Column(db.Integer, db.ForeignKey('all_video.id', ondelete='CASCADE'))
    num_seasons = db.Column(db.Integer)
    num_episodes = db.Column(db.Integer)

    all_video = db.relationship('AllVideo', back_populates='series')
    seasons = db.relationship('Season', back_populates='series', cascade="all, delete-orphan", order_by="Season.season_number")

    @property
    def current_season(self):
        # seasons is ordered by season_number because of order_by
        return self.seasons[-1] if self.seasons else None

    @property
    def current_season_incomplete(self):
        cs = self.current_season
        return bool(cs and not cs.completed)

# Season table
class Season(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    series_id = db.Column(db.Integer, db.ForeignKey('series.id', ondelete='CASCADE'))
    season_number = db.Column(db.Integer)
    num_episodes = db.Column(db.Integer, default=0)
    description = db.Column(db.Text)
    cast = db.Column(db.Text)
    completed = db.Column(db.Boolean, default=False)
    
    # Optional / recommended
    release_date = db.Column(db.Date)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    image = db.Column(db.String, nullable=True)
    trailer_url = db.Column(db.String(300))
    
    
    series = db.relationship('Series', back_populates='seasons')
    episodes = db.relationship('Episode', back_populates='season', cascade="all, delete-orphan", order_by="Episode.episode_number")

# Episode table
class Episode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    season_id = db.Column(db.Integer, db.ForeignKey('season.id', ondelete='CASCADE'))
    episode_number = db.Column(db.Integer)
    name = db.Column(db.String(200))
    length = db.Column(db.String(20))
    description = db.Column(db.Text)
    cast = db.Column(db.Text)
    released_date = db.Column(db.Date)
    source = db.Column(db.String(300))
    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    download_link = db.Column(db.String(300))
    dub_download_link = db.Column(db.String(200))
    # 👇 NEW COLUMN
    backup_link = db.Column(db.String(500), nullable=True)
    downloads = db.Column(db.Integer, default=0)
    video_360p = db.Column(db.String(500))
    video_480p = db.Column(db.String(500))
    video_720p = db.Column(db.String(500))
    video_1080p = db.Column(db.String(500))
    views = db.Column(db.Integer, default=0)

    thumb_360p = db.Column(db.String, nullable=True)
    thumb_480p = db.Column(db.String, nullable=True)
    thumb_720p = db.Column(db.String, nullable=True)
    thumb_1080p = db.Column(db.String, nullable=True)
    coming_soon = db.Column(db.Boolean, default=False)

    # Link to storage server
    storage_server_id = db.Column(db.Integer, db.ForeignKey('storage_servers.id'), nullable=True)
    storage_server = db.relationship("StorageServer", back_populates="episodes")

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    video_qualities = db.Column(db.JSON)
    
    season = db.relationship('Season', back_populates='episodes')
    recent_items = db.relationship(
    'RecentItem',
    back_populates='episode',
    cascade='all, delete-orphan'
    )

    def update_video_qualities(self):
        qualities = {}
        for q in ["360p", "480p", "720p", "1080p"]:
            url = getattr(self, f"video_{q}", None)
            if url:
                qualities[q] = url
        self.video_qualities = qualities
        

class RecentItem(db.Model):
    __tablename__ = 'recent_item'
    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('all_video.id', ondelete='CASCADE'))
    episode_id = db.Column(db.Integer, db.ForeignKey('episode.id', ondelete='CASCADE'), nullable=True)
    type = db.Column(db.String(10), nullable=False, index=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    series_id = db.Column(db.Integer, db.ForeignKey("series.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    video = db.relationship('AllVideo', back_populates='recent_items')
    episode = db.relationship('Episode', back_populates='recent_items')

class Comment(db.Model):
    __tablename__ = "comment"

    id = db.Column(db.Integer, primary_key=True)

    video_id = db.Column(db.Integer, db.ForeignKey('all_video.id'), nullable=True)

    parent_id = db.Column(db.Integer, db.ForeignKey('comment.id'), nullable=True)
    trailer_id = db.Column(db.Integer, db.ForeignKey('trailer.id'), nullable=True)

    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    text = db.Column(db.Text, nullable=False)

    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    # Replies (self-referencing)
    replies = db.relationship(
        'Comment',
        backref=db.backref('parent', remote_side=[id]),
        lazy='select',
        cascade="all, delete-orphan"
    )

    video = db.relationship('AllVideo', back_populates='comments')
    trailer = db.relationship('Trailer', back_populates='comments')

class Trailer(db.Model):
    __tablename__ = "trailer"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(255), nullable=False)
    slug = db.Column(db.String(255), unique=True, nullable=False)

    trailer_link = db.Column(db.String(500), nullable=False)
    views = db.Column(db.Integer, default=0)
    image = db.Column(db.String(300), nullable=True)   
    description = db.Column(db.Text, nullable=True)
    total_comment = db.Column(db.Integer, default=0, nullable=True)

    date_added = db.Column(db.DateTime, default=datetime.utcnow)
    release_date = db.Column(db.DateTime, nullable=True)
    release_year = db.Column(db.Integer, nullable=True)

    # Relationship to comments
    comments = db.relationship(
    "Comment",
    back_populates="trailer",
    cascade='all, delete-orphan'
    )


class StorageServer(db.Model):
    __tablename__ = 'storage_servers'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)
    server_type = db.Column(db.String(50), nullable=True)  # e.g., 'local', 'aws_s3', 'bytescale'
    base_url = db.Column(db.String(255), nullable=True)
    api_key = db.Column(db.String(255))
    username = db.Column(db.String(100))
    password = db.Column(db.String(100))
    max_storage_gb = db.Column(db.Float, default=0)
    used_storage_gb = db.Column(db.Float, default=0)
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    videos = db.relationship("AllVideo", back_populates="storage_server", lazy="dynamic")
    episodes = db.relationship("Episode", back_populates="storage_server", lazy="dynamic")

    def __repr__(self):
        return f"<StorageServer {self.name} ({self.server_type})>"

    def available_storage(self):
        if self.max_storage_gb == 0:
            return float('inf')
        return self.max_storage_gb - self.used_storage_gb


class MovieRequest(db.Model):
    __tablename__ = "movie_request"  # Explicit table name

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False) # User's name
    email = db.Column(db.String(120), nullable=False)
    
    # What are they asking for?
    movie_name = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, nullable=True) # Details like year, actors, or IMDb link
    
    # Track the request lifecycle
    status = db.Column(db.String(20), default='Pending') # Pending, Filled, Rejected
    
    date_added = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Request {self.movie_name} by {self.name}>'


class SearchTerm(db.Model):
    """Tracks what users are searching for to help you find missing content."""
    id = db.Column(db.Integer, primary_key=True)
    term = db.Column(db.String(100), nullable=False) # e.g., "Avengers"
    count = db.Column(db.Integer, default=1)         # How many times searched?
    last_searched = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Search {self.term}: {self.count}>"


class AnalyticsEvent(db.Model):
    __tablename__ = "analytics_event"

    id = db.Column(db.Integer, primary_key=True)
    event = db.Column(db.String(50), nullable=False, index=True)
    target = db.Column(db.String(120), nullable=True)
    page = db.Column(db.String(240), nullable=True)
    ip_address = db.Column(db.String(64), nullable=True)
    user_agent = db.Column(db.String(180), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class WatchlistNotify(db.Model):
    __tablename__ = "watchlist_notify"

    id = db.Column(db.Integer, primary_key=True)
    video_id = db.Column(db.Integer, db.ForeignKey('all_video.id', ondelete='CASCADE'), nullable=False, index=True)
    name = db.Column(db.String(100), nullable=True)
    email = db.Column(db.String(120), nullable=True, index=True)
    telegram = db.Column(db.String(120), nullable=True, index=True)
    source = db.Column(db.String(20), default="web")
    notified = db.Column(db.Boolean, default=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    video = db.relationship('AllVideo', lazy='joined')


class WeeklyPoll(db.Model):
    __tablename__ = "weekly_poll"

    id = db.Column(db.Integer, primary_key=True)
    question = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True, index=True)
    starts_at = db.Column(db.DateTime, default=datetime.utcnow)
    ends_at = db.Column(db.DateTime, nullable=True, index=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, index=True)

    options = db.relationship('WeeklyPollOption', back_populates='poll', cascade='all, delete-orphan')


class WeeklyPollOption(db.Model):
    __tablename__ = "weekly_poll_option"

    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('weekly_poll.id', ondelete='CASCADE'), nullable=False, index=True)
    option_text = db.Column(db.String(180), nullable=False)
    votes = db.Column(db.Integer, default=0)

    poll = db.relationship('WeeklyPoll', back_populates='options')


class WeeklyPollVote(db.Model):
    __tablename__ = "weekly_poll_vote"

    id = db.Column(db.Integer, primary_key=True)
    poll_id = db.Column(db.Integer, db.ForeignKey('weekly_poll.id', ondelete='CASCADE'), nullable=False, index=True)
    option_id = db.Column(db.Integer, db.ForeignKey('weekly_poll_option.id', ondelete='CASCADE'), nullable=False, index=True)
    voter_token = db.Column(db.String(120), nullable=False, index=True)
    ip_address = db.Column(db.String(64), nullable=True)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, index=True)


class SportsSport(db.Model):
    __tablename__ = "sports_sport"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    slug = db.Column(db.String(80), nullable=False, unique=True, index=True)
    enabled = db.Column(db.Boolean, default=True, index=True)
    display_order = db.Column(db.Integer, default=0, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    competitions = db.relationship("SportsCompetition", back_populates="sport", cascade="all, delete-orphan")
    teams = db.relationship("SportsTeam", back_populates="sport", cascade="all, delete-orphan")


class SportsCompetition(db.Model):
    __tablename__ = "sports_competition"

    id = db.Column(db.Integer, primary_key=True)
    sport_id = db.Column(db.Integer, db.ForeignKey("sports_sport.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), nullable=False, index=True)
    country = db.Column(db.String(80), nullable=True, index=True)
    logo_url = db.Column(db.String(500), nullable=True)
    current_season = db.Column(db.String(40), nullable=True, index=True)
    provider_name = db.Column(db.String(80), nullable=True, index=True)
    provider_competition_id = db.Column(db.String(120), nullable=True, index=True)
    enabled = db.Column(db.Boolean, default=False, index=True)
    featured = db.Column(db.Boolean, default=False, index=True)
    hidden = db.Column(db.Boolean, default=False, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sport = db.relationship("SportsSport", back_populates="competitions")
    seasons = db.relationship("SportsSeason", back_populates="competition", cascade="all, delete-orphan")
    matches = db.relationship("SportsMatch", back_populates="competition", cascade="all, delete-orphan")
    standings = db.relationship("SportsStanding", back_populates="competition", cascade="all, delete-orphan")

    __table_args__ = (
        db.UniqueConstraint("sport_id", "slug", name="uq_sports_competition_sport_slug"),
    )


class SportsTeam(db.Model):
    __tablename__ = "sports_team"

    id = db.Column(db.Integer, primary_key=True)
    sport_id = db.Column(db.Integer, db.ForeignKey("sports_sport.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(160), nullable=False)
    slug = db.Column(db.String(180), nullable=False, index=True)
    short_name = db.Column(db.String(80), nullable=True)
    country = db.Column(db.String(80), nullable=True, index=True)
    logo_url = db.Column(db.String(500), nullable=True)
    provider_name = db.Column(db.String(80), nullable=True, index=True)
    provider_team_id = db.Column(db.String(120), nullable=True, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sport = db.relationship("SportsSport", back_populates="teams")

    __table_args__ = (
        db.UniqueConstraint("sport_id", "slug", name="uq_sports_team_sport_slug"),
    )


class SportsSeason(db.Model):
    __tablename__ = "sports_season"

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("sports_competition.id", ondelete="CASCADE"), nullable=False, index=True)
    name = db.Column(db.String(80), nullable=False)
    provider_name = db.Column(db.String(80), nullable=True, index=True)
    provider_season_id = db.Column(db.String(120), nullable=True, index=True)
    starts_at = db.Column(db.DateTime, nullable=True, index=True)
    ends_at = db.Column(db.DateTime, nullable=True, index=True)
    current = db.Column(db.Boolean, default=False, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    competition = db.relationship("SportsCompetition", back_populates="seasons")


class SportsMatch(db.Model):
    __tablename__ = "sports_match"

    id = db.Column(db.Integer, primary_key=True)
    sport_id = db.Column(db.Integer, db.ForeignKey("sports_sport.id", ondelete="CASCADE"), nullable=False, index=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("sports_competition.id", ondelete="SET NULL"), nullable=True, index=True)
    season_id = db.Column(db.Integer, db.ForeignKey("sports_season.id", ondelete="SET NULL"), nullable=True, index=True)
    home_team_id = db.Column(db.Integer, db.ForeignKey("sports_team.id", ondelete="SET NULL"), nullable=True, index=True)
    away_team_id = db.Column(db.Integer, db.ForeignKey("sports_team.id", ondelete="SET NULL"), nullable=True, index=True)
    name = db.Column(db.String(240), nullable=False)
    slug = db.Column(db.String(260), nullable=False, index=True)
    kickoff_at = db.Column(db.DateTime, nullable=True, index=True)
    status = db.Column(db.String(40), default="scheduled", index=True)
    provider_status = db.Column(db.String(80), nullable=True, index=True)
    provider_clock = db.Column(db.String(40), nullable=True)
    minute = db.Column(db.Integer, nullable=True, index=True)
    home_score = db.Column(db.Integer, default=0)
    away_score = db.Column(db.Integer, default=0)
    provider_name = db.Column(db.String(80), nullable=True, index=True)
    provider_match_id = db.Column(db.String(120), nullable=True, index=True)
    external_match_id = db.Column(db.String(120), nullable=True, index=True)
    featured = db.Column(db.Boolean, default=False, index=True)
    pinned = db.Column(db.Boolean, default=False, index=True)
    archived = db.Column(db.Boolean, default=False, index=True)
    last_synced_at = db.Column(db.DateTime, nullable=True, index=True)
    stale_after = db.Column(db.DateTime, nullable=True, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    sport = db.relationship("SportsSport")
    competition = db.relationship("SportsCompetition", back_populates="matches")
    season = db.relationship("SportsSeason")
    home_team = db.relationship("SportsTeam", foreign_keys=[home_team_id])
    away_team = db.relationship("SportsTeam", foreign_keys=[away_team_id])
    events = db.relationship("SportsMatchEvent", back_populates="match", cascade="all, delete-orphan", order_by="SportsMatchEvent.sort_order")
    streams = db.relationship("SportsStreamSource", back_populates="match", cascade="all, delete-orphan", order_by="SportsStreamSource.priority")


class SportsMatchEvent(db.Model):
    __tablename__ = "sports_match_event"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("sports_match.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type = db.Column(db.String(50), nullable=False, index=True)
    minute = db.Column(db.Integer, nullable=True, index=True)
    clock = db.Column(db.String(40), nullable=True)
    team_id = db.Column(db.Integer, db.ForeignKey("sports_team.id", ondelete="SET NULL"), nullable=True, index=True)
    player_name = db.Column(db.String(160), nullable=True)
    related_player_name = db.Column(db.String(160), nullable=True)
    summary = db.Column(db.String(300), nullable=True)
    provider_name = db.Column(db.String(80), nullable=True, index=True)
    provider_event_id = db.Column(db.String(120), nullable=True, index=True)
    sort_order = db.Column(db.Integer, default=0, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    occurred_at = db.Column(db.DateTime, nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    match = db.relationship("SportsMatch", back_populates="events")
    team = db.relationship("SportsTeam")


class SportsStanding(db.Model):
    __tablename__ = "sports_standing"

    id = db.Column(db.Integer, primary_key=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("sports_competition.id", ondelete="CASCADE"), nullable=False, index=True)
    season_id = db.Column(db.Integer, db.ForeignKey("sports_season.id", ondelete="SET NULL"), nullable=True, index=True)
    team_id = db.Column(db.Integer, db.ForeignKey("sports_team.id", ondelete="SET NULL"), nullable=True, index=True)
    position = db.Column(db.Integer, nullable=True, index=True)
    played = db.Column(db.Integer, default=0)
    won = db.Column(db.Integer, default=0)
    drawn = db.Column(db.Integer, default=0)
    lost = db.Column(db.Integer, default=0)
    goals_for = db.Column(db.Integer, default=0)
    goals_against = db.Column(db.Integer, default=0)
    goal_difference = db.Column(db.Integer, default=0)
    points = db.Column(db.Integer, default=0, index=True)
    group_name = db.Column(db.String(80), nullable=True, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    last_synced_at = db.Column(db.DateTime, nullable=True, index=True)

    competition = db.relationship("SportsCompetition", back_populates="standings")
    season = db.relationship("SportsSeason")
    team = db.relationship("SportsTeam")


class SportsStreamSource(db.Model):
    __tablename__ = "sports_stream_source"

    id = db.Column(db.Integer, primary_key=True)
    match_id = db.Column(db.Integer, db.ForeignKey("sports_match.id", ondelete="CASCADE"), nullable=True, index=True)
    sport_id = db.Column(db.Integer, db.ForeignKey("sports_sport.id", ondelete="CASCADE"), nullable=True, index=True)
    competition_id = db.Column(db.Integer, db.ForeignKey("sports_competition.id", ondelete="CASCADE"), nullable=True, index=True)
    source_type = db.Column(db.String(40), default="manual", index=True)
    provider_name = db.Column(db.String(80), nullable=True, index=True)
    title = db.Column(db.String(160), nullable=False)
    embed_url = db.Column(db.String(700), nullable=True)
    external_url = db.Column(db.String(700), nullable=True)
    url_pattern = db.Column(db.String(700), nullable=True)
    enabled = db.Column(db.Boolean, default=True, index=True)
    priority = db.Column(db.Integer, default=100, index=True)
    notes = db.Column(db.Text, nullable=True)
    last_checked_at = db.Column(db.DateTime, nullable=True, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    match = db.relationship("SportsMatch", back_populates="streams")
    sport = db.relationship("SportsSport")
    competition = db.relationship("SportsCompetition")


class SportsProviderCache(db.Model):
    __tablename__ = "sports_provider_cache"

    id = db.Column(db.Integer, primary_key=True)
    provider_name = db.Column(db.String(80), nullable=False, index=True)
    cache_key = db.Column(db.String(240), nullable=False, index=True)
    payload = db.Column(db.JSON, nullable=True)
    status = db.Column(db.String(40), default="fresh", index=True)
    expires_at = db.Column(db.DateTime, nullable=False, index=True)
    stale_until = db.Column(db.DateTime, nullable=True, index=True)
    last_error = db.Column(db.Text, nullable=True)
    last_fetched_at = db.Column(db.DateTime, default=datetime.utcnow, index=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("provider_name", "cache_key", name="uq_sports_provider_cache_key"),
    )


class SportsProviderMapping(db.Model):
    __tablename__ = "sports_provider_mapping"

    id = db.Column(db.Integer, primary_key=True)
    provider_name = db.Column(db.String(80), nullable=False, index=True)
    entity_type = db.Column(db.String(40), nullable=False, index=True)
    local_id = db.Column(db.Integer, nullable=True, index=True)
    provider_entity_id = db.Column(db.String(120), nullable=False, index=True)
    provider_payload = db.Column(db.JSON, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        db.UniqueConstraint("provider_name", "entity_type", "provider_entity_id", name="uq_sports_provider_mapping_external"),
    )

class CourseLead(db.Model):
    __tablename__ = "course_lead"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(50), nullable=True)
    course_interest = db.Column(db.String(150), nullable=False)
    date_added = db.Column(db.DateTime, default=datetime.utcnow, index=True)
