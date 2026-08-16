"""Question parsing (Phase 4).

The parser matches keywords; it does not read language. So the tests worth
having are of two kinds: the shapes it must get right, and — more importantly —
the questions it must *refuse* rather than answer from a plausible-looking but
wrong query.
"""

import datetime as dt

from app.pipeline.s10g_assistant import EXAMPLES, parse_question

TODAY = dt.date(2026, 8, 15)


def plan(question, today=TODAY):
    return parse_question(question, today=today)


# --- refusals --------------------------------------------------------------


def test_a_question_it_cannot_parse_is_refused_not_guessed():
    result = plan("what should I invest in?")
    assert result["understood"] is False
    assert "intent" not in result or result.get("intent") is None
    assert result["examples"]


def test_the_refusal_says_it_matches_keywords_rather_than_reading():
    """Someone who knows why it failed can rephrase. Someone told 'sorry'
    cannot."""
    assert "keyword" in plan("explain my finances philosophically")["reason"].lower()


def test_an_empty_question_is_refused_politely():
    assert plan("")["understood"] is False
    assert plan("   ")["understood"] is False


def test_every_offered_example_actually_parses():
    """An example that does not work is worse than no example."""
    for question in EXAMPLES:
        assert plan(question)["understood"] is True, question


# --- intents ---------------------------------------------------------------


def test_spending_questions():
    for question in ("how much did I spend?", "what did I spend last month",
                     "total expenses", "how much have I paid out"):
        assert plan(question)["intent"] == "total_spend", question


def test_income_questions():
    for question in ("how much did I earn?", "what was my income",
                     "how much salary came in"):
        assert plan(question)["intent"] == "total_income", question


def test_a_biggest_category_question_beats_the_generic_how_much():
    """'How much is my biggest category' contains both triggers."""
    assert plan("what is my biggest category?")["intent"] == "top_categories"
    assert plan("how much is my biggest category")["intent"] == "top_categories"


def test_merchant_questions():
    for question in ("who do I pay the most?", "which merchant takes the most",
                     "top merchants"):
        assert plan(question)["intent"] == "top_merchants", question


def test_largest_transaction_is_not_confused_with_largest_category():
    assert plan("what was my largest transaction?")["intent"] == "largest_transaction"
    assert plan("biggest payment I made")["intent"] == "largest_transaction"
    assert plan("my biggest category")["intent"] == "top_categories"


def test_counting_and_averaging():
    assert plan("how many transactions do I have?")["intent"] == "transaction_count"
    assert plan("what do I spend on average")["intent"] == "average_spend"
    assert plan("average monthly spending")["intent"] == "average_spend"


# --- categories ------------------------------------------------------------


def test_a_category_is_recognised_by_name_and_by_synonym():
    assert plan("how much did I spend on food")["category"] == "food"
    assert plan("how much on restaurants")["category"] == "food"
    assert plan("what did I spend on medicine")["category"] == "health"
    assert plan("spending on petrol")["category"] == "transport"


def test_the_longer_phrase_wins():
    """'water bill' and 'bills' both match; the answer must not depend on
    dictionary ordering."""
    assert plan("how much was my water bill")["category"] == "bills_utilities"


def test_a_question_with_no_category_has_none():
    assert plan("how much did I spend last month")["category"] is None


def test_asking_about_income_does_not_narrow_to_the_income_category():
    """Salary rows are credits; some carry other categories. Filtering to the
    'income' category would silently drop them."""
    result = plan("how much salary did I earn")
    assert result["intent"] == "total_income"
    assert result["category"] is None


# --- periods ---------------------------------------------------------------


def test_last_month_and_this_month():
    assert plan("how much did I spend last month")["month"] == "2026-07"
    assert plan("how much did I spend this month")["month"] == "2026-08"


def test_last_month_crosses_the_year_boundary():
    result = parse_question("spending last month", today=dt.date(2026, 1, 9))
    assert result["month"] == "2025-12"


def test_a_named_month_means_the_most_recent_one_that_happened():
    """Asked in August, 'June' is this June; 'October' is last October."""
    assert plan("how much did I spend in June")["month"] == "2026-06"
    assert plan("how much did I spend in October")["month"] == "2025-10"


def test_a_named_month_with_a_year_is_taken_literally():
    assert plan("how much did I spend in June 2024")["month"] == "2024-06"


def test_an_explicit_month_key_is_accepted():
    assert plan("spending in 2026-03")["month"] == "2026-03"


def test_a_bare_year_is_a_year_not_a_month():
    result = plan("how much did I spend in 2025")
    assert result["month"] is None
    assert result["year"] == 2025


def test_this_year_resolves_to_the_current_one():
    assert plan("how much did I earn this year")["year"] == 2026


def test_no_period_means_all_data():
    result = plan("how much did I spend")
    assert result["month"] is None and result["year"] is None
    assert "all your data" in result["explanation"]


# --- the explanation -------------------------------------------------------


def test_every_understood_question_explains_what_it_will_count():
    """The commonest failure of an interface like this is answering a
    different question well. The explanation is what makes that visible."""
    for question in EXAMPLES:
        result = plan(question)
        assert result["explanation"]
        assert len(result["explanation"]) > 20


def test_the_explanation_names_the_category_and_the_period():
    explanation = plan("how much did I spend on food in June")["explanation"]
    assert "food" in explanation
    assert "2026-06" in explanation


def test_the_spending_explanation_says_transfers_are_excluded():
    assert "transfer" in plan("how much did I spend")["explanation"].lower()
