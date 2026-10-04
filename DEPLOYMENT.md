# 🚀 PLAYOOT — Production Deployment

Kahoot-style multiplayer quiz platform. FastAPI + WebSocket backend, React/Vite
frontend served by nginx, PostgreSQL in production.

---

## 0. Topology

```
Browser  ──HTTPS──►  Caddy/TLS  ──HTTP──►  nginx :8080   (SPA + static)
                                                │
                            /api/*  ────────────┤
                            /ws/*   ────────────┤
                                                ▼
                                        backend :8000  (FastAPI)
                                                │
                                                ▼
                                          PostgreSQL :5432
```

The browser talks to **one origin**. nginx proxies `/api` and `/ws` internally,
so there is no CORS in production and no hardcoded host in the frontend.

---

## 1. 🔴 DO THIS FIRST — rotate credentials

The following real credentials currently exist on disk in your working copy:

| Credential type | Where | Action |
|---|---|---|
| Groq API key | `backend/.env` → `GROQ_API_KEY` | **REVOKE + reissue** at console.groq.com/keys |
| Google OAuth client secret | `backend/.env` → `GOOGLE_CLIENT_SECRET` | **Rotate** in Google Cloud Console |
| Firebase service-account private key | `backend/firebase-service-account.json` | **Delete the key** in Google Cloud → IAM → Service Accounts, then reissue |
| JWT `SECRET_KEY` | `backend/.env` | Generate a fresh one (below) |
| Database password | `.env` → `POSTGRES_PASSWORD` | Choose a strong one |

> No Git repository exists yet, so **nothing has been committed** and there is no
> history to scrub. `.gitignore` and `.dockerignore` are already in place so
> these files cannot be committed or baked into an image. Rotate anyway: the
> keys have been present in plaintext on a developer machine.

Generate a new signing key:
```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

---

## 2. Initialise Git (optional but recommended)

```bash
git init
git add .
git status          # confirm NO .env, NO firebase-service-account.json, NO *.db
git commit -m "Initial commit"
```

If `git status` ever shows a secret file, stop and fix `.gitignore` **before**
committing.

---

## 3. Required environment variables

Copy the template and fill it in:

```bash
cp .env.example .env
```

### Required (the app refuses to boot without these in production)

| Variable | Example | Notes |
|---|---|---|
| `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB` | `quizhost` / strong pw / `quizhost` | Compose creates the DB |
| `SECRET_KEY` | 64-char random string | ≥32 chars, not a placeholder |
| `CORS_ORIGINS` | `https://playoot.example.com` | Comma separated. No `*`, no `localhost` |
| `GROQ_API_KEY` | `gsk_…` | Required while `AI_ENABLED=true` |

### Optional

| Variable | Default | Notes |
|---|---|---|
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | Verified working model |
| `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` | – | Omit to disable Google login |
| `GOOGLE_REDIRECT_URI` | – | Must be `https://` + `/api/auth/google/callback` |
| `FIREBASE_PROJECT_ID` / `_PRIVATE_KEY` / `_CLIENT_EMAIL` | – | Required in production for phone auth |
| `RATE_LIMIT_TRUST_PROXY` | `true` | Keep `true` behind nginx; `false` if uvicorn is public |
| `DB_POOL_SIZE` / `DB_MAX_OVERFLOW` / `DB_POOL_RECYCLE` | `10` / `20` / `1800` | PostgreSQL pool sizing |
| `VITE_API_URL` / `VITE_WS_URL` | `/api` / empty | Frontend build-time; leave `VITE_WS_URL` empty |
| `VITE_FIREBASE_API_KEY` / `_AUTH_DOMAIN` / `_PROJECT_ID` / `_APP_ID` | – | **Required if you use phone auth.** `frontend/.env` is excluded from the Docker context, so these must be set in the root `.env` |
| `VITE_FIREBASE_SKIP_RECAPTCHA` | `false` | Keep `false` in production |

### Start-up validation

When `ENVIRONMENT=production` the backend **refuses to start** if any of these
is wrong, and prints every problem at once:

- `SECRET_KEY` missing / short / a known placeholder
- `DATABASE_URL` not PostgreSQL
- `DEBUG=true`
- `AUTO_MIGRATE=true`
- `CORS_ORIGINS` empty, contains `*`, or contains `localhost` / `127.0.0.1`
- `AI_ENABLED=true` with no `GROQ_API_KEY`
- `GOOGLE_REDIRECT_URI` that is not `https://` or points at localhost

---

## 4. Deploy

```bash
git clone <your-repo> playoot && cd playoot
cp .env.example .env && nano .env        # fill in section 3

# 1. build images (frontend is built inside the image)
docker compose -f docker-compose.prod.yml build

# 2. start the database and wait for it to be healthy
docker compose -f docker-compose.prod.yml up -d postgres

# 3. apply migrations  <-- EXPLICIT, one-off, before the backend starts
docker compose -f docker-compose.prod.yml run --rm backend alembic upgrade head

# 4. start backend + frontend
docker compose -f docker-compose.prod.yml up -d
```

The app is now on `http://<server-ip>:8080`.

> **Migrations are never automatic in production.** `AUTO_MIGRATE` is forced off
> and the app refuses to boot if it is on. Run step 3 on every deploy that ships
> schema changes, before step 4.

---

## 5. HTTPS (required — WebSockets need `wss://`)

Install Caddy in front of port 8080; it provisions a free certificate.

`/etc/caddy/Caddyfile`:
```
playoot.example.com {
    reverse_proxy localhost:8080
}
```

```bash
sudo apt install caddy
sudo systemctl reload caddy
```

With HTTPS the frontend derives `wss://playoot.example.com/ws/...` from the page
origin automatically — no extra configuration.

Optionally redirect plain HTTP to HTTPS and add security headers in
`frontend/nginx.conf`:
```nginx
add_header X-Content-Type-Options nosniff always;
add_header X-Frame-Options SAMEORIGIN always;
add_header Referrer-Policy strict-origin-when-cross-origin always;
```

---

## 6. Firebase / Google OAuth production configuration

### Google OAuth
1. Google Cloud Console → APIs & Services → Credentials → your OAuth client.
2. Add an **Authorized redirect URI** that is byte-identical to
   `GOOGLE_REDIRECT_URI`:
   - dev  → `http://localhost:8000/api/auth/google/callback`
   - prod → `https://YOUR_DOMAIN/api/auth/google/callback`
3. Put the client id + secret in `.env`.

### Firebase phone auth
1. Firebase console → Project settings → Service accounts → **Generate new
   private key**.
2. Copy `project_id`, `private_key` and `client_email` into `.env` as
   `FIREBASE_*`. Keep the literal `\n` escapes inside the quoted key.
3. Firebase console → Authentication → Settings → **Authorised domains** → add
   your production domain.
4. `firebase-service-account.json` is a **development-only** convenience. It is
   git-ignored, excluded from the image by `.dockerignore`, and the app
   **ignores it entirely when `ENVIRONMENT=production`** (it logs a warning).
   Production must use the environment variables.
5. Frontend build: set `VITE_FIREBASE_SKIP_RECAPTCHA=false`. Leaving it `true`
   breaks SMS delivery for real users (reCAPTCHA is only bypassed on localhost).

The `VITE_FIREBASE_*` values are Firebase **web client keys**, which are public
by design and safe in a browser bundle. What protects them is authorised-domain
restriction plus API-key restrictions — never put `SECRET_KEY`,
`GROQ_API_KEY`, `GOOGLE_CLIENT_SECRET`, the Firebase private key, or the
database password into any `VITE_*` variable.

---

## 7. Verification checklist

Run these after deploying.

**Liveness / readiness**
```bash
curl -i https://YOUR_DOMAIN/api/health    # 200, no infrastructure detail
curl -i https://YOUR_DOMAIN/api/ready     # 200 {"ready":true,"databaseReachable":true}
```
`/api/health` is safe to expose publicly. It intentionally does **not** return
the database DSN, live game PINs or provider configuration.

**API**
```bash
curl -s https://YOUR_DOMAIN/api | jq       # advertises /api/health, /api/ready
curl -i https://YOUR_DOMAIN/api/auth/login -H 'Content-Type: application/json' \
     -d '{"email":"nobody@example.com","password":"wrong"}'
```
Expect `401` (not `500`).

**SPA fallback** — each must return `200` HTML:
```
/   /login   /join   /dashboard   /create   /quiz/1   /play/123456   /results/123456
```

**WebSocket** — in DevTools → Network → WS, open a game and confirm the socket
connects to `wss://YOUR_DOMAIN/ws/game/<pin>` and stays open through a question.

**CORS** — from a browser on your real origin there must be no CORS error. From
a foreign origin the `Access-Control-Allow-Origin` header must be absent.

---

## 8. Local development (unchanged)

```bash
# backend - SQLite, AUTO_MIGRATE on, localhost CORS
cd backend
..\venv\Scripts\python.exe -m pytest -q          # 172 tests, no Groq credits used
..\venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000

# frontend
cd frontend
npm run dev
```

`pytest` overrides `DATABASE_URL` with a throwaway SQLite file in a temp
directory and mocks Groq, so running tests never touches `quizhost.db` and never
spends API credits.

---

## 9. Operations

**Backups** (PostgreSQL)
```bash
docker compose -f docker-compose.prod.yml exec -T postgres \
  pg_dump -U quizhost quizhost | gzip > backup-$(date +%F).sql.gz
```

**Logs**
```bash
docker compose -f docker-compose.prod.yml logs -f backend frontend
```

**Scaling** — the game registry (live game state) is **in-process**. Running
more than one backend replica will break live games: two players can land on
different instances. Stay single-instance until a shared store is added.

**Security headers / uptime** — consider adding status monitoring against
`/api/ready` (it returns `503` when the database is unreachable).

---

## 10. Troubleshooting

| Symptom | Cause |
|---|---|
| `ProductionConfigError` on boot | Read the printed list — it names every bad variable |
| `401` from CORS in the browser | `CORS_ORIGINS` missing or mismatched with the real origin |
| WebSocket connects then closes | TLS not terminated; browser is on `wss://` but nginx is serving plain HTTP |
| SPA 404 on refresh | `try_files $uri $uri/ /index.html;` missing from the nginx `location /` |
| Tables missing | Migrations not run — step 3 in section 4 |
| `socketRooms` / DSN in a response | Should not happen; `/api/health` was hardened — confirm you deployed the current build |
| SMS code never arrives | `VITE_FIREBASE_SKIP_RECAPTCHA` still `true`, or the domain is not in Firebase authorised domains |

