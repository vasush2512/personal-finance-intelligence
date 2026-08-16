# Security review

Phase 4, step 4. Every item below was checked against the code as it stands,
not assumed from the design. Where something was fixed, the fix is named; where
something is a real limitation, it is stated plainly rather than softened.

**Scope note.** This app runs on localhost against a local SQLite file, with a
single user's own bank statements. That context changes what several findings
mean — it does not make them untrue.

---

## Fixed in this review

### Uploads had no size limit — **fixed**

`upload_statement` called `file.file.read()`, which reads the entire uploaded
file into memory with no ceiling. A multi-gigabyte upload would have exhausted
memory before anything checked it.

Fixed in `app/routers/s17_uploads.py`: `read_within_limit()` reads in 1 MB
chunks and aborts with **413** past 25 MB. Chunked deliberately — a limit
checked *after* `.read()` has already performed the exhaustion it exists to
prevent. Covered by `tests/test_upload_limits.py`, including a test that a 2 GB
file is never read to the end.

### Exported data carried account and card numbers — **fixed**

Export is the one place this data leaves the application. Bank narrations carry
UTRs, card numbers and account numbers, and 28 of 29 sample rows contained one.

Fixed in `app/store/s12d_export.py`: runs of nine or more digits are masked to
their last four (`412345678901` → `XXXX8901`). Nine digits is past any
plausible amount or year. The last four are kept so a row can still be matched
against a paper statement, and the Merchant column is untouched. **The stored
data is not modified** — only the exported copy.

---

## Checked and sound

| Item | Finding |
|---|---|
| **Password storage** | `pbkdf2_sha256`, **600,000 iterations**, per-user salt from `secrets.token_bytes`. Parameters stored with the hash so the count can be raised later without locking anyone out. |
| **Password comparison** | `hmac.compare_digest`, not `==`. A plain comparison stops at the first differing byte and leaks how much was guessed. |
| **Password exposure** | `AccountOut` has no password field and cannot name the hash, so no endpoint can return it by accident. |
| **Sign-in error messages** | 401 says the same thing whether the address is unknown or the password is wrong — no account enumeration. |
| **SQL injection** | Every query is built through SQLAlchemy with bound parameters. The only raw SQL in the project is the `ALTER TABLE` in `s03_db.py`, whose table and column names come from model metadata written by a developer, never from a request. |
| **Secrets in frontend code** | None. No API keys, tokens or credentials anywhere in `frontend/src`. |
| **Upload file types** | Extension checked against an allow-list, *and* the real format detected from the bytes rather than trusted from the name. |
| **Unsafe parsing** | The CSV parser never raises on a bad file — bad rows are skipped and counted. Excel is read by `openpyxl`, which does not evaluate formulas or macros. |
| **Path traversal** | Uploaded filenames are stored as data and never used to build a filesystem path. Export filenames are generated server-side, never echoed from input. |
| **CORS** | Restricted to the two localhost dev origins, with `allow_credentials=False`. |
| **Question endpoint** | `/api/ask` truncates input at 300 characters and matches it against a fixed pattern list. Nothing is evaluated, executed or interpolated into a query. |

---

## Fixed in the follow-up phase

### 1. Sign-in now protects something — **fixed**

It used to gate nothing: the session lived entirely in the browser and no
endpoint asked who was calling, so anyone who could reach port 8000 could read
and modify every transaction without signing in.

Now sign-in issues a 32-byte random token, stored only as its SHA-256 hash,
expiring after 14 days. Every data endpoint requires it. Sign-out deletes the
row, so the token stops working immediately rather than being forgotten by a
browser that could simply remember it again.

### 2. Per-user data isolation — **fixed**

`transactions` and `uploads` now carry `user_id`, threaded through
`source_conditions` so it reaches every total, trend, detector and export at
once — including ones written later. Existing rows were assigned to their owner
by `scripts/backfill_ownership.py`, which refuses to guess when more than one
account exists.

Proved rather than assumed: a two-user probe over real HTTP covers 42 checks —
17 endpoints returning 401 unauthenticated, one user seeing zero of another's
205 rows, and cross-user read, write and delete all refused with 404 rather
than 403 (confirming a row exists would leak which ids are real). Its first run
found three leaks that would otherwise have shipped.

## Real limitations — not fixed, and you should know

### 1. The database is not encrypted

`data/expenses.db` is a plain SQLite file. Anyone with access to the machine
can read every transaction with any SQLite tool. Appropriate for a local
single-user app; worth knowing before the file is copied anywhere.

---

### 2. The session token is readable by injected script

It lives in `sessionStorage`, so any successful XSS could read it. An
httpOnly cookie would not be, at the cost of CSRF protection to add. For a
localhost single-user app this is the right trade; for a deployed one it is
not.

### 3. Fingerprint uniqueness is global, not per-user

The unique index is on `fingerprint` alone, so two accounts cannot upload the
*same file*. Deduplication is scoped per-user in the query; the constraint is
not. Fixing it means rebuilding the table, which the auto-migration
deliberately will not do.

## Verdict

Nothing here is exploitable by a remote attacker in the way this app is
actually run — it binds to `127.0.0.1` and is not deployed. Every finding from
the first pass has been fixed, and each is covered by tests.

The limitations above are honestly scoped and mostly about deployment: the
unencrypted file and the storage of the token both stop being acceptable the
moment this is served on a network.
