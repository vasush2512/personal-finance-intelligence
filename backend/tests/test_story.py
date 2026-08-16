"""The monthly story (Phase 3).

Templates over figures that were already computed, so this needs no database.
What is worth testing is what the sentences claim, and what they refuse to.
"""

from app.pipeline.s10f_story import build_story, month_title

SUMMARY = {
    "total_spent": "50000.00",
    "total_income": "80000.00",
    "transaction_count": 57,
    "by_category": [
        {"category": "food", "total": "20000.00", "count": 40},
        {"category": "rent", "total": "18000.00", "count": 2},
        {"category": "transport", "total": "7000.00", "count": 15},
    ],
}

ANOMALIES = [
    {"id": 1, "amount": "18000.00", "description": "X", "category": "shopping"},
    {"id": 2, "amount": "8116.00", "description": "Y", "category": "health"},
]

RECURRING = [
    {"merchant": "Netflix", "average_amount": "649.00"},
    {"merchant": "Gym", "average_amount": "1840.00"},
]


def story_text(*args, **kwargs):
    return " ".join(build_story(*args, **kwargs)["paragraphs"])


def test_a_month_is_named_the_way_a_person_says_it():
    assert month_title("2026-07") == "July 2026"


def test_the_opening_states_in_out_and_what_was_left():
    text = story_text("2026-07", SUMMARY)
    assert "Rs 80,000 came in" in text
    assert "Rs 50,000 went out" in text
    assert "Rs 30,000" in text and "38%" in text


def test_spending_more_than_came_in_is_said_plainly():
    summary = {**SUMMARY, "total_spent": "95000.00"}
    text = story_text("2026-07", summary)
    assert "more than came in" in text
    assert "Rs 15,000" in text


def test_the_biggest_categories_are_named_with_their_share():
    text = story_text("2026-07", SUMMARY)
    assert "Food" in text and "Rent" in text and "Transport" in text
    assert "90%" in text  # 45,000 of 50,000


def test_a_first_month_gets_no_comparison_paragraph():
    """There is nothing to compare against, so nothing is claimed."""
    text = story_text("2026-07", SUMMARY, previous=None)
    assert "than in" not in text


def test_a_rise_is_reported_against_the_named_month():
    previous = {"month": "2026-06", "spent": "40000.00"}
    text = story_text("2026-07", SUMMARY, previous=previous)
    assert "25% more than in June 2026" in text


def test_a_change_too_small_to_matter_is_called_about_the_same():
    previous = {"month": "2026-06", "spent": "49000.00"}
    text = story_text("2026-07", SUMMARY, previous=previous)
    assert "about the same" in text


def test_flagged_transactions_are_never_called_wrong():
    text = story_text("2026-07", SUMMARY, anomalies=ANOMALIES)
    assert "2 transactions stood out" in text
    assert "not a sign anything is wrong" in text
    for banned in ("fraud", "fraudulent", "suspicious", "definitely"):
        assert banned not in text.lower()


def test_commitments_are_described_as_a_typical_month():
    text = story_text("2026-07", SUMMARY, recurring=RECURRING)
    assert "2 recurring payments" in text
    assert "Rs 2,489" in text


def test_a_month_with_nothing_in_it_says_so():
    empty = {"total_spent": "0.00", "total_income": "0.00", "transaction_count": 0,
             "by_category": []}
    story = build_story("2026-07", empty)
    assert story["available"] is False
    assert "July 2026" in story["reason"]
    assert story["paragraphs"] == []


def test_the_story_never_gives_advice():
    text = story_text("2026-07", SUMMARY,
                      previous={"month": "2026-06", "spent": "40000.00"},
                      anomalies=ANOMALIES, recurring=RECURRING).lower()
    for banned in ("you should", "try to", "consider ", "we recommend", "cut back"):
        assert banned not in text
