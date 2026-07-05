# MAXCINEMA — Architecture Documentation

**Last Updated:** 2026-07-05

---

## Project Structure

```
MAXCINEMA/
├── app/                          # Main Flask application
│   ├── __init__.py               # App factory with context processors
│   ├── config.py                 # Configuration (DB, API keys, etc.)
│   ├── extensions.py             # Flask extensions (db, migrate, login_manager)
│   ├── models.py                 # 25+ SQLAlchemy models (642 lines)
│   ├── main_routes.py            # All public routes (2095 lines)
│   ├── listeners.py              # SQLAlchemy event listeners
│   ├── utils.py                  # TMDB content importer
│   ├── indexnow.py               # IndexNow SEO submission
│   ├── forms.py                  # BROKEN: DB export script (not forms)
│   ├── getthem.py                # Dead/commented code
│   │
│   ├── admin/                    # Admin blueprint
│   │   ├── __init__.py           # Blueprint registration
│   │   ├── views.py              # All admin routes (2385 lines)
│   │   ├── forms.py              # WTForms definitions
│   │   └── templates/admin/      # 30+ admin templates
│   │
│   ├── sports/                   # Sports Hub blueprint
│   │   ├── __init__.py           # Blueprint registration
│   │   ├── routes.py             # Sports public routes + API
│   │   ├── services.py           # Cache, sync, provider logic
│   │   ├── providers.py          # Provider adapters
│   │   ├── stream_resolver.py    # Stream source resolution
│   │   ├── state.py              # MatchState dataclass
│   │   ├── serializers.py        # Payload serializers
│   │   └── retention.py          # Data cleanup
│   │
│   ├── templates/                # Public HTML templates
│   │   ├── base.html             # Base layout
│   │   ├── header.html           # Desktop header
│   │   ├── darkheader.html       # Mobile header
│   │   ├── footer.html           # Footer
│   │   ├── index.html            # Homepage
│   │   ├── movie.html            # Movie detail
│   │   ├── stream.html           # Streaming page
│   │   ├── download.html         # Download page
│   │   ├── emails/               # Email templates
│   │   ├── ads/                  # Ad partials
│   │   └── sports/               # Sports templates
│   │
│   └── static/                   # Static assets
│       ├── css/style.css         # Compiled Tailwind (7384 lines)
│       ├── src/input.css         # Tailwind input
│       ├── js/                   # JavaScript files
│       └── images/               # Static images
│
├── backup_service/               # Independent backup service (Phase 4)
│   └── (to be created)
│
├── migrations/                   # Alembic migrations
├── instance/                     # SQLite database files
├── docs/                         # Project documentation
├── .env                          # Environment variables
├── run.py                        # Application entry point
├── requirements.txt              # Python dependencies
├── Dockerfile                    # Docker build
├── package.json                  # Node.js (Tailwind build only)
└── tailwind.config.js            # Tailwind configuration
```

---

## Blueprints

### Main Blueprint (`main`)
- **Prefix:** `/` (root)
- **File:** `app/main_routes.py`
- **Purpose:** All public-facing routes
- **Routes:** Homepage, movie/series detail, streaming, download, search, genre, trailers, comments, ratings, polls, requests, notifications, sitemap, analytics

### Admin Blueprint (`admin`)
- **Prefix:** `/admin`
- **File:** `app/admin/views.py`
- **Purpose:** Content management and administration
- **Routes:** Dashboard, CRUD for movies/series/trailers/users/storage, notifications, stats, polls, leads, search terms

### Sports Blueprint (`sports`)
- **Prefix:** `/sports`
- **File:** `app/sports/routes.py`
- **Purpose:** Sports hub functionality
- **Routes:** Sports home, competition detail, match detail, watch match, API endpoints

---

## Services

### TMDB Content Importer (`app/utils.py`)
- Import movies/series from TMDB API
- Fetch metadata, cast, trailers, genres
- Auto-generate slugs

### IndexNow (`app/indexnow.py`)
- Submit URLs to search engines on content changes
- Support Bing, Yandex, and other IndexNow partners

### Sports Services (`app/sports/services.py`)
- Live match synchronization
- Provider caching with configurable TTLs
- Stale fallback for provider unavailability

---

## Utilities

### Event Listeners (`app/listeners.py`)
- Auto-generate slugs on AllVideo/Trailer insert/update
- Maintain RecentItem table on content changes

### Stream Resolver (`app/sports/stream_resolver.py`)
- Manual admin override > provider lookup > fallback

---

## Database

### Primary: Neon PostgreSQL
- Serverless PostgreSQL with connection pooling
- Used in production (Hugging Face Spaces)

### Fallback: SQLite
- Used for local development
- Auto-detected based on `DATABASE_URL` env var

### Models (25+)
- **Content:** AllVideo, Movie, Series, Season, Episode, Trailer
- **Interaction:** Rating, Comment, MovieRequest, WeeklyPoll
- **Users:** User, WatchlistNotify, CourseLead
- **Analytics:** SearchTerm, AnalyticsEvent, RecentItem
- **Storage:** StorageServer
- **Sports:** SportsSport, SportsCompetition, SportsTeam, SportsSeason, SportsMatch, SportsMatchEvent, SportsStanding, SportsStreamSource, SportsProviderCache, SportsProviderMapping

---

## Authentication

### Flask-Login
- Session-based authentication
- `@login_required` decorator for protected routes
- `@admin_required` custom decorator for admin-only routes

### Session Security
- SECRET_KEY from environment variable
- CSRF protection via Flask-WTF
- Session-based spam guard (12s cooldown)

---

## Background Services

### Current: Synchronous
- Email notifications sent in request cycle
- Telegram notifications sent in request cycle
- No background job system

### Planned (Phase 4): Backup Service
- Independent Flask service
- PostgreSQL backup/restore
- Telegram integration for backup storage

---

## Caching

### Current: Minimal
- Sports provider cache in database (configurable TTLs)
- No application-level caching

### Planned (Phase 3): Lightweight Caching
- Trending data caching (5 minutes)
- Admin stats caching (10 minutes)
- Comment badge caching

---

## Admin

### Dashboard
- Content counts (movies, series, trailers, users)
- Storage health monitoring
- Recent analytics

### Content Management
- Full CRUD for movies, series, seasons, episodes
- TMDB import with metadata auto-fill
- Bulk link assignment for series
- Incomplete content tracking

### Analytics
- Top content by views
- Request funnel analysis
- Ad performance metrics
- Search term analytics

---

## Email

### Providers
- **Resend API:** Primary email provider
- **SMTP:** Fallback email provider

### Templates
- Release notification (`release_notification.html`)
- (Phase 5) Welcome email, generic notification, custom message

### Configuration
- All keys stored in environment variables
- Configurable via admin notification settings page

---

## Backup System

### Current: Manual
- `backup.py` script (mostly commented out)
- `db_backup.json` export

### Planned (Phase 4): Automated Service
- Independent `backup_service/` directory
- PostgreSQL SQL dump
- Telegram integration for backup storage
- Restore from local or Telegram
- Metadata tracking

---

## Ad/Monetization System

### Providers
- **Adsterra:** Popunder, in-page, push ads
- **Monetag:** In-page, vignette, push ads

### Ad Positions
- Banner (desktop 728x90, mobile 320x50)
- Sidebar (300x250)
- Sticky (desktop/mobile)
- Popunder

### Features
- Cooldown-based frequency capping
- Country-based ad targeting (Cloudflare headers)
- Ad analytics (views, clicks, CTR)
- Server-side key management (all keys in env vars)
