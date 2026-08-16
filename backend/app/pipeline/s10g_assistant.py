"""Turning a typed question into a query this app can actually run.

**This is pattern matching, not a language model.** It recognises a fixed set of
question shapes by keyword and regular expression, and maps them onto the same
filters the Transactions page uses. Nothing is generated, nothing is inferred
beyond what is written here, and there is no model behind it.

That distinction is the whole design. A question this cannot parse returns
`understood=False` and says what it does understand — it never guesses at an
intent and answers confidently from the wrong query. An assistant that answers
everything is indistinguishable from one that answers nothing, because you
cannot tell which replies to trust.

The parser returns a *plan*: an intent plus filters. Running it is the store
layer's job (s12e_assistant), so the mapping from words to query can be tested
without a database, and the query that gets run can be shown to the user
alongside the answer.
"""

import datetime as dt
import re

from app.core.s01_constants import CATEGORIES

# Every intent this understands. Anything else is honestly refused.
INTENTS = (
    "total_spend",
    "total_income",
    "transaction_count",
    "top_categories",
    "top_merchants",
    "largest_transaction",
    "average_spend",
)

# Words that mean a category, beyond the category name itself. Kept explicit
# rather than fuzzy-matched: "medicine" should find health, but "medium"
# should not, and a similarity threshold cannot tell those apart reliably.
_CATEGORY_WORDS = {
    "food": ["food", "eating out", "restaurant", "restaurants", "dining", "swiggy", "zomato"],
    "groceries": ["groceries", "grocery", "supermarket", "vegetables"],
    "transport": ["transport", "travel", "fuel", "petrol", "cab", "cabs", "uber", "ola", "commute"],
    "shopping": ["shopping", "clothes", "amazon", "flipkart", "myntra"],
    "bills_utilities": ["bills", "utilities", "electricity", "water bill", "recharge", "broadband", "internet"],
    "rent": ["rent", "landlord"],
    "entertainment": ["entertainment", "movies", "netflix", "subscriptions", "cinema"],
    "health": ["health", "medical", "medicine", "doctor", "hospital", "pharmacy"],
    "education": ["education", "tuition", "course", "courses", "school", "college"],
    "transfer": ["transfer", "transfers"],
    "income": ["income", "salary", "earned", "earnings"],
    "other": ["other", "uncategorised", "uncategorized"],
}

_MONTH_NAMES = {
    "january": 1, "jan": 1, "february": 2, "feb": 2, "march": 3, "mar": 3,
    "april": 4, "apr": 4, "may": 5, "june": 6, "jun": 6, "july": 7, "jul": 7,
    "august": 8, "aug": 8, "september": 9, "sep": 9, "sept": 9,
    "october": 10, "oct": 10, "november": 11, "nov": 11, "december": 12, "dec": 12,
}

# What the UI offers when it cannot parse something. Real questions, so they
# can be clicked and will work.
EXAMPLES = [
    "How much did I spend last month?",
    "How much did I spend on food in June?",
    "What is my biggest category?",
    "Who do I pay the most?",
    "What was my largest transaction?",
    "How many transactions do I have?",
    "How much did I earn this year?",
]


def _find_category(text):
    """The category a question is about, or None.

    Longest phrase first, so "water bill" is matched before "bills" and
    lands on the same category either way rather than by luck of ordering.
    """
    matches = []
    for category, words in _CATEGORY_WORDS.items():
        for word in words:
            if re.search(rf"\b{re.escape(word)}\b", text):
                matches.append((len(word), category))

    if not matches:
        return None
    return max(matches)[1]


def _find_month(text, today):
    """A specific month, as YYYY-MM, or None for all time.

    Handles "June", "June 2025", "2026-06", "last month" and "this month".
    A bare month name means the most recent one that has already happened —
    asking about "June" in August means this June, not next.
    """
    if re.search(r"\blast month\b", text):
        first = today.replace(day=1)
        previous = first - dt.timedelta(days=1)
        return f"{previous.year:04d}-{previous.month:02d}"

    if re.search(r"\bthis month\b", text):
        return f"{today.year:04d}-{today.month:02d}"

    explicit = re.search(r"\b(20\d{2})-(0[1-9]|1[0-2])\b", text)
    if explicit:
        return explicit.group(0)

    for name, number in _MONTH_NAMES.items():
        if not re.search(rf"\b{name}\b", text):
            continue

        year_match = re.search(rf"\b{name}\s+(20\d{{2}})\b", text)
        if year_match:
            year = int(year_match.group(1))
        else:
            # No year given: the most recent occurrence that has happened.
            year = today.year if number <= today.month else today.year - 1
        return f"{year:04d}-{number:02d}"

    return None


def _find_year(text):
    """A bare year, when no month was named. 'this year' resolves upstream."""
    match = re.search(r"\b(20\d{2})\b", text)
    return int(match.group(1)) if match else None


def _find_intent(text):
    """Which question shape this is, or None."""
    # Order matters: "biggest category" must beat the generic "how much".
    if re.search(r"\b(biggest|top|largest|main|most)\b.*\bcategor", text):
        return "top_categories"
    if re.search(r"\bcategor\w*\b.*\b(biggest|most|top)\b", text):
        return "top_categories"

    # Plurals matter here: "top merchants" is the commonest phrasing of this
    # question, and \bmerchant\b does not match it.
    if re.search(r"\b(who|where|which merchant|what merchant)\b", text) or re.search(
        r"\b(top|biggest|most)\b.*\b(merchants?|shops?|stores?|pay)\b", text
    ):
        return "top_merchants"

    if re.search(r"\b(largest|biggest|highest|most expensive)\b.*\b(transaction|payment|purchase|expense)\b", text):
        return "largest_transaction"

    if re.search(r"\bhow many\b|\bnumber of\b|\bcount\b", text):
        return "transaction_count"

    if re.search(r"\baverage\b|\btypical\b|\bper month\b|\bmonthly\b", text):
        return "average_spend"

    if re.search(r"\b(earn|earned|income|salary|receive|received|came in)\b", text):
        return "total_income"

    if re.search(r"\b(spend|spent|spending|cost|paid|pay|expense|expenses|went out)\b", text):
        return "total_spend"

    if re.search(r"\bhow much\b", text):
        return "total_spend"

    return None


def parse_question(question, today=None):
    """A typed question -> a plan this app can run, or an honest refusal.

    The returned plan carries `explanation`, a plain sentence naming exactly
    what will be counted. The UI shows it beside the answer, so a
    misunderstanding is visible rather than silent — the commonest failure of
    a natural-language interface is answering a different question well.
    """
    today = today or dt.date.today()
    text = (question or "").lower().strip()

    if not text:
        return {
            "understood": False,
            "question": question or "",
            "reason": "Ask a question about your transactions.",
            "examples": EXAMPLES,
        }

    intent = _find_intent(text)
    if intent is None:
        return {
            "understood": False,
            "question": question,
            "reason": (
                "This only recognises a fixed set of question shapes — it "
                "matches keywords rather than reading language, so it cannot "
                "work out what this one is asking."
            ),
            "examples": EXAMPLES,
        }

    category = _find_category(text)
    month = _find_month(text, today)

    year = None
    if month is None:
        if re.search(r"\bthis year\b", text):
            year = today.year
        else:
            year = _find_year(text)

    # "How much did I earn" is about credits, so a category of 'income' adds
    # nothing and would wrongly exclude salary rows labelled anything else.
    if intent == "total_income" and category == "income":
        category = None

    return {
        "understood": True,
        "question": question,
        "intent": intent,
        "category": category,
        "month": month,
        "year": year,
        "explanation": _explain(intent, category, month, year),
    }


def _period(month, year):
    if month:
        return f"in {month}"
    if year:
        return f"in {year}"
    return "across all your data"


def _explain(intent, category, month, year):
    """The sentence shown beside the answer, naming what was counted."""
    period = _period(month, year)
    scope = f" in {category.replace('_', ' ')}" if category else ""

    sentences = {
        "total_spend": f"Total of every debit{scope}, {period}, excluding transfers.",
        "total_income": f"Total of every credit, {period}.",
        "transaction_count": f"Number of transactions{scope}, {period}.",
        "top_categories": f"Spending by category, largest first, {period}.",
        "top_merchants": f"Spending by merchant, largest first, {period}.",
        "largest_transaction": f"The single biggest debit{scope}, {period}.",
        "average_spend": f"Total spending{scope} {period}, divided by the months it covers.",
    }
    return sentences[intent]
