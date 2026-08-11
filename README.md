# TalentPulse ATS — Advanced Applicant Screening System

[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

An enterprise-grade applicant tracking system built with **Python + Django**,
featuring a **hybrid AI screening engine**: deterministic rule-based scoring
that always works offline, plus optional LLM-powered deep analysis when an API
key is configured.

## ✨ Features

| Area | Capabilities |
| --- | --- |
| **Resume parsing** | Upload PDF / DOCX / TXT — auto-extracts contact info, skills (60+ category taxonomy), education and years of experience |
| **Hybrid AI screening** | Weighted ATS score (skills 45% · keywords 20% · experience 20% · education 15%), verdicts, strengths/concerns, human-sounding natural-language insight + next-step recommendation, rule-based interview question suggestions, multi-dimension fit radar. Optional LLM deep-analysis pass adjusts scores with narrative feedback |
| **Pipeline board** | Drag-and-drop kanban: New → Screening → Interview → Offer → Hired / Rejected (persisted via JSON API, every move logged) |
| **Job management** | Requisitions with required/nice-to-have skills, salary bands, seniority levels; one-click screening of all applicants, bulk **"Advance top matches"**, per-job **CSV export** with scores |
| **Candidate profiles** | Parsed resume view, per-job screening breakdowns, interview history, apply-to-job flow, per-application **activity timeline** + recruiter note composer |
| **Activity feed** | Every stage change, screening, interview, note and application logged with timestamps — surfaced as a live "Recent activity" feed on the dashboard |
| **Interview scheduling** | Schedule, complete with star-rating + feedback (auto-promotes on 4+), cancel |
| **Analytics dashboard** | Time-aware greeting, AI hiring insights panel, 5 live charts: applications over time, sources, per-job volume, ATS score distribution, pipeline funnel |
| **Command palette** | Press `Ctrl+K` / `Cmd+K` (or the Search button) for instant global search across candidates, jobs and pages — keyboard-navigable, debounced, with quick actions |
| **Pinned candidates** | Star any candidate to float them to the top of the list; one-click `?pinned=1` filter, pin/unpin from list or profile |
| **Extras** | Light/dark theme, toasts, live table search, mobile-responsive sidebar, candidate CSV export (formula-injection safe), Django admin |

## 🚀 Quick start

```bash
# 1. Create and activate a virtual environment
python -m venv venv
# Windows:  venv\Scripts\activate
# macOS/Linux: source venv/bin/activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Prepare the database + demo data (9 jobs, 28 candidates, screenings, interviews)
python manage.py migrate
python manage.py seed_demo

# 4. Run the server
python manage.py runserver
```

Open **http://127.0.0.1:8000** and sign in with the seeded superuser:

```
username: admin
password: admin12345
```

> `python manage.py seed_demo --flush` wipes and re-seeds all demo data.

## 🤖 Enabling AI deep analysis (optional)

The rule-based engine needs **no API key** and powers everything by default.
To add LLM-powered screening, create a `.env` file (see `.env.example`):

```
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.openai.com/v1   # any OpenAI-compatible endpoint
LLM_MODEL=gpt-4o-mini
```

Then use **"AI deep analysis"** on any screening report, or tick "Run
screening" on a job — results get a narrative summary, an LLM verdict and a
±15 point score adjustment. Without a key the UI simply shows a friendly
notice.

## 🧱 Architecture

```
config/        Django project (settings, URLs, WSGI/ASGI)
core/          Base models, skill taxonomy, resume parsers, LLM client, seed command
jobs/          Job requisitions + forms/views
candidates/    Candidate, Resume, Application models + pipeline board
screening/     Hybrid scoring engine (screening/engine.py) + report views
interviews/    Interview scheduling & feedback
dashboard/     Analytics views
templates/     Server-rendered UI (sidebar layout, design system)
static/        styles.css + app.js (theme, kanban drag-drop, charts)
```

## 🧪 Screening engine internals

`screen_job()` / `screen_application()`:

1. **Rule pass** — required skills are matched against the resume (alias-aware,
   token-prefix tolerant), keywords are extracted from the job description and
   compared against the resume corpus, experience is benchmarked against the
   role's seniority band, and education signals are checked. Produces a 0–100
   score, component scores, matched/missing skills and keywords, and a verdict.
2. **Optional LLM pass** — when configured, the resume + job are sent to the
   chat-completions endpoint which returns structured JSON (verdict,
   score delta, strengths, concerns, summary). The result is merged into the
   stored screening result and flagged `AI-enhanced`.

## ⚡ Performance

- **Query efficiency** — dashboard aggregates are single `GROUP BY` queries (14-day trend, pipeline funnel, verdict counts); activity feed and lists use `select_related` / `prefetch_related` with no N+1.
- **Scoped chart library** — Chart.js is loaded only on the pages that render charts (dashboard, screening report), deferred so it never blocks first paint.
- **Non-blocking fonts** — Google Fonts loads via `preload` + `onload`, so text paints immediately.
- **Instant navigation** — internal links are prefetched on hover / touch (respects `saveData` / 2G connections), and same-origin clicks run through the View Transitions API with a top progress bar for a smooth cross-fade.
- **Page-load skeletons** — every page shows an animated shimmer skeleton (cards + table rows) for a beat while loading, then fades into the real content with zero layout shift; a failsafe guarantees the content always appears even if a script fails.
- **Indexes** — `Application.status`, `ScreeningResult.ats_score` and the `-created_at` ordering columns are indexed for the pipeline board, feeds and top-matches queries.

## 🗄️ Production notes

- **PostgreSQL**: set `DB_ENGINE=postgres` plus `DB_NAME`, `DB_USER`, `DB_PASSWORD`,
  `DB_HOST`, `DB_PORT` in `.env` (see `.env.example`), then run
  `python manage.py migrate`. SQLite remains the zero-config dev default.
- **Static files**: WhiteNoise serves collected static files — run
  `python manage.py collectstatic --noinput` during deploy.
- **Server**: Gunicorn is included — `gunicorn config.wsgi:application`
  (a ready-made `Procfile` is provided for PaaS platforms).
- **HTTPS hardening**: set `DJANGO_DEBUG=False`, a strong `DJANGO_SECRET_KEY`,
  `DJANGO_ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, then enable
  `SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`,
  `SECURE_HSTS_SECONDS` in `.env`.
- **Uploads**: resume files are stored under `media/`. On a VPS, point Nginx
  at `MEDIA_ROOT`. On PaaS, use a persistent disk mount or object storage.

## 📄 License

Released under the [MIT License](LICENSE).
