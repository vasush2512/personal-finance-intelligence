# Build steps — Expense Tracker in Claude Code

Follow these in order. Do not skip ahead. Each phase ends with a check and a git
commit, so when something breaks you can always go back to a working state.

---

## Step 0 — Set up the folder (do this yourself, not with Claude)

```bash
mkdir expense-tracker
cd expense-tracker
git init
mkdir backend frontend
```

Put `PRD.md` and `CLAUDE.md` in the root of `expense-tracker`.

Create the Python environment:

```bash
cd backend
python -m venv venv
```

Activate it:

- Windows (CMD): `venv\Scripts\activate`
- Windows (PowerShell): `venv\Scripts\Activate.ps1`
- macOS / Linux: `source venv/bin/activate`

You should see `(venv)` at the start of your prompt. Then go back to the project
root and start Claude Code:

```bash
cd ..
claude
```

Commit the empty skeleton:

```bash
git add . && git commit -m "chore: project setup with PRD and CLAUDE.md"
```

---

## The loop you repeat for every phase

1. Paste the phase prompt.
2. Read what Claude proposes; if it starts building extra things, stop it.
3. Run the app / tests yourself and check the "verify" box below.
4. Commit.
5. Type `/clear` to reset the context before the next phase.

`/clear` matters. Without it, context from Phase 2 clutters Phase 5 and the
answers get worse.

---

## Phase 1 — Skeleton

**Prompt:**

```
Read PRD.md and CLAUDE.md.

Build Phase 1 only: the backend skeleton.

- backend/requirements.txt with fastapi, uvicorn, sqlalchemy, pandas,
  scikit-learn, joblib, pytest, python-multipart
- app/config.py, app/db.py (SQLAlchemy engine + session + Base, SQLite at
  data/expenses.db)
- app/models.py with the transactions and uploads tables exactly as in PRD §6
- app/constants.py with the CATEGORIES list
- app/main.py with a GET /health endpoint returning {"status": "ok"}
- Tables created on startup

Do not build the CSV parser, categorizer, or any other endpoint yet.
Before you write files, list the files you plan to create.
```

**Verify:**

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open `http://127.0.0.1:8000/health` → you should see `{"status":"ok"}`.
Open `http://127.0.0.1:8000/docs` → FastAPI's auto docs load.
Check that `backend/data/expenses.db` now exists.

**Commit:** `git add . && git commit -m "feat: backend skeleton with models"`

---

## Phase 2 — CSV ingestion

**Prompt:**

```
Read PRD.md. Build Phase 2 only: CSV ingestion.

- app/services/parser.py implementing every parsing rule in PRD §7.1:
  junk rows above the header, the column name variations listed, the three
  date formats, comma/₹ amounts, separate withdrawal+deposit columns OR a
  single signed amount column, skipping unparseable rows.
- Duplicate detection via the fingerprint in PRD §7.2.
- POST /api/upload and GET /api/transactions with the filters in PRD §8.
- data/sample_statement.csv as described in PRD §12: ~200 fake rows, every
  category represented, some duplicates, a junk header block, one malformed row.
- pytest cases covering at least 3 different CSV shapes.

Categorization comes later — set every category to "other" for now.
```

**Verify:**

```bash
pytest
```

Then in `/docs`, use `POST /api/upload` to upload `data/sample_statement.csv`.
It should return counts for imported / skipped / duplicates. Upload the **same
file again** — imported should be 0. Then `GET /api/transactions` should return
your rows.

**Commit:** `git add . && git commit -m "feat: CSV parsing and upload"`

---

## Phase 3 — Rule-based categorization

**Prompt:**

```
Read PRD.md. Build Phase 3 only: rule-based categorization.

- The description normalizer described in PRD §7.3 (strip UPI/NEFT/IMPS/POS,
  reference numbers, long digit runs, punctuation; lowercase).
- A keyword rule map in app/constants.py, around 60 keywords, weighted toward
  merchants common in India.
- app/ml/categorizer.py applying rules at import time, setting
  category_source = 'rule'.
- PATCH /api/transactions/{id} to correct a category, setting
  category_source = 'user'.
- Tests for the normalizer and the rule matcher.

No machine learning yet.
```

**Verify:** delete `data/expenses.db`, restart the server, re-upload the sample
CSV. Most rows should now have a real category. `PATCH` one row and confirm the
change sticks after a page refresh.

**Commit:** `git add . && git commit -m "feat: rule-based categorization"`

---

## Phase 4 — The ML model

**Prompt:**

```
Read PRD.md. Build Phase 4 only: the ML classifier, exactly as in PRD §7.3
stage 2.

- app/ml/trainer.py: TF-IDF (word 1-2 grams + char_wb 3-5) into
  LogisticRegression, trained on rule-labelled and user-labelled rows, saved
  with joblib to data/model.joblib.
- Train/test split, report held-out accuracy.
- Refuse to train when there are fewer than 50 labelled rows, and say so.
- At import time: rules first, model only for what the rules miss.
  predict_proba below 0.55 → category "other", store the confidence.
- POST /api/model/retrain returning accuracy and label count.
- User-corrected labels are never overwritten by the model.

Explain in comments why the model is trained on rule output — I need to be able
to explain this in an interview.
```

**Verify:** call `POST /api/model/retrain` and check it returns an accuracy
figure. Re-upload the sample CSV into a fresh DB and confirm some rows now show
`category_source: "model"` with a confidence value.

**Commit:** `git add . && git commit -m "feat: ML categorizer with retrain"`

---

## Phase 5 — Dashboard

Do this in two prompts, not one. The frontend is the biggest chunk.

**Prompt 5a — the remaining API endpoints:**

```
Read PRD.md. Build the remaining backend endpoints from PRD §8:
GET /api/summary, GET /api/trends, DELETE /api/uploads/{id}.
Aggregation logic goes in app/services/. Add CORS middleware allowing
http://localhost:5173. Backend only — no frontend yet.
```

**Prompt 5b — the React app:**

```
Now build the frontend from PRD §7.5.

- Vite + React in frontend/, Recharts for charts
- src/api.js holds every fetch call, nothing else calls the API directly
- Upload screen, summary cards, monthly trend bar chart, category donut,
  top merchants, transaction table with month/category/search filters and an
  inline category dropdown that calls PATCH
- Empty state when there is no data; loading states while fetching
- Clean and readable, no UI library

Do not build the anomalies view yet.
```

**Verify:** `npm run dev`, upload the sample CSV through the UI, change a
category from the table, refresh — the change persists.

**Commit:** `git add . && git commit -m "feat: dashboard"`

---

## Phase 6 — Anomalies and polish

**Prompt:**

```
Read PRD.md. Build Phase 6: anomaly detection (§7.4) plus polish.

- app/ml/anomalies.py using the mean + 2.5*std rule per category over the
  trailing 6 months, minimum 8 prior transactions, with the human-readable
  reason string.
- GET /api/anomalies and a flagged-transactions panel in the UI.
- Error toasts on failed uploads showing the backend's message.
- A README.md: what the project is, the stack, setup commands, how the
  categorization works, and placeholders for screenshots.
```

**Verify:** run the whole flow start to finish in a browser as if you were a
stranger seeing it for the first time.

**Commit:** `git add . && git commit -m "feat: anomaly detection and README"`

---

## Prompts for when things break

Use these instead of "it's not working":

```
Running `uvicorn app.main:app --reload` gives this error:
<paste the FULL traceback>
Find the cause and fix it. Explain what was wrong before you change anything.
```

```
The upload endpoint returns 500 for data/sample_statement.csv but works for a
2-row file. Add logging to find where it fails, then fix it.
```

```
Explain what app/ml/trainer.py does line by line. I am learning — assume I have
not used scikit-learn pipelines before.
```

```
git reset --hard HEAD        ← undo everything since your last commit
git log --oneline            ← see your commits
```

---

## Habits that keep this from falling apart

- **Commit after every phase.** This is your undo button.
- **`/clear` between phases.** Fresh context, better answers.
- **Run the code yourself** after every phase. Do not trust "done" without
  seeing it work.
- **Push back when it over-builds.** "I only asked for Phase 3. Remove the
  budgets feature." is a normal thing to say.
- **Read the diffs.** If you cannot explain a file in an interview, ask Claude
  to walk you through it before moving on.
