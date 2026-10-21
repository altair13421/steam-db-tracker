# Steam Tracker (Django + Docker)

A Django web app + long-running scheduler that tracks Steam apps — **price,
discounts, patch notes / app updates, news/announcements** — using only
**public Steam storefront APIs (no API key)**. Ships with a Dockerfile +
docker-compose so it **auto-restarts on crash or reboot**.

- 🐍 Pure Python / Django 4.2+ (LTS) project, no Node / no npm.
- 🌐 Web UI (Bootstrap 5) for: dashboard, app detail with chart, changelog
  with filters, news feed, weekly digest.
- 🔐 Django admin at `/admin/` for power-user management.
- 🔓 **No Steam API key required** — uses public storefront endpoints.
- 🐳 Docker: two services (`web` + `scheduler`) sharing a SQLite volume;
  `restart: unless-stopped` brings both back on host reboot.
- 🧱 SQLite by default — Postgres-ready via `DATABASE_URL=postgres://...`.
- 📈 Per-app price-history PNGs rendered with matplotlib.
- 🧾 Filterable changelog of every detected change.

---

## 1. Quick start — Docker (recommended)

```bash
# 1. Configure env (optional — defaults are sane).
cp .env.example .env
# Edit .env to set DJANGO_SECRET_KEY for production.
# Set DOCKER_UID and DOCKER_GID in .env to the output of `id -u` and `id -g`
# so the containers can write to the bind-mounted data/, media/, and logs/.

# 2. Build + start both services.
docker compose up -d --build

# 3. Wait for the scheduler to seed + migrate, then open the UI:
open http://localhost:9000/
```

The compose file:
1. Builds the image once (cached on subsequent runs).
2. Starts `scheduler` (runs `migrate`, `seed_apps`, then `manage.py schedule`).
3. Starts `web` (gunicorn on :8000) once `scheduler` is healthy.
4. Both services share `./data`, `./media`, `./logs`, `./config` host volumes.

Logs:
```bash
docker compose logs -f scheduler        # tracking cycles
docker compose logs -f web              # HTTP requests
```

Stop / restart:
```bash
docker compose stop
docker compose start
docker compose restart scheduler       # just kick the scheduler
```

---

## 2. Quick start — local Python

```bash
# 1. Create + activate a venv.
python -m venv .venv && source .venv/bin/activate

# 2. Install deps.
pip install -r requirements.txt

# 3. Migrate + seed the watchlist.
python manage.py migrate
python manage.py seed_apps

# 4. Run one tracking cycle so the dashboard has data.
python manage.py track

# 5. Start the dev server in one terminal…
python manage.py runserver

# 6. …and the scheduler in another.
python manage.py schedule
```

Visit <http://localhost:8000/>.

---

## 3. Management commands

All commands work the same in Docker:

```bash
docker compose exec web python manage.py <cmd>
# or one-shot:
docker compose run --rm web python manage.py <cmd>
```

| Command | What it does |
|---------|-------------|
| `python manage.py migrate` | Apply DB schema migrations. |
| `python manage.py seed_apps` | Populate the watchlist from `config/apps.yaml` (or defaults). |
| `python manage.py track` | Run one tracking cycle for **every** tracked app (snapshot + news + diff). |
| `python manage.py track --appid 730` | Track just one app. |
| `python manage.py schedule` | Long-running scheduler (uses `SCHEDULE_INTERVAL`, default 12h). |
| `python manage.py schedule --once` | Run one cycle then exit (cron mode). |
| `python manage.py chart` | Render a price PNG for every tracked app (needs ≥2 snapshots). |
| `python manage.py chart 730` | Render for a single app. |
| `python manage.py digest` | Build + print a weekly Markdown digest. |
| `python manage.py digest --days 30 --write` | Save a 30-day digest to `media/digest_<date>.md`. |
| `python manage.py createsuperuser` | Create an admin login for `/admin/`. |
| `python manage.py collectstatic` | Bundle static files (only needed for production nginx). |

---

## 4. Web UI pages

| URL | Page |
|-----|------|
| `/` | Dashboard — list of tracked apps with current price + discount + last-snapshot time, plus recent changes. Add new apps here. |
| `/track-now` | POST — triggers one tracking cycle for every app. |
| `/track/<appid>` | POST — triggers tracking for one app. |
| `/remove/<appid>` | POST — removes the app from the watchlist (history kept). |
| `/app/<appid>` | App detail — price chart + recent snapshots + recent changes + latest news. |
| `/changelog` | Filterable changelog (by app, change type, days). |
| `/news` | News feed across all apps, filterable by app + "only updates". |
| `/digest` | Weekly (or N-day) digest with per-app stats. |
| `/charts/<filename>` | Serves the PNGs (in production prefer nginx). |
| `/admin/` | Django admin (login required). |

---

## 5. How tracking works

Each `track` cycle per app:

1. **`fetch_app_snapshot`** hits
   `https://store.steampowered.com/api/appdetails?appids=<ID>&cc=<CC>&l=<LANG>`
   for: name, type, free/paid, currency, initial/final price, discount %,
   release date, **last_update**, developers, publishers, short description.

2. **`fetch_app_news`** hits
   `https://api.steampowered.com/ISteamNews/GetNewsForApp/v2?appid=<ID>`
   for the most recent 20 community announcements.

3. **`diff_and_store`** compares the new snapshot against the previous one
   and creates `Change` rows for:
   - `price_drop` / `price_hike` — final price moved
   - `new_discount` / `discount_end` — discount % changed
   - `app_update` — Steam's `last_update` timestamp bumped
   - `added` — first-ever snapshot for this app

4. **`record_new_news`** inserts news posts (deduplicated by Steam's `gid`).
   New posts become either `app_update` (if their feed signals a
   patch / hotfix / release note) or `new_news` change events.

All detected changes show up on the dashboard, changelog page, app-detail
page, and digest page. The scheduler logs them to `logs/steam_tracker.log`
and the SQLite DB keeps every row forever (until you `TrackedApp.delete()`).

---

## 6. Project layout

```
steam-tracker-django/
├── manage.py
├── requirements.txt
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
├── config/
│   └── apps.yaml            # seed watchlist
├── data/                    # SQLite DB lives here (mounted volume)
│   └── steam.sqlite3
├── logs/
│   └── steam_tracker.log
├── media/
│   ├── charts/              # price_*.png, discount_*.png
│   └── digest_*.md
├── steamtracker/            # Django project package
│   ├── settings.py
│   ├── urls.py
│   ├── wsgi.py
│   └── asgi.py
└── tracker/                 # Django app
    ├── models.py            # TrackedApp, AppSnapshot, NewsPost, Change
    ├── admin.py
    ├── views.py
    ├── urls.py
    ├── forms.py
    ├── services/
    │   ├── steam_api.py     # public Steam storefront client (no key)
    │   ├── tracker.py       # track_one, track_all, diff_and_store
    │   ├── charts.py        # matplotlib PNGs
    │   └── digest.py        # digest report builder
    ├── management/commands/
    │   ├── track.py
    │   ├── schedule.py
    │   ├── chart.py
    │   ├── digest.py
    │   └── seed_apps.py
    ├── templates/tracker/
    │   ├── base.html
    │   ├── dashboard.html
    │   ├── app_detail.html
    │   ├── changelog.html
    │   ├── news.html
    │   └── digest.html
    └── static/tracker/
        └── style.css
```

---

## 7. Configuration

All settings live in `.env` (or environment variables on Docker):

| Variable                  | Default                                | Description |
|---------------------------|----------------------------------------|-------------|
| `DJANGO_SECRET_KEY`       | (dev-only string)                      | **SET THIS** in production. |
| `DJANGO_DEBUG`            | `False`                                | Set `True` for `runserver` dev work. |
| `DJANGO_ALLOWED_HOSTS`   | `localhost,127.0.0.1`                  | Comma list — add your domain in prod. |
| `DATABASE_URL`            | (empty → SQLite)                       | `postgres://user:pass@host:5432/db` for Postgres. |
| `STEAM_CC`                | `us`                                   | Steam currency code. |
| `STEAM_LANG`             | `english`                              | Steam language code. |
| `STEAM_THROTTLE_SECONDS` | `4`                                    | Min seconds between Steam requests. |
| `SCHEDULE_INTERVAL`      | `12 hours`                            | Scheduler polling interval. |
| `MEDIA_ROOT`             | `/app/media`                          | Where chart PNGs + digests live. |

---

## 8. Production notes

- **Static files**: in production run `python manage.py collectstatic` once
  and serve `staticfiles/` via nginx (or your reverse proxy).
- **HTTPS**: put Caddy / Traefik / nginx in front of gunicorn on :8000.
- **Postgres**: switch `DATABASE_URL=postgres://...` and you're done — the
  ORM code is identical.
- **Scale**: the scheduler is single-process by design (Steam throttles
  aggressively). For >100 apps, consider sharding across multiple scheduler
  instances with disjoint app sets.

---

## 9. Why no Steam API key?

The Steam Web API (the `*.steamapis.com` family) has been gating keys more
aggressively since 2024. The public storefront endpoints used here are
open, undocumented, and cover 95% of tracking needs.

Trade-offs:
- ❌ No concurrent player count (lives behind the gated API).
- ❌ No review-summary score (also gated).
- ❌ No depot/build history (also gated).

If you ever need those: drop a `key` into `tracker/services/steam_api.py`
and add new fetcher functions; the rest of the pipeline (models, views,
templates, charts, digest) doesn't care where the data came from.

---

## 10. License

MIT — do what you want with this; not affiliated with Valve / Steam.
