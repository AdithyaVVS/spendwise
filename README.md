# SpendWise

A personal expense and budget manager. Track spending by category, set monthly budgets, import bank statements from CSV, and see on a dashboard how the month is going compared with your budget.

**Live demo:** https://spendwise-1-epdq.onrender.com

> The demo runs on a free hosting tier, which sleeps after about 15 minutes of inactivity. The first visit after a pause can take 30 to 60 seconds to wake up. Create an account (there is no email verification) and import `backend/samples/demo.csv` to see the dashboard with data. Please don't use a real password on the demo site.

<!-- Add screenshots here, for example:
![Dashboard](docs/dashboard.png)
![Budgets](docs/budgets.png)
![CSV import](docs/import.png)
-->

## Features

- **Accounts:** register and log in; every user sees only their own data
- **Transactions:** add, edit and delete; filter by date range, category and description text; paginated, with a total for the filtered results
- **Categories:** create, rename and delete; a category that still has transactions can't be deleted
- **Budgets:** a monthly overall budget plus per-category budgets, with spent, remaining, percent used and an On track / Close to limit / Over budget status
- **Dashboard:** the month's total spending and a comparison with the previous month, a budget strip that shows how much of the overall budget is used against how much of the month has passed, category budget bars, spending-by-category and daily-spending charts, and a category breakdown table
- **CSV import:** upload a statement; valid rows are imported, bad rows are reported with a row number and reason, duplicates are skipped, and missing categories are created

## Tech stack

| Layer | Technology |
|---|---|
| Backend | Python, FastAPI |
| Database | PostgreSQL, SQLAlchemy, Alembic migrations |
| Auth | bcrypt password hashing, JWT access tokens |
| Validation | Pydantic |
| Frontend | HTML, CSS, vanilla JavaScript (Fetch API), Chart.js |
| Testing | pytest against a separate PostgreSQL test database |
| Rate limiting | slowapi |
| Local database | Docker Compose |
| Hosting | Render (app), Neon (PostgreSQL) |

FastAPI also serves the frontend as static files, so the whole app is one deployable service and needs no CORS configuration.

## API overview

| Area | Endpoints |
|---|---|
| Auth | `POST /api/auth/register`, `POST /api/auth/login`, `GET /api/auth/me` |
| Categories | `GET/POST /api/categories`, `PUT/DELETE /api/categories/{id}` |
| Transactions | `GET/POST /api/transactions`, `GET/PUT/DELETE /api/transactions/{id}`; list filters: `date_from`, `date_to`, `category_id`, `search`, `page`, `page_size` |
| Import | `POST /api/transactions/import` (CSV upload) |
| Budgets | `GET/PUT /api/budgets`, `GET /api/budgets/status?month=2026-10`, `DELETE /api/budgets/{id}` |
| Dashboard | `GET /api/dashboard?month=2026-10` |
| Health | `GET /api/health` |

Interactive API docs are served at `/docs`.

## Data model

- **users:** `email` (unique), `password_hash`
- **categories:** belongs to a user; the name is unique per user
- **transactions:** belongs to a user and a category; `amount NUMERIC(12,2)` with a `CHECK (amount > 0)`; composite index on `(user_id, date)`
- **budgets:** belongs to a user; optional category (null means the overall budget); month stored as the first day of the month; unique per user, category and month

## Design decisions

- **Per-user data isolation.** Every query filters by the authenticated user's id as well as the record id. Another user's record looks the same as a missing one (`404`, not `403`), so ids can't be probed. Creating or moving a transaction into someone else's category is also a `404`.
- **Money is never a float.** Amounts are `Decimal` in Python, `NUMERIC(12,2)` in Postgres and strings in JSON. All totals, remaining amounts and percentages are computed on the server.
- **Constraints in the database, not just the code.** Positive amounts, unique category names per user, one budget per category per month and first-day-of-month budget dates are all enforced by Postgres. The overall budget has a null category, and Postgres treats nulls as distinct in unique constraints, so a partial unique index covers that case.
- **Aggregation in SQL.** Budget status and the dashboard use `GROUP BY` queries, so the cost doesn't grow with the number of rows returned. Month ranges are half-open (`date >= start AND date < next month`).
- **Percentage change from zero is null,** not infinity; the UI shows "New".
- **Safe CSV import.** Limited to 1 MB and 1000 rows, UTF-8 only (Excel's BOM is handled), amounts parsed as `Decimal`, partial success with a per-row report, and duplicate detection against existing data that counts copies, so two identical purchases in one file are both kept the first time but re-importing the same file adds nothing.
- **Authentication.** bcrypt with a per-password salt; login returns the same error for an unknown email and a wrong password and verifies against a dummy hash for unknown emails, so response time doesn't reveal which accounts exist. Tokens are signed JWTs that expire after 24 hours.
- **Hardening.** Rate limits on login and registration, security headers on every response (including a Content Security Policy on the web pages, which is why the pages use no inline scripts), `Cache-Control: no-store` on API responses, a generic 500 response that doesn't leak internals, and a refusal to start in production with a short signing secret.
- **Output escaping.** All server-provided text is escaped before it is placed in the page.
- **A budget strip with a pace marker.** The dashboard shows the overall budget as a strip with one notch per day of the month and a marker at where an even spending pace would put you today, so you can see at a glance whether you are spending faster or slower than the month is passing.
- **Visual design.** The palette is drawn from Indian banknotes (violet, teal, saffron and magenta on a sage-grey ground), with a serif display face for headings and amounts and a clean sans-serif for everything else. Over budget is magenta rather than the usual red.

## Testing

The pytest suite runs against a separate `spendwise_test` database that is rebuilt before every test, and the setup asserts the database name so it can't run against real data. It covers:

- registration rules, password hashing, login, and expired, forged and unsigned tokens
- category and transaction CRUD and amount validation
- **isolation:** one user trying to read, edit, delete and reuse another user's data, and a check that all protected endpoints return `401` without a login
- filters, search and pagination
- budget maths, the 80% and 100% boundaries, and month and year boundaries
- dashboard comparisons, empty months and leap years
- CSV import: good rows, many kinds of bad rows, duplicates and unusual file formats
- rate limits, security headers, production safety checks, and a guard that fails if an inline script or event attribute is added to a page

## Run locally

Requires Python 3.10+, Docker and Git.

```bash
git clone https://github.com/AdithyaVVS/spendwise.git
cd spendwise

# 1. Start PostgreSQL (port 5433)
docker compose up -d

# 2. Python environment
cd backend
python -m venv venv
venv\Scripts\activate          # Windows (macOS/Linux: source venv/bin/activate)
pip install -r requirements.txt

# 3. Configuration: create backend/.env containing
#    DATABASE_URL=postgresql+psycopg2://spendwise:spendwise@localhost:5433/spendwise
#    JWT_SECRET=<a long random string, for example: python -c "import secrets; print(secrets.token_hex(32))">

# 4. Create the tables and start the server
alembic upgrade head
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000 for the app or http://127.0.0.1:8000/docs for the API docs.

To run the tests:

```bash
docker exec -it spendwise_db psql -U spendwise -d spendwise -c "CREATE DATABASE spendwise_test;"
cd backend
pytest -q
```

### Configuration

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | required | PostgreSQL connection string (use the `postgresql+psycopg2://` prefix) |
| `JWT_SECRET` | required | Signing key for login tokens |
| `JWT_EXPIRE_MINUTES` | `1440` | Login token lifetime |
| `PRODUCTION` | `false` | Enables HSTS and requires a `JWT_SECRET` of at least 32 characters |
| `LOGIN_RATE_LIMIT` | `10/minute` | Per-IP limit on login attempts |
| `REGISTER_RATE_LIMIT` | `5/minute` | Per-IP limit on registrations |

## Project structure

```
spendwise/
├── backend/
│   ├── app/
│   │   ├── main.py            # app setup, security headers, error handling, static files
│   │   ├── config.py          # environment-based settings
│   │   ├── database.py        # engine and session
│   │   ├── models.py          # users, categories, transactions, budgets
│   │   ├── schemas.py         # request and response validation
│   │   ├── security.py        # password hashing and JWT
│   │   ├── dependencies.py    # get_current_user
│   │   ├── limiter.py         # rate limiter
│   │   ├── routes/            # auth, categories, transactions, importer, budgets, dashboard
│   │   └── services/          # ownership checks, CSV import
│   ├── alembic/               # database migrations
│   ├── samples/               # example CSV files
│   ├── tests/                 # pytest suite
│   └── requirements.txt
├── frontend/                  # login, dashboard, transactions, budgets, import, categories
│   ├── css/style.css
│   └── js/
├── docker-compose.yml         # local PostgreSQL
└── README.md
```

## Deployment

- **App:** Render web service with root directory `backend`, build command `pip install -r requirements.txt`, and start command `alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port $PORT --proxy-headers --forwarded-allow-ips="*"`
- **Database:** Neon managed PostgreSQL, with its own database for this app
- Environment variables set on the host: `DATABASE_URL`, `JWT_SECRET`, `PRODUCTION=true`, `PYTHON_VERSION`

## Known limitations and ideas

- Login tokens are kept in `localStorage` and can't be revoked before they expire. HttpOnly cookies with CSRF protection, or short-lived access tokens with refresh tokens, would be the next step.
- No email verification or password reset.
- Rate limit counters are held in memory, so they are per server instance and reset on restart.
- Recurring expenses, CSV export and custom date ranges on the dashboard are natural additions.
