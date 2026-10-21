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
app. Switching layout modes does not change any Adsterra or Smartlink code.

```env
# Default when omitted or invalid: legacy
AD_CONFIGURATION=legacy
```

- `legacy`: the existing layout, including every current ad placement.
- `deduped`: removes repeated banner/sidebar calls on the same page while keeping
  the existing Popunder, Smartlink, sticky, native, and Monetag placements.
- `optimized`: the manager test—one clean banner placement per public page
  (728x90 on desktop, 320x50 on mobile, placed nearest the primary user action),
  plus the existing Popunder and Smartlink. It hides sidebar, sticky, and Monetag
  units.

Switching back to `legacy` restores the old rendered placement layout; no ad
placement code or key is deleted.

## Adsterra global script URLs

The global Popunder and Social Bar units use full HTTPS script URLs. Set these
in the deployment environment when Adsterra supplies updated active-code URLs:

```env
AD_POPUNDER_SCRIPT_URL=https://your-adsterra-domain.example/path
AD_SOCIAL_BAR_SCRIPT_URL=https://your-adsterra-domain.example/path
```

Use only the URL from each Adsterra script's `src` attribute, not a complete
`<script>` tag. The application keeps the currently active URLs as defaults so
an unset variable does not interrupt the existing units. `data-cfasync="false"`
remains in the template to prevent Cloudflare Rocket Loader from delaying the
scripts.

## Adsterra 2026 display and Native code format

The current Adsterra display snippets use a full source URL with a `/22/`
segment, while the current Native snippet uses a full source URL with a `/21/`
segment. Configure their exact source shape in the deployment environment:

```env
# The literal {key} is replaced by the matching display-placement key.
AD_IFRAME_SCRIPT_URL_TEMPLATE=https://your-adsterra-domain.example/22/{key}

# The complete Native script src value from Adsterra.
AD_NATIVE_SCRIPT_URL=https://your-adsterra-domain.example/21/your-native-key
```

Keep using `AD_BANNER_KEY`, `AD_BANNER_MOBILE_KEY`, `AD_SIDEBAR_KEY`,
`AD_STICKY_DESKTOP_KEY`, `AD_STICKY_MOBILE_KEY`, and
`AD_NATIVE_PLACEMENT_KEY` for the respective placement keys. If the two new
variables are absent, the app continues to render the original Adsterra
`/invoke.js` URL format for compatibility.

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
