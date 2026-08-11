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
| **Auth & RBAC** | Self-service signup (auto-login), two roles (Admin · Recruiter) enforced server-side with a 403 page, admin-only user management with promote/demote and enable/disable guards |
| **Strong passwords** | Enforced policy — 10+ chars, 3+ character types, no common/numeric-only passwords — with a live strength meter + rule checklist on every password field |
| **Account settings** | Logged-in users change their own password from the sidebar (Settings) — current-password check, strength meter, session-hash rotation |
| **Two-factor auth (TOTP)** | Optional authenticator-app 2FA (Google Authenticator / Authy / 1Password): QR setup with confirmation code, 2-step login, replay protection, brute-force throttling, password-confirmed disable, **one-time recovery codes**, **"remember this device" trust cookies** (skip the code on trusted browsers for 30 days, per-device revocable) |
| **Login alerts** | Opt-in email alert whenever a sign-in happens from a browser that isn't trusted — device, IP and time, with a change-password shortcut if it wasn't you |
| **Security log** | Per-user audit trail at `/settings/security/` — sign-ins (trusted vs new browser), 2FA enable/disable, trusted-device add/revoke, recovery-code issuance, password changes — newest first with IPs, capped per user |
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

Open **http://127.0.0.1:8000** — sign in with a seeded account, or **create
your own** via the “Create your account” link on the login page (you'll get
a verification email — in dev it prints to the terminal):

```
Admin     — username admin     · password admin12345
Recruiter — username recruiter · password recruiter12345
```

> `python manage.py seed_demo --flush` wipes and re-seeds all demo data.

## 🔐 Roles & access control

Two roles, enforced on both the UI and the server:

| Role | Capabilities |
| --- | --- |
| **Admin** (superuser) | Everything a Recruiter can do, **plus** the Users page — promote/demote roles, disable/enable accounts — and the Django admin console. |
| **Recruiter** (default for new signups) | Full hiring workflow: jobs, candidates, pipeline, screening, interviews. |

- New accounts **always** sign up as Recruiters — the Admin role is reserved
  (the signup form shows it as locked).
- Admins manage accounts at `/users/` with safety guards: you can't change
your own role, can't disable yourself, and the last Admin can never be demoted.
- Protected pages return a friendly **403** page for the wrong role; the
  sidebar shows the current user's role badge and only renders the Users
  navigation for admins.

## ✉️ Email verification

New signups get a **welcome email** with a signed verification link (expires
after 48h). The account can't sign in until the link is clicked — the login
page explains this and offers a one-click **resend** when needed.

- **Development**: no SMTP needed — the email (with its link) prints to your
  terminal via Django's console backend, and the "check your inbox" page
  tells you so.
- **Production**: set these in `.env`:
  ```
  EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
  EMAIL_HOST=smtp.yourprovider.com
  EMAIL_PORT=587
  EMAIL_HOST_USER=apikey
  EMAIL_HOST_PASSWORD=secret
  EMAIL_USE_TLS=true
  DEFAULT_FROM_EMAIL="TalentPulse <no-reply@yourdomain.com>"
  ```
- Tokens are signed with the project `SECRET_KEY` (no database storage) and
  verification state lives on each user's profile. The seeded `admin` and
  `recruiter` demo accounts are pre-verified so they always work.

**Stale-account reminders** — accounts still unverified after
`VERIFY_REMINDER_AFTER_HOURS` (default **24h**) get a nudge email, at most
once per `VERIFY_REMINDER_COOLDOWN_HOURS` (default **24h**) per account.
Run the management command from any scheduler (system cron, Heroku
Scheduler, GitHub Actions) — it's safe to run hourly:

```bash
python manage.py send_verification_reminders        # send the nudges
python manage.py send_verification_reminders --dry-run  # preview, send nothing
```

```cron
0 * * * *  cd /path/to/ats && venv/bin/python manage.py send_verification_reminders
```

## 🔑 Password reset

Forgot your password? From the login page, **"Forgot your password?"**
opens the reset flow (Django's battle-tested machinery, branded to match):

1. Enter your email → a reset link is emailed (same system as verification
   emails — console backend in dev, SMTP in production, absolute links via
   `SITE_URL`).
2. Click the link → choose a new password. The link is **single-use** and
   **expires after 3 days** (`PASSWORD_RESET_TIMEOUT`).
3. Sign in with the new password.

Security details:

- **Anti-enumeration** — the "check your inbox" page is identical whether
  or not the email has an account, so the endpoint can't be used to probe
  for signups.
- **Rate limited** — reset requests are limited per IP + address
  (`PASSWORD_RESET_RATE_LIMIT`, default 3 per 15 min) and confirm
  submissions per IP (`PASSWORD_RESET_CONFIRM_RATE_LIMIT`, default 10 per
  hour), reusing the same limiter as signup/resend.
- **No auto-login** — after resetting, users sign in normally, so the
  email-verification gate still applies to unverified accounts.

## 🔒 Strong password policy

Every password set through the UI (signup, password reset) is validated by
Django's validator stack plus a custom diversity rule:

- **Minimum length** — 10 characters by default (`PASSWORD_MIN_LENGTH`).
- **Character diversity** — must mix **3+ of 4** character types (lowercase,
  uppercase, numbers, symbols), so `aaaaaaaaaaaa` or `123456789012` can never
  pass by being long. (`core/validators.py`)
- **Not a common password** — Django's `CommonPasswordValidator` blocks the
  top 20,000 most-used passwords; numeric-only passwords are rejected too.
- **Not too similar to your identity** — `UserAttributeSimilarityValidator`
  rejects passwords matching your name/email/username.

**Live strength meter** — the signup and reset forms show a 5-segment meter
that fills and re-colors in real time (Weak → Fair → Strong → Excellent),
plus a rule checklist that ticks off each requirement as you type and a
Show/Hide toggle. It mirrors the server-side policy, so what the meter says
is what the server enforces. (`static/js/password-meter.js`)

## ⚙️ Account settings

Signed-in users can change their own password from the **Settings** (gear icon)
in the sidebar footer → `/settings/password/`:

- Requires the **current password**, then the same strong-password policy as
  signup (validators enforced server-side) with the **live strength meter**
  on the new-password field.
- On success Django rotates the session auth hash — the current session
  stays signed in, every other session is invalidated — and a toast
  confirms the change.

## 🔐 Two-factor authentication (TOTP)

Any user can enable **authenticator-app 2FA** from Settings (shield icon in the
sidebar footer, or the 2FA card on the password page):

1. **Setup** — the page shows a scannable **QR code** (generated in-app with
   the pure-Python `segno` library — no image dependencies) plus the manual
   base32 secret for typing into your app.
2. **Confirm** — enter the current 6-digit code from the app; the feature is
   only enabled once a valid code proves you actually scanned it. At that
   point a batch of **8 one-time recovery codes** is issued (shown exactly
   once, with copy/download buttons) — your backup way in if you ever lose
   the app.
3. **Sign-in** — password first, then the code: the login flow verifies the
   password but doesn't sign you in; a branded challenge page (`/2fa/challenge/`)
   asks for the code, and only a correct code completes the login. Tick
   **"Trust this browser for 30 days"** while entering the code and that
   browser will skip the challenge on future sign-ins (the password is
   still always required).

Security details:

- **Replay-proof** — a code can only be used once within its 30-second step;
  the same code can't be replayed even by the real user.
- **Brute-force throttled** — wrong codes are rate-limited per IP
  (`TOTP_CHALLENGE_RATE_LIMIT`, default 5 per 15 min) on top of the 6-digit
  keyspace.
- **Pending-login only** — the challenge page requires a password-verified
  session; a stale or absent one redirects to login.
- **Disable requires your password** — a stolen session can't silently turn
  security off.
- Codes are verified with a ±1-step clock-drift window, and the secret is
  stored base32 on the user's profile.

**Trusted devices** — "remember this browser" for `TOTP_TRUST_DAYS` (default
**30 days**):

- The trust cookie is **HttpOnly**, `SameSite=Lax`, Secure in production,
  and contains a random 256-bit token — only its **SHA-256 digest** is
  stored (in the `TrustedDevice` table), so a database leak never yields a
  usable cookie.
- Each device is **bound to one user**, so a cookie can't skip 2FA for a
  different account, and it **expires automatically** (`expires_at`).
- Manage them on the 2FA settings page: see each device (browser, IP,
  trusted/expiry dates), **revoke a single device** or **"Forget all
  devices"** to require the code everywhere again. Disabling 2FA wipes
  every trusted device.

**Sign-in alerts** — an opt-in **"Notify me of new logins"** toggle on the
Settings page:

- When on, a successful sign-in from a browser **without a valid trust
  cookie** emails you with the device ("Chrome on Windows"), IP address
  and time — so a stolen password is spotted within minutes, not weeks.
- Covers every path: plain password logins *and* 2FA challenge completions
  (which by definition happen on untrusted browsers). Trusted-device logins
  are silent.
- The email includes a one-click **"Change my password"** link. Delivery
  failures never block the login itself — the alert is best-effort.
- Reuses the same email pipeline as verification/reset (console backend in
  dev, SMTP in production).

**Security log** — every account-security event is recorded and shown at
`/settings/security/` (newest first, with IPs):

- **Sign-ins** — every login, labelled **"Trusted browser"** vs
  **"New browser"** (and **"Signed in with 2FA"** when the challenge was
  completed), so you can spot a login you didn't make.
- **2FA events** — enabled / disabled / verified, trusted devices added and
  revoked (per-device and revoke-all), recovery-code issuance and
  regeneration.
- **Other security actions** — password changes, sign-in-alert toggles, and
  **"Sign out other sessions"** (a header button kills every session except
  the current browser's — the action is itself logged).
- **Filter by type** — chips above the list narrow it to **Sign-ins**,
  **2FA & codes**, **Devices** or **Account** events (`?filter=`); an
  unknown filter value safely falls back to "All" and can never hide events.
- **Private by design** — each user sees only their own events; rows are
  capped at `MAX_EVENTS_PER_USER` (500) per account, oldest pruned
  automatically, so the table can't grow without bound.

**Daily security digest** — with sign-in alerts on, users also get one
summary email per day. Run it from any scheduler (cron, Heroku Scheduler,
GitHub Actions) — it's safe to run more often than daily:

```bash
python manage.py send_security_digests            # send the digests
python manage.py send_security_digests --dry-run  # preview, send nothing
```

```cron
30 8 * * *  cd /path/to/ats && venv/bin/python manage.py send_security_digests
```

- Covers the last `SECURITY_DIGEST_WINDOW_HOURS` (default **24h**) — or
  since the last digest, whichever is more recent — with per-group counts
  (Sign-ins / 2FA & codes / Devices / Account), the latest 20 events and a
  link to the full log.
- **No news = no email** — users with nothing in the window aren't emailed;
  the per-user `security_digest_sent_at` timestamp prevents double-sends if
  cron runs twice, and failed deliveries are retried next run.

**Recovery codes** — 8 single-use `XXXXX-XXXXX` codes per batch:

- Issued **hashed** (salted PBKDF2, like passwords) — nobody, including us,
  can recover them from the database.
- Shown **exactly once** on `/settings/2fa/recovery/`, with copy-all and
  download buttons; after that the page only shows how many remain.
- Redeemable at the 2FA challenge (case-insensitive, separators ignored) and
  **consumed on use**. Running low? Regenerate a fresh batch from the 2FA
  settings page (password-confirmed); old codes stop working.

Dependencies: `pyotp` (TOTP) and `segno` (QR) — both tiny, pure-Python.

## 🛡️ Rate limiting

Public endpoints are protected by a lightweight sliding-window limiter
(`core/ratelimit.py`, zero dependencies — backed by Django's cache):

| Endpoint | Default limit | Bucket |
| --- | --- | --- |
| Login (failed attempts) | **5 failures / 15 min** per IP + username, **20 / 15 min** per IP (spraying), **10 / 15 min** per account → **15 min lockout** | IP + username + IP cap + account lockout |
| Signup | **5 accounts / hour** per IP | IP address |
| Resend verification | **3 emails / 15 min** | IP + submitted address |

- Only `POST` requests count; hitting the limit returns a branded **429**
  page with a `Retry-After` hint.
- **Login counts only *failed* attempts** — a successful login resets the
  counters for that IP + username, so a few typos never lock out a real user,
  while brute-forcing one account (or spraying many usernames) is throttled.
- **Account lockout** — after `ACCOUNT_LOCKOUT_LIMIT` failed attempts
  (default 10) across *any* IPs, the account is locked for
  `ACCOUNT_LOCKOUT_COOLDOWN` (default 15 min), with a friendly countdown
  notice on the login page. The **correct password always unlocks** — an
  attacker's noise can't lock out the real owner, and a brute-forcer can't
  produce the right password anyway. Lockout keys are per submitted username
  (existing or not), so it never reveals which accounts exist.
- Limits are read from settings at request time, so tune them via `.env`
  without touching code — e.g. `SIGNUP_RATE_LIMIT=10`, `SIGNUP_RATE_WINDOW=3600`,
  `RESEND_RATE_LIMIT=5`, `RESEND_RATE_WINDOW=900`, `LOGIN_RATE_LIMIT=5`,
  `LOGIN_IP_RATE_LIMIT=20`, `LOGIN_RATE_WINDOW=900`, `PASSWORD_MIN_LENGTH=12`,
  `TOTP_CHALLENGE_RATE_LIMIT=5`, `TOTP_CHALLENGE_RATE_WINDOW=900`.
- Development uses the per-process `LocMemCache`; in production point
  `CACHES` at a shared backend (Redis or the database cache) so limits are
  enforced across all app instances. The check-then-set is not atomic on a
  shared backend — under heavy concurrent load the effective limit can drift
  slightly; that is acceptable for an ATS.
- Behind a reverse proxy every request's `REMOTE_ADDR` is the proxy's IP, so
  all users would share one bucket. Configure trusted `X-Forwarded-For`
  handling (e.g. `gunicorn --forwarded-allow-ips=127.0.0.1`) so the limiter
  sees real client IPs, or accept per-instance limiting.

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
