---
title: Maxcinema Live
emoji: 🎬
colorFrom: purple
colorTo: red
sdk: docker
pinned: false
license: apache-2.0
---

# MaxCinema Live
This is the live version of the MaxCinema movie database app, running on Docker and Neon Postgres.

## Reversible ad layout modes

Set `AD_CONFIGURATION` in the deployment environment, then restart/redeploy the
app. No Adsterra key or Smartlink/Popunder code needs to be changed.

```env
# Default when omitted or invalid: legacy
AD_CONFIGURATION=legacy
```

- `legacy`: the existing layout, including every current ad placement.
- `deduped`: removes repeated banner/sidebar calls on the same page while keeping
  the existing Popunder, Smartlink, sticky, native, and Monetag placements.
- `optimized`: the later manager test—one desktop 728x90 placement per public
  page (with the download-page placement kept beside the server choices), plus
  the existing Popunder and Smartlink. It hides mobile, sidebar, sticky, native,
  and Monetag units.

Switching back to `legacy` restores the old rendered placement layout; no ad
placement code or key is deleted.

## Telegram Relay

If the main host cannot reach `api.telegram.org` reliably, deploy `telegram_relay.py`
as a small Render web service and point the main app to it.

Render start command:

```bash
gunicorn telegram_relay:app
```

Render relay environment:

```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_RELAY_SECRET=use_a_long_random_secret
```

Main app environment:

```env
TELEGRAM_NOTIFY_CHAT_ID=-1001234567890
TELEGRAM_NOTIFY_GROUP_URL=https://t.me/your_notify_group
TELEGRAM_MAIN_GROUP_URL=https://t.me/MaxCinemaOfficial
TELEGRAM_RELAY_URL=https://your-render-service.onrender.com/telegram/send
TELEGRAM_RELAY_SECRET=use_the_same_long_random_secret
```
