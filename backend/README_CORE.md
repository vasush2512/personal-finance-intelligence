# Core logic — already built and tested

This is Phases 2, 3 and 4 of the PRD: the parts that are actually hard and
that make this an ML project rather than a CRUD app. Everything here was run
and verified before you got it.

Modules are numbered in reading order; `s05` to `s10` below is one bank row's
journey from raw text to a category.

    backend/
      app/core/s01_constants.py       categories + ~60 keyword rules
      app/pipeline/s05_normalize.py   narration cleaner + fingerprint
      app/pipeline/s06_readers.py     bytes -> rows (CSV / JSON / Excel)
      app/pipeline/s07_parser.py      messy bank statement -> clean dicts
      app/pipeline/s08_rules.py       stage 1: rules
      app/pipeline/s09_model.py       stage 2: TF-IDF + LogisticRegression
      app/pipeline/s10_anomalies.py   unusual-spend detection
      scripts/make_sample.py          regenerates the fake statement
      scripts/pipeline_demo.py        runs the whole pipeline, prints stats
      tests/test_core.py              42 test cases
      data/sample_statement.csv       205 unique rows + duplicates + junk

## Run it

    cd backend
    python -m venv venv
    venv\Scripts\activate          # Windows CMD
    # source venv/bin/activate     # macOS / Linux
    pip install -r requirements.txt

    python scripts/pipeline_demo.py
    pytest

## What the demo prints

    rows parsed        : 207     (3 skipped: junk header, footer, malformed row)
    duplicate rows     : 2
    matched by rules   : 198/205 (96.6%)
    held-out accuracy  : 0.98
    anomalies flagged  : 4

## Two numbers not to quote in an interview without a caveat

**96.6% rule coverage is inflated.** The same file wrote both the keyword
rules and the fake merchants in the sample data, so of course they match.
On a real statement expect roughly 60-75%. Run it on your own statement (do
not commit it) to find your true number.

**0.98 accuracy measures agreement with the rules, not correctness.** The
training labels came from the rules, so the model is being scored on how well
it reproduces them. That is what weak supervision buys you: coverage, not
ground truth. The honest number only appears after a user corrects rows and
you evaluate against those corrections.

Being able to say that out loud is worth more in an interview than the 0.98.

## What is NOT here

**Out of date as of 2026-08-14.** The FastAPI app, the SQLAlchemy models and
every route are now built — see `app/core/`, `app/store/` and `app/routers/`,
and PRD §11 for what is left (the frontend, which does not exist yet).

What is still true is the constraint: nothing in `app/pipeline/` imports
FastAPI or SQLAlchemy. That separation is why the modules above can be tested
without a database or a server, and it is enforced by the folder layout.
