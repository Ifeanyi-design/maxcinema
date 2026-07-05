# MAXCINEMA — Changelog

All notable changes to this project will be documented in this file.

Format based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [Unreleased]

### Added (Phase 5 — 2026-07-05)
- Admin email tools (`app/admin/email.py`):
  - Compose and send emails from admin panel
  - Select recipients from user list
  - Choose from 3 email templates (welcome, notification, custom)
  - Email history with status tracking
- `EmailHistory` model for tracking sent emails
- Email templates (`app/templates/emails/`):
  - `welcome.html` — Welcome email template
  - `generic_notification.html` — Generic notification template
  - `custom_message.html` — Custom message with CTA template
- Admin email page (`app/admin/templates/admin/email.html`)

### Added (Phase 4 — 2026-07-05)
- Independent backup service (`backup_service/` directory):
  - PostgreSQL backup via `pg_dump` with timestamped files
  - Telegram integration for offsite backup storage
  - Restore from local backup or Telegram
  - REST API with API key authentication
  - Configurable retention policy (auto-cleanup)
  - Docker support included
  - Metadata tracking for all backups

### Performance (Phase 3 — 2026-07-05)
- Fixed N+1 query in `build_comment_badges()` — reduced from N+1 queries to 1 query
- Added 5-minute in-memory cache for sidebar trending data
- Added 10-minute in-memory cache for admin stats dashboard
- Reviewed database connection pooling (kept `NullPool` for Neon compatibility)

### Changed (Phase 2 — 2026-07-05)
- Split `admin/views.py` (2385 lines) into 11 focused modules:
  - `helpers.py` — Shared helper functions
  - `movies.py` — Movie CRUD routes
  - `series.py` — Series/Season/Episode CRUD routes
  - `trailers.py` — Trailer CRUD routes
  - `users.py` — User management routes
  - `storage.py` — Storage server routes
  - `notifications.py` — Email/Telegram notification routes
  - `analytics.py` — Stats dashboard and search terms
  - `polls.py` — Weekly poll management
  - `leads.py` — Course leads management
  - `content.py` — TMDB import, bulk links, incomplete content, search, IndexNow
- Reduced `admin/views.py` from 2385 lines to 220 lines (91% reduction)

### Security (Phase 2 — 2026-07-05)
- Added `@login_required` + `@admin_required` to `view_users` (was publicly accessible)
- Added `@login_required` + `@admin_required` to `view_storage` (was publicly accessible)
- Added `@admin_required` to `edit_video` (was only `@login_required`)

### Fixed (Phase 2 — 2026-07-05)
- Fixed `add_storage_server` redirect to use correct endpoint (`admin.view_storage` instead of `admin.list_storage_servers`)

### Security (Phase 1 — 2026-07-05)
- Moved hardcoded `BYTESCALE_API_KEY` and `BYTESCALE_ACCOUNT_ID` to environment variables
- Moved hardcoded TMDB API key to `TMDB_API_KEY` environment variable
- Moved hardcoded Neon DB credentials to `DATABASE_URL` environment variable
- Changed `SECRET_KEY` to require environment variable (fails loudly if missing)
- Fixed admin route authorization:
  - Added `@login_required` to `view_trailers`
  - Restored `@login_required` + `@admin_required` to `delete_storage_server`
  - Added `@admin_required` to `view_requests`, `update_request_status`, `delete_request`
  - Added `@login_required` + `@admin_required` to `admin_uploads`
- Disabled debug mode by default (only enabled via `FLASK_DEBUG=1`)

### Fixed
- Notification email URLs now use correct download routes (`/download/movie/...` and `/download/series/...`) instead of broken `/watch_movie/` and `/watch_series/` routes
- Default `SITE_BASE_URL` updated to include `www` prefix

### Removed
- Deleted `app/forms.py` (broken DB export script that crashed on import)
- Deleted `app/getthem.py` (dead code with broken imports and hardcoded TMDB key)

---

## [Previous Updates]

### Added
- Sports Hub with live match tracking
- Weekly poll system
- Watchlist notification system (email + Telegram)
- TMDB content importer
- Multi-storage server support (Bytescale, Telegram, GoFile, etc.)
- IndexNow SEO integration
- Admin analytics dashboard with Chart.js
- Comment badge system (Rising Voice, Contributor, Top Fan, Legend)
- Release calendar page
- Movie request system
- Course lead capture system
- Search term analytics
- Bulk link assignment for series episodes

### Changed
- Migrated from SQLite to Neon PostgreSQL for production
- Upgraded to Tailwind CSS 3.4
- Refactored to Flask Application Factory pattern

### Fixed
- Search redirect handler using slugify for URL-safe fallback
- Duplicate Edit buttons removed for movies in search and list views

---

## Version History

| Version | Date | Description |
|---------|------|-------------|
| Current | 2026-07-05 | Phase 5 Admin Email Tools complete |
| - | 2026-07-05 | Phase 4 Backup Service complete |
| - | 2026-07-05 | Phase 3 Performance Improvements complete |
| - | 2026-07-05 | Phase 2 Admin Refactoring complete |
| - | 2026-07-05 | Phase 1 Security Hardening complete |
| - | - | Initial development |
