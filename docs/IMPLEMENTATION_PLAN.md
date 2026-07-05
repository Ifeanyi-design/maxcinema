# MAXCINEMA — Implementation Plan

**Last Updated:** 2026-07-05

---

## Phase 1: Security Hardening

**Goal:** Eliminate all security vulnerabilities without changing functionality.

**Why:** Hardcoded secrets, missing auth, and weak defaults expose the application to credential theft, session forgery, and unauthorized access.

### Tasks

#### 1.1 Move Secrets to Environment Variables
- **Files:** `app/config.py`, `app/utils.py`, `app/getthem.py`, `migrate_to_neon.py`
- **Complexity:** Low
- **Dependencies:** None
- **Risks:** App will fail to start if env vars missing (intentional — fail loudly)
- **Rollback:** Revert file changes

| Current Location | Secret | Action |
|-----------------|--------|--------|
| `config.py:79` | `BYTESCALE_API_KEY` | Move to env var |
| `config.py:80` | `BYTESCALE_ACCOUNT_ID` | Move to env var |
| `utils.py:16` | TMDB API key | Move to env var |
| `getthem.py:146` | TMDB API key | Move to env var or delete file |
| `migrate_to_neon.py:13` | Neon DB credentials | Move to env var |

#### 1.2 Fix Default SECRET_KEY
- **Files:** `app/config.py`
- **Complexity:** Low
- **Dependencies:** None
- **Risks:** App crashes if SECRET_KEY not set (intentional)
- **Rollback:** Revert file change

Change from:
```python
SECRET_KEY = os.environ.get("SECRET_KEY", "supersecretkey")
```
To:
```python
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    raise RuntimeError("SECRET_KEY environment variable is required")
```

#### 1.3 Review and Fix Admin Route Authorization
- **Files:** `app/admin/views.py`
- **Complexity:** Medium
- **Dependencies:** None
- **Risks:** Breaking admin functionality if routes incorrectly protected
- **Rollback:** Revert file changes

Routes to review:
| Route | Current Auth | Required Action |
|-------|-------------|-----------------|
| `view_trailers` | None | Add `@login_required` |
| `delete_storage_server` | Commented out | Restore `@login_required` + `@admin_required` |
| `view_requests` | `@login_required` only | Add `@admin_required` |
| `update_request_status` | `@login_required` only | Add `@admin_required` |
| `delete_request` | `@login_required` only | Add `@admin_required` |
| `admin_uploads` (main_routes) | None | Add `@login_required` + `@admin_required` |

#### 1.4 Fix Broken forms.py
- **Files:** `app/forms.py`
- **Complexity:** Low
- **Dependencies:** None
- **Risks:** None — file is currently broken/unused
- **Rollback:** Revert file change

Action: Rename to `export_db.py` or delete entirely.

#### 1.5 Remove Debug Mode Default
- **Files:** `run.py`
- **Complexity:** Low
- **Dependencies:** None
- **Risks:** None
- **Rollback:** Revert file change

Change `debug=True` to `debug=os.environ.get("FLASK_DEBUG", "0").lower() == "1"`

---

## Phase 2: Admin Refactoring

**Goal:** Split `admin/views.py` (2385 lines) into smaller, maintainable modules.

**Why:** Single 2385-line file is difficult to navigate, maintain, and debug.

### Tasks

#### 2.1 Create Admin Module Structure
- **Files:** `app/admin/` directory
- **Complexity:** Medium-High
- **Dependencies:** Phase 1 complete
- **Risks:** Import errors, broken routes
- **Rollback:** Revert all file changes

Target structure:
```
app/admin/
├── __init__.py          # Blueprint registration
├── views.py             # Dashboard + core routes only (~500 lines)
├── movies.py            # Movie CRUD routes
├── series.py            # Series/Season/Episode CRUD routes
├── trailers.py          # Trailer CRUD routes
├── users.py             # User management routes
├── storage.py           # Storage server routes
├── notifications.py     # Email/Telegram notification routes
├── analytics.py         # Stats dashboard, search terms
├── polls.py             # Weekly poll management
├── leads.py             # Course leads management
├── helpers.py           # Shared helper functions
└── templates/admin/     # (unchanged)
```

#### 2.2 Extract Shared Helper Functions
- **Files:** `app/admin/helpers.py` (new)
- **Complexity:** Medium
- **Dependencies:** 2.1
- **Risks:** Import path changes
- **Rollback:** Revert file changes

Functions to extract:
- Sidebar data loading (duplicated 15+ times)
- Admin stats counters
- Common query patterns

#### 2.3 Reduce Sidebar Data Duplication
- **Files:** `app/admin/helpers.py`, all admin view files
- **Complexity:** Medium
- **Dependencies:** 2.1, 2.2
- **Risks:** Template variable name changes
- **Rollback:** Revert file changes

Create `get_admin_sidebar_data()` helper, call from each route.

---

## Phase 3: Performance Improvements

**Goal:** Add targeted caching and fix query performance issues.

**Why:** N+1 queries and repeated expensive queries slow down page loads.

### Tasks

#### 3.1 Fix N+1 Query in build_comment_badges()
- **Files:** `app/main_routes.py`
- **Complexity:** Medium
- **Dependencies:** None
- **Risks:** Badge logic changes
- **Rollback:** Revert file change

Replace per-email queries with single grouped query.

#### 3.2 Add Lightweight Caching for Trending Data
- **Files:** `app/main_routes.py`, `app/__init__.py`
- **Complexity:** Medium
- **Dependencies:** None
- **Risks:** Stale data display
- **Rollback:** Revert file changes

Cache trending movies, trending series, trending trailers for 5 minutes.

#### 3.3 Cache Admin Dashboard Stats
- **Files:** `app/admin/analytics.py` (after Phase 2)
- **Complexity:** Medium
- **Dependencies:** Phase 2
- **Risks:** Stale stats
- **Rollback:** Revert file changes

Cache expensive stats queries for 10 minutes.

#### 3.4 Review Database Connection Pooling
- **Files:** `app/config.py`
- **Complexity:** Low
- **Dependencies:** None
- **Risks:** Connection leaks if misconfigured
- **Rollback:** Revert file change

Current: `NullPool` (fresh connection per request). Evaluate if `QueuePool` would improve Neon performance.

---

## Phase 4: Backup & Restore Service

**Goal:** Create independent backup service for PostgreSQL backups.

**Why:** Current backup is manual script. Need automated, reliable backup with Telegram integration.

### Tasks

#### 4.1 Create Backup Service Structure
- **Files:** `backup_service/` directory (new, independent)
- **Complexity:** High
- **Dependencies:** None
- **Risks:** Service deployment complexity
- **Rollback:** Delete directory

```
backup_service/
├── __init__.py
├── app.py              # Flask app with API endpoints
├── config.py           # Configuration
├── backup.py           # PostgreSQL backup logic
├── restore.py          # PostgreSQL restore logic
├── telegram.py         # Telegram upload/download
├── metadata.py         # Backup metadata tracking
├── requirements.txt    # Independent dependencies
├── Dockerfile          # Independent deployment
└── README.md           # Documentation
```

#### 4.2 Implement Backup Logic
- **Files:** `backup_service/backup.py`
- **Complexity:** Medium
- **Dependencies:** 4.1
- **Risks:** Data loss if backup fails silently
- **Rollback:** Revert file changes

Features:
- PostgreSQL SQL dump (designed for future custom format)
- Timestamped backup files
- Metadata tracking (size, duration, status)
- Temporary file cleanup

#### 4.3 Implement Telegram Integration
- **Files:** `backup_service/telegram.py`
- **Complexity:** Medium
- **Dependencies:** 4.2
- **Risks:** Telegram API rate limits
- **Rollback:** Revert file changes

Features:
- Upload backup to Telegram channel
- Download backup from Telegram
- File size limits handling

#### 4.4 Implement Restore Logic
- **Files:** `backup_service/restore.py`
- **Complexity:** Medium
- **Dependencies:** 4.2
- **Risks:** Data loss, database corruption
- **Rollback:** Revert file changes

Features:
- Restore from local backup
- Restore from Telegram backup
- Restore verification

#### 4.5 Create API Endpoints
- **Files:** `backup_service/app.py`
- **Complexity:** Medium
- **Dependencies:** 4.2, 4.3, 4.4
- **Risks:** Unauthorized access
- **Rollback:** Revert file changes

Endpoints:
- `POST /backup` — Trigger backup
- `POST /restore` — Trigger restore
- `GET /status` — Check backup status
- `GET /list` — List available backups

---

## Phase 5: Admin Email Tools

**Goal:** Add simple email sending capability to admin panel.

**Why:** Admin needs to send manual emails to users without leaving the dashboard.

### Tasks

#### 5.1 Create Email Route Module
- **Files:** `app/admin/email.py` (new)
- **Complexity:** Medium
- **Dependencies:** Phase 2
- **Risks:** Email delivery failures
- **Rollback:** Revert file changes

Features:
- Send email to single recipient
- Use existing email configuration (Resend/SMTP)
- Basic email templates

#### 5.2 Create Email Templates
- **Files:** `app/templates/emails/` directory
- **Complexity:** Low
- **Dependencies:** 5.1
- **Risks:** None
- **Rollback:** Revert file changes

Templates:
- Welcome email
- Generic notification
- Custom message

#### 5.3 Add Email History
- **Files:** `app/models.py`, `app/admin/email.py`
- **Complexity:** Low
- **Dependencies:** 5.1
- **Risks:** Database migration needed
- **Rollback:** Revert file changes

Model: `EmailHistory` — tracks sent emails (recipient, subject, status, timestamp)

#### 5.4 Create Admin Email Page
- **Files:** `app/admin/templates/admin/email.html` (new)
- **Complexity:** Low
- **Dependencies:** 5.1
- **Risks:** None
- **Rollback:** Revert file changes

UI:
- Compose form (to, subject, body)
- Template selector
- Send button
- History list

---

## Dependencies Summary

```
Phase 1 (Security) ──────────────┐
                                  ├──> Phase 2 (Admin Refactoring) ──> Phase 5 (Email Tools)
Phase 3 (Performance) ───────────┘
                                  
Phase 4 (Backup Service) ──────── Independent
```

---

## Estimated Timeline

| Phase | Complexity | Estimated Effort |
|-------|-----------|-----------------|
| Phase 1: Security | Low-Medium | 1-2 hours |
| Phase 2: Admin Refactoring | Medium-High | 3-4 hours |
| Phase 3: Performance | Medium | 2-3 hours |
| Phase 4: Backup Service | High | 4-6 hours |
| Phase 5: Email Tools | Medium | 2-3 hours |
| **Total** | | **12-18 hours** |
