"""Run the whole categorization pipeline against the sample statement.

    python scripts/pipeline_demo.py

Parse -> rules -> train -> fill gaps -> anomalies, printing what happened at
each stage. No database, no API. This is how you check the core logic works
before any of it is wired into FastAPI.
"""

import os
import sys
from collections import Counter

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.pipeline.s10_anomalies import detect_anomalies                      # noqa: E402
from app.pipeline.s08_rules import apply_rules                          # noqa: E402
from app.pipeline.s09_model import NotEnoughData, categorize_unmatched, load_model, train  # noqa: E402
from app.pipeline.s07_parser import parse_statement                     # noqa: E402

SAMPLE = os.path.join(os.path.dirname(__file__), "..", "data", "sample_statement.csv")


def section(title):
    print("\n" + title)
    print("-" * len(title))


def main():
    with open(os.path.abspath(SAMPLE), "rb") as handle:
        transactions, skipped = parse_statement(handle.read())

    section("1. Parsing")
    unique = {t["fingerprint"] for t in transactions}
    print(f"rows parsed        : {len(transactions)}")
    print(f"rows skipped       : {skipped}  (junk header, footer, malformed row)")
    print(f"duplicate rows     : {len(transactions) - len(unique)}")

    # keep only the first occurrence of each fingerprint, as the DB would
    seen, deduped = set(), []
    for txn in transactions:
        if txn["fingerprint"] in seen:
            continue
        seen.add(txn["fingerprint"])
        deduped.append(txn)
    transactions = deduped

    section("2. Rules")
    stats = apply_rules(transactions)
    print(f"matched by rules   : {stats['matched']}/{stats['total']} "
          f"({stats['coverage'] * 100:.1f}%)")
    unmatched = [t for t in transactions if t["category"] == "other"]
    print(f"left as 'other'    : {len(unmatched)}")
    for txn in unmatched[:5]:
        print(f"   - {txn['normalized_description'][:60]}")

    section("3. Model")
    try:
        report = train(transactions)
        print(f"labelled rows      : {report['labelled_rows']}")
        print(f"classes learned    : {', '.join(report['classes'])}")
        print(f"held-out accuracy  : {report['holdout_accuracy']}")
    except NotEnoughData as error:
        print(f"skipped: {error}")
        return

    section("4. Filling the gaps")
    model = load_model()
    filled = categorize_unmatched(transactions, model)
    print(f"rows the model labelled that rules missed : {filled}")
    for txn in transactions:
        if txn["category_source"] == "model":
            print(f"   {txn['normalized_description'][:45]:45} -> "
                  f"{txn['category']}  ({txn['confidence']})")

    section("5. Final category spread")
    for category, count in Counter(t["category"] for t in transactions).most_common():
        print(f"   {category:16} {count:4}")

    section("6. Anomalies")
    flagged = detect_anomalies(transactions)
    print(f"flagged: {len(flagged)}")
    for txn in flagged[:5]:
        print(f"   {txn['date']}  {txn['reason']}")

    print("\nDone.")


if __name__ == "__main__":
    main()
