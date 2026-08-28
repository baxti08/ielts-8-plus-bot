# DEPLOY.md — IELTS 8+ Bot

Exact steps to take this from zero to a running bot + admin panel on a fresh
DigitalOcean droplet.

## 0. Why webhook, not long polling

Webhook was chosen over long polling: at this scale (broadcasts to up to
~50k users, an admin panel that needs to be reachable anyway, a single
droplet), running Caddy for the admin panel's HTTPS is already required —
reusing that same Caddy + domain for the bot's webhook costs nothing extra,
avoids a permanently-open long-poll connection competing for the same
event loop as admin traffic, and gives Telegram push delivery instead of
the bot repeatedly asking "anything new?". Long polling would be simpler to
reason about with zero infra, but since Caddy/HTTPS is non-negotiable here
anyway, webhook is the better fit.

## 1. Create the droplet

1. DigitalOcean → Create → Droplets
2. Image: **Ubuntu 24.04 (LTS) x64**
3. Plan — you're expecting up to **50,000 total users**, which puts you in
   the "tens of thousands" band: go with **4 GB RAM / 2 vCPU** to start.
   The connection-pool and webhook tuning in step 13 lets it absorb short
   traffic bursts well beyond that without crashing; resize later in a
   couple of clicks if real usage tells you otherwise.
4. Choose a region close to your users (e.g. Frankfurt/Amsterdam for
   Central Asia latency)
5. Authentication: **SSH key** (recommended) or password
6. Create the droplet, note its public IP

## 2. Point DNS at it

In your domain's DNS provider, create an **A record**:

```
admin.yourdomain.uz  ->  <droplet_public_ip>
```

(Replace `yourdomain.uz` with your real domain throughout this doc and in
`.env`'s `ADMIN_DOMAIN` / `WEBHOOK_BASE_URL`. Caddy needs this DNS record
live and propagated *before* it first starts, or it will fail to issue a
Let's Encrypt certificate — wait a few minutes after creating the record and
verify with `dig admin.yourdomain.uz` before proceeding to step 6.)

## 3. SSH in and do basic hardening

```bash
ssh root@<droplet_public_ip>

# create a non-root user (optional but recommended)
adduser deploy
usermod -aG sudo deploy

# firewall: only allow SSH, HTTP, HTTPS
ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

## 4. Install Docker + Compose plugin

```bash
curl -fsSL https://get.docker.com | sh
usermod -aG docker $USER   # run as root, or `sudo usermod -aG docker deploy`
# log out and back in for group membership to apply, or:
newgrp docker

docker --version
docker compose version
```

## 5. Clone the repo

```bash
sudo mkdir -p /opt/ielts-8-plus-bot
sudo chown $USER:$USER /opt/ielts-8-plus-bot
cd /opt/ielts-8-plus-bot

git clone https://github.com/baxti08/ielts-8-plus-bot.git .
```

## 6. Configure environment variables

```bash
cp .env.example .env
nano .env
```

Fill in, at minimum:

| Variable | Value |
|---|---|
| `BOT_TOKEN` | from [@BotFather](https://t.me/BotFather) |
| `WEBHOOK_BASE_URL` | `https://admin.yourdomain.uz` |
| `ADMIN_DOMAIN` | `admin.yourdomain.uz` |
| `WEBHOOK_SECRET` | random string — generate with `openssl rand -hex 24` |
| `ADMIN_SECRET_KEY` | random string — generate with `openssl rand -hex 32` |
| `POSTGRES_PASSWORD` | a strong password |
| `DATABASE_URL` | must contain the **same** password as `POSTGRES_PASSWORD` above (these two are not auto-synced — edit both) |
| `ADMIN_USERNAME` / `ADMIN_PASSWORD` | already pre-filled as `admin` / `baxti777` — change if you want |

The 5 content-channel IDs and admin panel path are already pre-filled with
the values you gave during spec — double check them against your actual
channels before going live:

```
CHANNEL_READING_ID=-1004415568526
CHANNEL_MULTILEVEL_ID=-1004356238968
CHANNEL_LISTENING_ID=-1004369157403
CHANNEL_SPEAKING_ID=-1004425106652
CHANNEL_WRITING_ID=-1003695165186
```

**Before starting the stack**, make sure the bot account (once created via
BotFather) has been added as **admin** in:
- all 5 content channels above (needed for `copyMessage`)
- all 4 required gate channels (`@MultiLevelRecord`, `@RS_IELTS`,
  `@alisher_abduvohobov`, `@xojaevs`) — needed both for `getChatMember` checks
  and for `chat_member` leave/rejoin events

## 7. Bring the stack up

```bash
docker compose build
docker compose up -d
```

This runs, in order: `postgres` (waits for healthy) → `migrate` (runs
`alembic upgrade head` once, then exits — this is expected, it's not
supposed to stay running) → `bot` + `admin` (start once migration succeeds)
→ `caddy` (issues the TLS cert and starts proxying).

Check everything is up:

```bash
docker compose ps
docker compose logs -f caddy   # watch for successful cert issuance
docker compose logs -f bot
docker compose logs -f admin
```

## 8. Verify the webhook

```bash
curl -s "https://api.telegram.org/bot<BOT_TOKEN>/getWebhookInfo" | python3 -m json.tool
```

You should see `"url": "https://admin.yourdomain.uz/webhook/tg/<WEBHOOK_SECRET>"`
and `"pending_update_count": 0` (or draining down). If `last_error_message`
is non-empty, check `docker compose logs bot` and re-verify DNS/TLS.

Then message your bot `/start` on Telegram and confirm it replies.

## 9. Log into the admin panel

Visit `https://admin.yourdomain.uz` → log in with `ADMIN_USERNAME` /
`ADMIN_PASSWORD` from `.env`. Go to **Content** and add your first day of
lessons for each section (message IDs from the private source channels).

## 10. Install the systemd watchdog (fallback if the droplet reboots)

Docker Compose's `restart: unless-stopped` already brings containers back up
after a reboot **once the Docker daemon itself starts**, but this systemd
unit adds a belt-and-suspenders `docker compose up -d` on boot in case a
container is stuck or was manually stopped:

```bash
sudo cp systemd/ielts-8-plus-bot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ielts-8-plus-bot.service
sudo systemctl start ielts-8-plus-bot.service
sudo systemctl status ielts-8-plus-bot.service
```

## 11. Day-to-day operations

```bash
# view logs
docker compose logs -f bot
docker compose logs -f admin

# deploy a code update
git pull
docker compose build
docker compose up -d   # migrate re-runs automatically, is a no-op if nothing changed

# run a one-off migration manually (rarely needed, compose does this automatically)
docker compose run --rm migrate alembic upgrade head

# create a new Alembic migration after changing common/db/models.py
docker compose run --rm migrate alembic revision --autogenerate -m "describe the change"

# restart just the bot
docker compose restart bot

# full teardown (keeps the Postgres volume)
docker compose down

# full teardown INCLUDING the database (destructive)
docker compose down -v
```

## 12. Backups

**This is now automatic — the bot sends a full database backup to your
Telegram DM every morning at 08:00 Asia/Tashkent**, no cron setup needed
(see `bot/services/backup.py`). The admin account receiving it is set by
`BACKUP_ADMIN_CHAT_ID` in `.env` — **that account must have pressed /start
on the bot at least once**, or Telegram will refuse to deliver the file
(bots can only message users who've initiated contact). A rolling 7-day
copy is also kept on the droplet itself (`backups` Docker volume) as a fast
local restore option, but the Telegram copy is the real off-site safety net
— it's what actually protects you if the droplet itself is lost or deleted.

To restore from a sent backup file: download it from Telegram, then:

```bash
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean < ielts_bot_YYYY-MM-DD.dump
```

If you additionally want an off-droplet copy somewhere other than Telegram
(S3-compatible Spaces, etc.), you can still add the cron-based approach:

```bash
# /opt/ielts-8-plus-bot/backup.sh
#!/bin/bash
cd /opt/ielts-8-plus-bot
docker compose exec -T postgres pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB" | gzip > "/opt/backups/ielts_bot_$(date +%F).sql.gz"
```

```bash
mkdir -p /opt/backups
chmod +x backup.sh
crontab -e
# add: 0 3 * * * /opt/ielts-8-plus-bot/backup.sh
```

## 13. Handling high-burst load (many /start at once)

Several things are already tuned for this:

- **Postgres connection pool**: `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` in `.env`
  (defaults 20/40 per service — bot + admin together can open up to ~120
  connections). Postgres itself is raised to `max_connections=300` in
  `docker-compose.yml` to comfortably hold that.
- **Webhook concurrency**: the bot registers its webhook with
  `max_connections=100` (Telegram's maximum), so Telegram can push updates
  to us with more parallelism during a spike instead of throttling itself.
- **uvloop**: the bot uses uvloop instead of the default asyncio event loop
  when available, for meaningfully faster throughput under load.
- **Graceful degradation, not crashes**: aiogram isolates each update's
  handler — one failing update (e.g. a DB timeout under extreme load) is
  logged and skipped, it does not take down the whole bot process. If the
  connection pool is briefly exhausted, new requests wait up to
  `DB_POOL_TIMEOUT` seconds rather than erroring immediately.

**Honest ceiling**: this is a single droplet running a single bot process.
The tuning above lets it absorb large simultaneous bursts (hundreds to a
few thousand concurrent requests) far better than the untuned defaults —
but it is not infinite horizontal scaling. If you expect sustained,
very large simultaneous spikes well beyond that, the next step up is
running multiple bot instances behind a message queue (e.g. Redis) instead
of one process handling every webhook call directly — that's a real
architecture change, not a config tweak, and isn't built here. Right-size
the droplet to your actual expected user base (see the note in step 1) and
watch `docker stats` under real traffic before assuming you need it.

## 14. Broadcasting to everyone without affecting the live bot

A broadcast to all 50k users runs entirely inside the **admin** service, in
its own process with its own Bot instance and its own DB connection pool —
completely separate from the **bot** service that handles real-time
`/start` traffic. A 30-minute broadcast run cannot block, slow down, or
crash the bot's ability to respond to users at the same time; they don't
share a process, an event loop, or a connection pool.

Within the broadcast itself:
- Paced at `BROADCAST_RATE_PER_SEC` (default 28 msg/sec, just under
  Telegram's ~30/sec ceiling), with dynamic pacing so it never sends slower
  than necessary — at 50k users this completes in roughly 30 minutes.
- Telegram flood-control responses (`TelegramRetryAfter`) are handled by
  sleeping exactly as long as Telegram asks, then continuing — graceful
  backoff, not a crash, if you're ever pushed toward the limit.
- Each user send is isolated; one failure (blocked bot, deleted account,
  etc.) never aborts the batch or the run.
- The whole run is wrapped in error handling — an unexpected failure marks
  the run "failed" in the admin dashboard and stops cleanly, it does not
  propagate into the admin process itself.
- The admin panel blocks starting a second broadcast while one is already
  running, so you can't accidentally double the send rate against
  Telegram's per-bot limit.

Tune `BROADCAST_RATE_PER_SEC` in `.env` if you want to push closer to (or
pull back from) Telegram's ceiling.

### Triggering a broadcast from inside Telegram (no admin panel needed)

Any account listed in `ADMIN_IDS` (`.env`, comma-separated, defaults to
`8233724149`) can message the bot directly:

- `/broadcast` — pick a segment via buttons, then send the message text as
  your next message, review, confirm
- `/broadcast_status` — check the most recent run's progress

This path runs the broadcast as a background task **inside the bot
process** (not the separate admin process the web panel uses) — safe
because the send loop is pure async I/O with existing error isolation
(see the docstring in `bot/handlers/admin_broadcast.py`), but worth
knowing it's a different isolation story than the web-panel path above.
Both paths share the same "one broadcast at a time" guard, so triggering
from the bot and from the web panel can't race each other.

