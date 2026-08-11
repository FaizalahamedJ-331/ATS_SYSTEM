# Deploying TalentPulse ATS on PythonAnywhere — 100% free

**Why this platform:** free forever with **no credit card**, managed (no server
maintenance), free `https://yourusername.pythonanywhere.com` subdomain with
HTTPS, and your web app stays reachable (it may cold-start after a long idle —
see "Caveats" below).

**Free-tier limits (Jan 2026 overhaul):**
- 1 web app · 2 Bash consoles · 512 MB disk · 100 CPU-seconds/day
- New free accounts: **SQLite only** (no MySQL) — this project defaults to
  SQLite, so **no database setup is needed**.
- Free consoles have whitelisted outbound internet → the optional **LLM deep
  analysis may not work** from free tier; rule-based screening works fully.

---

## Step 1 — Create the account (no card)

1. Go to **https://www.pythonanywhere.com/registration/register/start/**
2. Enter username, email, password. **No payment details.**
3. Confirm your email.

You now have `https://YOURUSERNAME.pythonanywhere.com`.

## Step 2 — Push the code to GitHub

PythonAnywhere pulls your code from a Git repo.

```bash
# From your Windows machine, in the project folder:
git init
git add .
git commit -m "TalentPulse ATS"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ats-system.git
git push -u origin main
```

> `.gitignore` already excludes `venv/`, `db.sqlite3`, `.env`, and `media/`.

## Step 3 — Clone the code & create the virtualenv

Open the PythonAnywhere **Bash console** (Dashboard → Consoles → Bash) and run:

```bash
git clone https://github.com/YOUR_USERNAME/ats-system.git ~/ats
cd ~/ats

python3.12 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements-pa.txt     # slim set: fits 512 MB disk
```

## Step 4 — Create the `.env` file

```bash
nano .env
```

```ini
DJANGO_SECRET_KEY=<generate one with: python -c "import secrets; print(secrets.token_urlsafe(50))">
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=YOURUSERNAME.pythonanywhere.com
CSRF_TRUSTED_ORIGINS=https://YOURUSERNAME.pythonanywhere.com
DJANGO_TIME_ZONE=UTC
SESSION_COOKIE_SECURE=True
CSRF_COOKIE_SECURE=True

# Optional (may be blocked by free-tier outbound whitelist):
LLM_API_KEY=
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL=gpt-4o-mini
```

## Step 5 — Prepare the database & static files

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py createsuperuser          # or: python manage.py seed_demo
```

## Step 6 — Create the web app

1. Dashboard → **Web** tab → **Add a new web app**
2. Choose **Manual configuration** → **Python 3.12** → Next.
3. In the **Code** section set:
   - **Source code:** `/home/YOURUSERNAME/ats`
   - **Working directory:** `/home/YOURUSERNAME/ats`
   - **Virtualenv:** `/home/YOURUSERNAME/ats/venv`

## Step 7 — Replace the WSGI file

Click the **WSGI configuration file** link (e.g.
`/var/www/YOURUSERNAME_pythonanywhere_com_wsgi.py`) and replace its contents
with:

```python
import os
import sys
from pathlib import Path

PROJECT = Path("/home/YOURUSERNAME/ats")
sys.path.insert(0, str(PROJECT))

from dotenv import load_dotenv
load_dotenv(PROJECT / ".env")

os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

## Step 8 — Media files mapping (resume uploads)

In the same **Web** tab, find the **Static files** section and add:

| URL | Directory |
| --- | --- |
| `/media/` | `/home/YOURUSERNAME/ats/media` |

(Static files at `/static/` are already served by WhiteNoise — no mapping needed.)

## Step 9 — Reload & verify

1. Click **Reload** at the top of the Web tab.
2. Open **https://YOURUSERNAME.pythonanywhere.com** → sign in with your
   superuser → try the Dashboard, Pipeline, and a resume upload.

---

## 🔁 Updating the app later

```bash
# In a Bash console:
cd ~/ats && git pull
source venv/bin/activate
pip install -r requirements-pa.txt
python manage.py migrate
python manage.py collectstatic --noinput
# Then click "Reload" on the Web tab.
```

---

## ⚠️ Caveats to know

- **Idle cold-start:** free web apps may shut down after inactivity and wake
  on the next visit (first load takes a few extra seconds). No card = this is
  the standard tradeoff.
- **Account expiry:** free accounts expire after ~1 month of inactivity — just
  log in every few weeks.
- **CPU quota:** 100 CPU-seconds/day. Heavy use (mass screening runs) may get
  throttled until midnight UTC.
- **Outbound whitelist:** the AI deep-analysis feature calls an external LLM
  API, which the free tier may block. Everything rule-based works regardless.
- **Support:** free accounts use the community forum (no email tickets).
- **Disk:** 512 MB total. The venv takes ~250–350 MB — that's why we skip
  `psycopg` and `gunicorn` on this platform. If you run low, delete the
  `staticfiles/` folder and re-run `collectstatic`.
