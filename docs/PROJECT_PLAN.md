# MAXCINEMA — Project Plan

**Last Updated:** 2026-07-05
**Status:** Active Development

---

## Overview

MaxCinema is a Flask-based movie and series streaming/download platform with admin CMS, sports hub, notification system, and multi-storage backend support. Deployed on Hugging Face Spaces with Neon PostgreSQL.

---

## Current Architecture

### Tech Stack
| Layer | Technology |
|-------|-----------|
| Backend | Flask 3.1.2, Python 3.10+ |
| Database | Neon PostgreSQL (production), SQLite (local) |
| ORM | SQLAlchemy 2.0.44 via Flask-SQLAlchemy |
| Migrations | Alembic via Flask-Migrate |
| Auth | Flask-Login |
| Forms | Flask-WTF / WTForms |
| Frontend | Tailwind CSS 3.4, Vanilla JS |
| Deployment | Docker on Hugging Face Spaces |
| Storage | Bytescale, Telegram, GoFile, local |
| Email | Resend API / SMTP |
| SEO | IndexNow, dynamic sitemap |

### Blueprint Structure
```
app/
├── __init__.py          # App factory
├── main_routes.py       # Public routes (2095 lines)
├── admin/
│   ├── __init__.py      # Admin blueprint
│   └── views.py         # Admin routes (2385 lines)
├── sports/
│   ├── __init__.py      # Sports blueprint
│   ├── routes.py        # Sports routes
│   ├── services.py      # Sports services
│   └── providers.py     # Provider adapters
├── models.py            # 25+ SQLAlchemy models
├── config.py            # Configuration
└── extensions.py        # Flask extensions
```

### Database Models (25+)
- User, Genre, AllVideo, Movie, Series, Season, Episode
- Rating, Comment, Trailer, StorageServer
- RecentItem, MovieRequest, SearchTerm, AnalyticsEvent
- WatchlistNotify, WeeklyPoll, WeeklyPollOption, WeeklyPollVote
- SportsSport, SportsCompetition, SportsTeam, SportsSeason
- SportsMatch, SportsMatchEvent, SportsStanding
- SportsStreamSource, SportsProviderCache, SportsProviderMapping
- CourseLead

---

## Goals

### Primary Objectives
1. **Security Hardening** — Eliminate all hardcoded secrets, fix auth gaps
2. **Code Maintainability** — Split monolithic files, reduce duplication
3. **Performance** — Add targeted caching, fix N+1 queries
4. **Operational Reliability** — Independent backup service, proper logging

### Constraints
- Do NOT break existing functionality
- Do NOT change URLs or model names without approval
- Do NOT introduce heavy infrastructure (Celery, Redis, etc.) unless approved
- Prefer small, safe, incremental improvements

---

## Identified Risks

### Critical
1. **Hardcoded secrets** in `config.py`, `utils.py`, `migrate_to_neon.py` — exposed in git history
2. **Weak default SECRET_KEY** — sessions forgeable if env var missing
3. **Missing auth on admin routes** — some sensitive routes unprotected
4. **Debug mode** in `run.py` — could run in production accidentally

### High
5. **Monolithic files** — `main_routes.py` (2095 lines), `admin/views.py` (2385 lines)
6. **N+1 query patterns** — `build_comment_badges()`, `stats_dashboard()`
7. **No rate limiting** — brute-force, DDoS possible
8. **No connection pooling** — `NullPool` with Neon adds latency

### Medium
9. **50+ `print()` statements** — no structured logging
10. **Massive code duplication** — sidebar queries 15x, MockGenre 4x
11. **Dead/broken code** — `forms.py` is DB export script, `getthem.py` broken imports
12. **Synchronous notifications** — blocks admin on 1000+ subscribers

---

## Future Improvements (Planning Only)

- Worker/job service for background tasks
- Scheduled automated backups
- Advanced monitoring and alerting
- Email verification for admin users
- Content Security Policy headers
- Database connection pooling optimization
- Restore verification system

---

## Decisions Log

See `DECISIONS.md` for detailed architectural decision records.
