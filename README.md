# IELTS 8+ Bot

Telegram bot that delivers IELTS/Multi-Level video lessons and materials,
gated behind a 4-channel subscription check and a friend-referral unlock
system, plus a FastAPI admin panel for content and broadcast management.

## Stack

- **Bot**: Python 3.12, [aiogram 3](https://docs.aiogram.dev/) (webhook mode)
- **Admin panel**: FastAPI + Jinja2, session-cookie auth
- **DB**: PostgreSQL via SQLAlchemy 2 (async) + asyncpg, Alembic migrations
- **Infra**: Docker Compose (`bot`, `admin`, `postgres`, `caddy`), Caddy for
  automatic HTTPS, systemd unit as a boot-time watchdog

See [DEPLOY.md](./DEPLOY.md) for full droplet setup instructions.

## How it works

### Content delivery
All lesson files (video/pdf/html per day) live in **5 private Telegram
channels** the bot admin controls — one per section (Reading, Listening,
Speaking, Writing, Multi-Level). The admin panel maps
`(section, day_number) -> [message_ids in that channel]`. Delivery to users
uses `copyMessage` (never `forwardMessage`, no "Forwarded from" tag) with
`protect_content=True` so users can't forward/save lesson content. Content
is entirely data-driven — no redeploy needed to add or replace a day.

### Subscription gate
Users must be members of 4 required public channels before using the bot.
The bot must be an **admin** in all 4 (and all 5 content channels) —
required both for `getChatMember` checks and to receive `chat_member`
update events when someone leaves/rejoins.

### Referral / unlock system
- **Reading** is free. **Listening, Speaking, Writing, Multi-Level darslari**
  are locked behind referrals.
- A referral only counts if the invited friend was **not already** a member
  of any of the 4 gate channels at the moment they clicked the link
  (checked and permanently recorded at that instant).
- Every 3 valid referrals = 1 unlock slot. At every multiple of 3 the
  referrer is prompted to choose which still-locked section to spend it on.
  4 sections × 3 = **12 total referrals** to unlock everything.
- If a referred friend later leaves a required channel, their point is
  revoked. If that drops an already-unlocked section's batch below 3, the
  section **re-locks** (future access only — already-delivered messages
  can't be un-sent via Telegram). Re-earning it goes back through the
  section-choice prompt rather than auto-reassigning.

See `common/referral_logic.py` for the full rules and rationale, spelled
out in the module docstring.

## Project layout

```
common/            # shared by bot + admin: config, DB models/engine, referral logic
bot/                # aiogram bot: handlers, keyboards, texts, services
admin/              # FastAPI admin panel: routers, templates, broadcast sender
alembic/            # DB migrations
docker-compose.yml
Dockerfile.bot
Dockerfile.admin
Caddyfile
.env.example
DEPLOY.md
systemd/
```

## Local development (without Docker)

Requires a local Postgres instance.

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

cp .env.example .env   # fill in BOT_TOKEN, DATABASE_URL pointing at your local postgres, etc.
# set USE_WEBHOOK=false in .env for local polling instead of a public webhook

alembic upgrade head

python -m bot.main            # runs the bot (long-polling if USE_WEBHOOK=false)
uvicorn admin.main:app --reload --port 8000   # runs the admin panel
```

## Admin panel

- **Content**: add/edit/delete which source-channel message IDs map to each
  `(section, day)`.
- **Users**: search by ID/username, view referral history, manually
  add/revoke referral points (audit-logged in `admin_actions`).
- **Broadcast**: send to all users / users still mid-funnel (fewer than 12
  valid referrals) / users not currently subscribed to all 4 gate channels.
  Runs as a rate-limited background job (~25 msg/sec) with live progress.
- **Dashboard**: totals, per-section unlock counts, verified-but-zero-referral
  drop-off.

## Open product decision (flagged, not guessed)

Re-locking a section after a referral revocation blocks **future** access
only — it does not (and technically cannot, via Telegram's API) claw back
lessons already delivered with `copyMessage`. This is implemented and
commented in `common/referral_logic.py::revoke_referral`.
