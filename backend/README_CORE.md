# Core logic — already built and tested

This is Phases 2, 3 and 4 of the PRD: the parts that are actually hard and
that make this an ML project rather than a CRUD app. Everything here was run
and verified before you got it.

    backend/
      app/constants.py              categories + ~60 keyword rules
      app/services/normalize.py     narration cleaner + fingerprint
      app/services/parser.py        messy bank CSV -> clean dicts
      app/ml/categorizer.py         stage 1: rules
      app/ml/trainer.py             stage 2: TF-IDF + LogisticRegression
      app/ml/anomalies.py           unusual-spend detection
      scripts/make_sample.py        regenerates the fake statement
      scripts/pipeline_demo.py      runs the whole pipeline, prints stats
      tests/test_core.py            42 test cases
      data/sample_statement.csv     205 unique rows + duplicates + junk

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

FastAPI app, SQLAlchemy models, routes, and the Expo mobile app. Those are
Phase 1, 5 and 6 — build them in Claude Code using BUILD_STEPS.md and
MOBILE_ADDENDUM.md. These modules deliberately import nothing from FastAPI or
SQLAlchemy, so they drop straight into the structure in CLAUDE.md.
