# RAILWAY.md — running the whole stack on Railway (staging / pre-launch)

This is a lighter-weight way to get bot + admin + Postgres actually running
and reachable on the internet, before committing to the DigitalOcean droplet
in [DEPLOY.md](./DEPLOY.md). Railway is a different shape of platform than
the droplet setup — no Caddy, no `docker-compose.yml` orchestration, no
systemd. Each piece becomes its own Railway **service**, and Railway itself
handles HTTPS and process supervision.

**Recommended for Railway specifically: run the bot in long-polling mode**
(`USE_WEBHOOK=false`), not webhook mode. The `docker-compose.yml` setup put
the bot's webhook under the *admin panel's* domain via Caddy — Railway gives
every service its own separate domain, so that combined routing doesn't
carry over cleanly. Long polling sidesteps needing a public URL/domain for
the bot service at all, and is the simplest path for a staging environment.
(DEPLOY.md's droplet setup keeps webhook mode — this doesn't change that.)

## 1. Push your latest local changes to GitHub first

Railway deploys from your GitHub repo, so anything only sitting on your Mac
needs to be pushed:

```bash
cd ~/Downloads/ielts-8-plus-bot
git add -A
git commit -m "Latest changes"
git push
```

## 2. Create the Railway project

1. Go to [railway.app](https://railway.app) → sign in with GitHub
2. **New Project** → **Deploy from GitHub repo** → pick `baxti08/ielts-8-plus-bot`
3. Railway will try to auto-detect a service from the repo root — **delete
   that auto-created service** once the project exists (click it → Settings
   → Danger Zone → Remove Service). We'll add the 3 services deliberately
   below instead, since this repo has multiple Dockerfiles, not one.

## 3. Add a Postgres database

Inside the project: **+ New** → **Database** → **Add PostgreSQL**.

Railway provisions it and exposes connection variables automatically
(`PGHOST`, `PGPORT`, `PGUSER`, `PGPASSWORD`, `PGDATABASE`) that other
services in the same project can reference.

## 4. Add the `admin` service

**+ New** → **GitHub Repo** → `baxti08/ielts-8-plus-bot` again (Railway lets
you deploy the same repo as multiple independent services).

In this service's **Settings**:
- **Dockerfile Path**: `Dockerfile.admin`
- **Networking → Generate Domain**: click this — Railway gives you a public
  URL like `ielts-8-plus-bot-admin-production.up.railway.app`. Set the port
  to `8000` (matching the `EXPOSE 8000` / uvicorn `--port 8000` in the
  Dockerfile).

In this service's **Variables** tab, add everything from `.env.example`,
with these Railway-specific changes:

```
DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
ADMIN_DOMAIN=<the domain Railway just generated for this service>
WEBHOOK_BASE_URL=<irrelevant here since the bot runs polling — any value is fine, e.g. https://unused.example.com>
```

The `${{Postgres.PGUSER}}` syntax is Railway's cross-service variable
reference — type it literally, Railway resolves it at deploy time. Fill in
the rest (`BOT_TOKEN`, the 5 content channel IDs, `ADMIN_USERNAME`,
`ADMIN_PASSWORD`, `ADMIN_SECRET_KEY`, etc.) the same as you did in your local
`.env`.

## 5. Add the `bot` service

**+ New** → **GitHub Repo** → same repo again.

Settings:
- **Dockerfile Path**: `Dockerfile.bot`
- **Networking**: leave it alone — don't generate a domain. Long-polling
  doesn't need one; the container just needs to keep running, which Railway
  does regardless of whether a domain is attached.

Variables — same list as the admin service (**Variables** tab has a
"copy from another service" option, or just paste the same block), with:

```
USE_WEBHOOK=false
```

## 6. Run the migration once

Install the Railway CLI locally if you don't have it:

```bash
brew install railway
railway login
```

Link your local repo folder to the project, then run the migration against
the admin service's environment (it has the same `DATABASE_URL`):

```bash
cd ~/Downloads/ielts-8-plus-bot
railway link
railway run --service admin alembic upgrade head
```

## 7. Verify

- **admin**: open the domain from step 4 in your browser, log in
- **bot**: check the `bot` service's **Deploy Logs** in the Railway
  dashboard for `Run polling for bot @IELTS_LEVEL_BOT` — same as what you've
  been seeing locally
- Message the bot on Telegram, confirm `/start` responds

## Moving from Railway to the real DigitalOcean launch

Railway here is just for testing reachability/behavior with a real public
admin URL before the droplet. When you're ready for the actual production
launch, follow `DEPLOY.md` from step 1 — that's the durable, full-control
setup (webhook mode, your own domain, backups, systemd watchdog). Nothing
about the Railway setup needs to be preserved or migrated; they use
independent databases.
