# MaxCinema Content Agent API

The API is a controlled execution layer for an external AI agent. The agent is responsible for reasoning over Telegram TXT exports, preserving filename/code pairs, identifying season and episode numbers, resolving ambiguous TMDB search results, and asking the user before risky changes. Flask validates and executes explicit operations; it does not perform LLM-based filename matching.

## Confirmed operating policy

- New imports are public by default (active=true).
- A future movie/series release is marked Coming Soon. Released content without a download link remains published and should show the site's missing-link state.
- Series imports create episode rows only when TMDB supplies a confirmed air date on or before the current UTC date. Future-dated and undated episodes are skipped. Existing rows are not deleted by sync.
- Link previews fill missing links by default and preserve existing links.
- Replacements require a preview followed by explicit user approval and confirm_replacements=true on apply.
- featured and trending may only be changed when the user explicitly instructs the agent; the API requires an editorial_reason alongside those fields.
- Series sync is manual/on-demand in v1. This avoids adding a fragile in-process scheduler to the Hugging Face web process. A durable scheduled runner can call the sync endpoint later.

## Pairing and authentication

1. In the MaxCinema admin panel, open /admin/agent-access.
2. Generate a one-time pairing code. It is high entropy, valid for 10 minutes, and can be exchanged once.
3. The agent sends POST /api/agent/v1/pair with JSON containing code and an optional label.
4. The response contains a bearer token valid for 60 minutes. Store it in the agent's secret manager/environment configuration, not in prompts, logs, or source control.
5. Send Authorization: Bearer mca_... on subsequent requests.
6. Revoke sessions from /admin/agent-access.

The database stores only SHA-256 hashes of pairing codes and bearer tokens. The API does not expose database credentials or arbitrary SQL.

## Endpoints

All endpoints except POST /pair require a bearer token.

- GET /capabilities
- GET /openapi.json
- GET /tmdb/search?q=...&type=all|movie|series
- GET /library/search?q=... or ?tmdb_id=...
- GET /storage-servers
- GET /series/{all_video_id}/status
- POST /movies/import with a numeric TMDB movie ID
- POST /series/import with a numeric TMDB TV ID and optional seasons
- POST /series/{all_video_id}/sync with optional seasons and episode range
- PATCH /library/{all_video_id}
- PATCH /seasons/{season_id}
- PATCH /episodes/{episode_id}
- POST /links/preview
- POST /links/apply

## Link intake workflow

The agent must read the original Telegram TXT export and retain the filename-to-code association for each row. It should then inspect the library's season/episode list and produce explicit assignments with episode_number, code, and source_filename. Explicit assignments are safer than positional lists because they cannot silently shift when an episode is missing from the export. ordered_codes remains available for a positional batch when the agent has verified the exact order.

Call /links/preview first. Review the returned assignments and skipped targets. If any replacement is shown, present the old/new target mapping to the user and wait for approval. Then call /links/apply with the returned preview_token; include confirm_replacements=true only after explicit approval. Preview tokens expire after 15 minutes.

## Release-date semantics

TMDB can list future episodes before broadcast. The importer must not create those episode rows before their air date. It also skips episodes without an air date because their release state cannot be confirmed. When those episodes air, a later manual sync can import them. Existing records and links are preserved. A primary link assignment clears the item's Coming Soon flag.

## Notes

- TMDB search can return multiple candidates; the agent must ask the user to select when title/year/type do not identify one unambiguously.
- Country values are preserved as TMDB supplies them; the current Hollywood filter already matches the substring United States, including United States of America.
- Season.completed describes editorial season completion, not whether episodes have download links.
- The actual Telegram media-ingestion bot is outside this repository. Direct bot integration is a separate phase; this API accepts codes supplied by the agent.


## Database migration and deployment

This repository's Docker startup command does not automatically run Alembic migrations. Before using the new agent-access page or API on a deployed environment, apply the new migration once against the same production database used by MaxCinema:

    flask --app run db upgrade

Run this in the Hugging Face Space/container environment (or another trusted environment configured with the production DATABASE_URL and SECRET_KEY). Take a database backup first. Do not use db.create_all() as a substitute for the production migration. The GitHub deploy workflow only deploys pushes to clean-main; this feature branch does not deploy to the live Space.

The external agent's operating instructions are in docs/AI_AGENT_SYSTEM_PROMPT.md.
