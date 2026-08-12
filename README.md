# Expense Tracker

Upload a bank statement CSV. Every transaction is parsed, deduplicated and
auto-categorized — first by keyword rules, then by a classifier trained on
those rules' output — and a dashboard shows where the money went, with
unusually large spending flagged.

Built for Indian bank statements: UPI/NEFT/IMPS narrations, `₹` amounts with
lakh grouping (`1,25,000.50`), and separate withdrawal/deposit columns.

## Screenshots

<!-- Replace these with real screenshots: run the app, then drop PNGs in docs/ -->

| | |
|---|---|
| ![Dashboard](docs/dashboard.png) | ![Transactions](docs/transactions.png) |
| Summary cards, monthly trend, category breakdown | Filterable table with inline re-categorization |

## Stack

| Layer | Choice |
|---|---|
| API | FastAPI, SQLAlchemy 2.x, SQLite |
| ML | scikit-learn — TF-IDF (word + char n-grams) into LogisticRegression |
| Data | pandas, Python `Decimal` for all money |
| UI | React (Vite) + Recharts, plain `fetch`, no UI library |
| Tests | pytest — 98 cases |

## Running it

Two servers. On Windows, double-click each `start.bat`; otherwise:

**Backend** (from `backend/`):

```
python -m venv venv
venv\Scripts\activate          # source venv/bin/activate on macOS/Linux
pip install -r requirements.txt
uvicorn app.main:app --reload
```

API docs at <http://127.0.0.1:8000/docs>.

**Frontend** (from `frontend/`):

```
npm install
npm run dev
```

Dashboard at <http://localhost:5173>.

Then upload `backend/data/sample_statement.csv` — 205 fake transactions with
deliberate duplicates, a junk header block and one malformed row.

**Tests** (from `backend/`): `pytest`

## How categorization works

Three stages, each one only handling what the previous could not.

**1. Normalize.** A bank narration is mostly noise:

```
UPI/DR/412345678901/SWIGGY/HDFC/swiggyupi@icici/Payment   ->   swiggy
```

Strip the payment rail, the reference number, the UPI handle, the bank code,
the PSP name, and the punctuation. Both later stages work on this cleaned
form, so a description is only ever cleaned in one place.

**2. Keyword rules.** ~60 ordered regex rules map merchants to categories.
First match wins, so specific merchants sit above generic words and income
sits above the generic transfer vocabulary. Anything unmatched becomes
`other`.

**3. The model.** TF-IDF into LogisticRegression, trained on whatever the
rules labelled. It runs **only** on rows the rules left as `other`, and
abstains below 0.55 confidence rather than guess.

Why train a model on the rules' own output? Because on day one there is no
labelled data, and nobody is going to hand-label 200 transactions before the
app does anything useful. The rules provide cheap, noisy labels — *weak
supervision* — and the model generalizes past the exact keywords. Corrections
you make in the UI join the same training set, so accuracy improves as you
use it.

Why word **and** character n-grams? Bank narrations fuse tokens together —
`UPISWIGGYBLR`, `AMAZONPAYINDIA`. Word n-grams miss those entirely; character
n-grams (`char_wb`, 3–5) catch `swigg` regardless of what it is glued to.

Why abstain at 0.55? A wrong category you have to hunt down is worse than an
honest `other`.

Every row records who labelled it — `rule`, `model` (with confidence), or
`user`. **A user label is never overwritten** by a later import or retrain.

## Two numbers not to quote without the caveat

**96.6% rule coverage on the sample data is inflated.** The same script wrote
both the keyword rules and the sample's fake merchants, so of course they
match. On a real statement expect roughly 60–75%.

**0.98 held-out accuracy measures agreement with the rules, not
correctness.** The training labels came from the rules, so the model is being
scored on how well it reproduces them. That is what weak supervision buys:
coverage, not ground truth. The honest number only exists after you correct
rows in the UI and evaluate against those corrections.

## Duplicate detection

Every row gets a SHA-256 fingerprint of
`date | normalized description | amount | direction`, stored with a unique
index. Re-uploading a statement imports 0 rows and reports them as
duplicates. Statements that overlap by a few weeks — the normal case when you
download monthly — only contribute their new rows.

The trade-off: two genuinely identical transactions on the same day (two ₹40
chai payments) collapse into one. Accepted, because the alternative
duplicates every re-upload.

## Unusual spending

Within a category, over the trailing six months, a debit is flagged when it
exceeds `mean + 2.5 × standard deviation`, requiring at least 8 prior
transactions in that category. The flagged transaction is excluded from its
own baseline. Each flag carries a sentence:

> Rs 9,400.00 on food — 23.0x your usual Rs 409.00

Deliberately plain statistics rather than IsolationForest, for two reasons:
the user needs a reason they can read, and the method has to be explainable
without hand-waving.

This is computed on every request rather than stored in a column. The flag
depends on a moving window, so a charge that looks extraordinary today stops
being one once similar charges arrive — a stored flag would quietly go stale.

## Money

`Decimal` in Python, a 2-decimal **string** in JSON, and whole **paise as an
INTEGER** in SQLite. Never a float, anywhere.

SQLite has no decimal type: given a `NUMERIC` column, SQLAlchemy round-trips
money through a float and warns that rounding errors may occur. Integer paise
keeps arithmetic exact and still lets SQL do `SUM()` and `ORDER BY`. The
`Money` type in `app/models.py` converts at the boundary, so the rest of the
code only ever sees `Decimal`.

## API

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | liveness |
| `POST` | `/api/upload` | import a CSV; returns imported/skipped/duplicate counts |
| `GET` | `/api/transactions` | list, filtered by month/category/search/direction |
| `PATCH` | `/api/transactions/{id}` | correct a category; marks it `user` |
| `GET` | `/api/categories` | the category vocabulary |
| `POST` | `/api/model/retrain` | refit the classifier; returns accuracy |
| `GET` | `/api/summary` | totals, category split, top merchants |
| `GET` | `/api/trends` | spend and income per month |
| `GET` | `/api/anomalies` | unusually large debits, with reasons |
| `DELETE` | `/api/uploads/{id}` | remove an upload and its transactions |

Spending totals exclude `transfer`: moving money between your own accounts is
not an expense, and counting it inflates every chart in a way that still
looks plausible.

## Parsing

The parser never raises on a bad row — bad rows are counted and skipped. Only
a file with no findable header fails, and that error carries the column names
it did detect so the UI can say what was wrong.

It handles junk blocks above the real header, `,`/`;`/tab/`|` delimiters,
three encodings, ten date formats, `₹`/`Rs`/comma/parenthesised amounts,
trailing `CR`/`DR`, separate withdrawal+deposit columns or one signed amount
column, and roughly 40 column-name variations.

## Project layout

```
backend/
  app/
    main.py            FastAPI app, CORS, router registration
    config.py          paths and settings
    db.py              engine, session, Base
    models.py          Transaction, Upload, the Money type
    schemas.py         Pydantic request/response models
    constants.py       CATEGORIES and the keyword rules
    routers/           one file per resource
    services/          parsing, importing, aggregation - the business logic
    ml/                categorizer, trainer, anomalies - no web framework here
  tests/               98 pytest cases
  data/                sample_statement.csv, expenses.db, model.joblib
frontend/
  src/
    api.js             every fetch call lives here
    components/
```

`app/ml/` and the parsing services import nothing from FastAPI or SQLAlchemy,
so they can be tested and reused on their own.

## Not built, on purpose

No accounts or login, no budgets or alerts, no bank API integration, no PDF
or Excel parsing, no multi-currency, no deployment. See §3 of `PRD.md`.
