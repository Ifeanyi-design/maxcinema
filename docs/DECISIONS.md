# MAXCINEMA — Architectural Decisions

**Last Updated:** 2026-07-05

This document records why specific architectural decisions were made, so future developers and AI sessions understand the reasoning.

---

## Decision 1: Flask over Django/FastAPI

**Date:** Project inception
**Status:** Accepted

**Context:**
MaxCinema is a movie streaming/download platform with admin CMS, not a complex API-driven application.

**Decision:**
Use Flask as the web framework.

**Rationale:**
- Lightweight and flexible — no opinionated structure forced
- Excellent ecosystem of extensions (Flask-Login, Flask-WTF, Flask-Migrate)
- Simple template rendering with Jinja2
- Easy to deploy on Hugging Face Spaces (Docker + gunicorn)
- Team familiarity with Flask ecosystem

**Alternatives Considered:**
- **Django:** Too heavyweight for this use case. Built-in admin is nice but custom admin was already being built.
- **FastAPI:** Better for API-first applications. MaxCinema is primarily server-rendered HTML with some AJAX.

---

## Decision 2: Neon PostgreSQL over Supabase/PlanetScale

**Date:** Database migration
**Status:** Accepted

**Context:**
Needed a cloud PostgreSQL database for production while keeping SQLite for local development.

**Decision:**
Use Neon PostgreSQL for production database.

**Rationale:**
- Serverless with auto-scaling (good for Hugging Face Spaces)
- Free tier generous for this use case
- Standard PostgreSQL (no vendor lock-in)
- Good Python driver support (psycopg2)
- Easy migration path from SQLite

**Alternatives Considered:**
- **Supabase:** PostgreSQL-based but adds real-time/auth complexity not needed here.
- **PlanetScale:** MySQL-based, would require different driver and dialect.
- **Railway:** Good but more expensive at scale.
- **Self-hosted PostgreSQL:** More operational overhead than necessary.

---

## Decision 3: Hugging Face Spaces for Deployment

**Date:** Deployment setup
**Status:** Accepted

**Context:**
Needed a hosting platform that supports Docker, is free/affordable, and handles Flask apps.

**Decision:**
Deploy on Hugging Face Spaces using Docker.

**Rationale:**
- Free Docker hosting with custom ports
- Automatic HTTPS
- Environment variable management
- Easy deployment from GitHub
- Good for side projects and MVPs

**Alternatives Considered:**
- **Render:** Good free tier but cold starts on free plan.
- **Railway:** Paid only after trial.
- **Vercel:** Serverless-first, not ideal for Flask with background tasks.
- **Heroku:** No longer free tier.

---

## Decision 4: Bytescale for File Storage

**Date:** Storage implementation
**Status:** Accepted

**Context:**
Needed cloud storage for video files with download and streaming capabilities.

**Decision:**
Use Bytescale as primary file storage with Telegram as backup/distribution.

**Rationale:**
- Good CDN performance
- Direct browser uploads
- Range request support (for streaming)
- Reasonable pricing

**Alternatives Considered:**
- **AWS S3:** More complex setup, harder to manage from Flask.
- **Cloudflare R2:** Good but limited streaming features.
- **GoFile:** Free but unreliable.
- **Self-hosted:** Too much operational overhead.

---

## Decision 5: Telegram for Backup Distribution

**Date:** Backup system design
**Status:** Accepted (planned)

**Context:**
Need to store database backups somewhere accessible and reliable.

**Decision:**
Use Telegram Bot API for backup storage and distribution.

**Rationale:**
- Free unlimited file storage (2GB per file)
- Accessible from anywhere
- Easy API integration
- Already used for notifications
- Can be used for manual restore from any device

**Alternatives Considered:**
- **Google Drive:** Requires OAuth setup, API quota limits.
- **S3:** Additional cost and complexity.
- **Email:** File size limits, not designed for binary backups.
- **Local only:** No off-site backup.

---

## Decision 6: NullPool for Neon Connections

**Date:** Database configuration
**Status:** Under review (Phase 3)

**Context:**
Neon PostgreSQL has serverless connection pooling. Need to configure SQLAlchemy engine appropriately.

**Decision:**
Use `NullPool` (fresh connection per request).

**Rationale:**
- Avoids connection state issues with Neon's serverless pooler
- Prevents stale connection errors
- Simple to configure

**Trade-offs:**
- Adds connection latency (~50-100ms per request)
- No connection reuse benefits

**Future Consideration (Phase 3):**
Evaluate `QueuePool` with proper timeouts for better performance.

---

## Decision 7: Application Factory Pattern

**Date:** Project restructure
**Status:** Accepted

**Context:**
Needed a clean way to initialize the Flask app with extensions, blueprints, and configuration.

**Decision:**
Use Flask Application Factory pattern (`create_app()`).

**Rationale:**
- Clean separation of concerns
- Easy testing (can create test app with different config)
- Blueprint registration is explicit
- Context processors added cleanly
- Standard Flask best practice

---

## Decision 8: Tailwind CSS over Bootstrap/custom CSS

**Date:** Frontend styling
**Status:** Accepted

**Context:**
Needed a CSS framework for rapid UI development.

**Decision:**
Use Tailwind CSS 3.4 with PostCSS.

**Rationale:**
- Utility-first approach enables rapid prototyping
- No need to write custom CSS for most components
- Small production bundle with purging
- Good documentation and ecosystem
- Modern developer experience

**Alternatives Considered:**
- **Bootstrap:** More opinionated, harder to customize look.
- **Custom CSS:** Too slow for rapid development.
- **Bulma:** Good but less flexible than Tailwind.

---

## Decision 9: Synchronous Notifications (Current)

**Date:** Notification implementation
**Status:** Under review (future improvement)

**Context:**
Need to send email and Telegram notifications when content is released.

**Decision:**
Send notifications synchronously in the request cycle.

**Rationale:**
- Simple implementation
- No additional infrastructure needed
- Works for small user base

**Known Limitation:**
- Admin waits for all notifications to send
- Slow with 1000+ subscribers
- No retry on failure

**Future Improvement:**
Move to background task queue (when infrastructure allows).

---

## Decision 10: Separate Backup Service

**Date:** Backup system design
**Status:** Planned (Phase 4)

**Context:**
Need automated PostgreSQL backups with Telegram integration.

**Decision:**
Create independent `backup_service/` directory, separate from MaxCinema.

**Rationale:**
- Can be deployed independently
- Can be copied to another repository
- Clean separation of concerns
- No dependency on main application
- Can be developed and tested in isolation

**Architecture:**
- Lightweight Flask app with API endpoints
- PostgreSQL SQL dump (not custom format for now)
- Telegram upload/download
- Metadata tracking
- No heavy infrastructure (Celery, Redis, etc.)
