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
    trailer_url = db.Column(db.String(300))
    total_comment = db.Column(db.Integer, default=0, nullable=True)
    video_360p = db.Column(db.String(500))  # path or URL
    video_480p = db.Column(db.String(500))
    video_720p = db.Column(db.String(500))
    video_1080p = db.Column(db.String(500))
    video_qualities = db.Column(db.JSON)

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
    seasons = db.relationship('Season', back_populates='series', cascade="all, delete-orphan")

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
    episodes = db.relationship('Episode', back_populates='season', cascade="all, delete-orphan")

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
    video_360p = db.Column(db.String(500))
    video_480p = db.Column(db.String(500))
    video_720p = db.Column(db.String(500))
    video_1080p = db.Column(db.String(500))

    thumb_360p = db.Column(db.String, nullable=True)
    thumb_480p = db.Column(db.String, nullable=True)
    thumb_720p = db.Column(db.String, nullable=True)
    thumb_1080p = db.Column(db.String, nullable=True)

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