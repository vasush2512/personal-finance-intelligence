"""Single source of truth for categories and the keyword rules.

Nothing else in the codebase should hardcode a category name.
"""

CATEGORIES = [
    "food",
    "groceries",
    "transport",
    "shopping",
    "bills_utilities",
    "rent",
    "entertainment",
    "health",
    "education",
    "transfer",
    "income",
    "refund",
    "other",
]

UNCATEGORIZED = "other"

# How a transaction entered the system.
#
# A statement row and a manual row are the same kind of thing — one
# Transaction table, one set of analytics — and this only records where it
# came from, so the user can filter by it and so an edit knows what it is
# allowed to touch.
#
# NULL in the database is read as ENTRY_STATEMENT: every row that existed
# before manual entry was possible came from a statement, and rewriting a
# hundred thousand rows to say so would be changing data to record something
# its absence already tells you.
ENTRY_STATEMENT = "statement"
ENTRY_MANUAL = "manual"
ENTRY_SOURCES = [ENTRY_STATEMENT, ENTRY_MANUAL]

# Where money moved, for a manual entry. Statement rows derive this from the
# narration instead — see extract_payment_method.
PAYMENT_METHODS = [
    "Cash", "UPI", "Card", "Credit Card", "Debit Card", "Net banking",
    "NEFT", "IMPS", "Wallet", "Cheque", "Auto-debit", "Other",
]

# The prefix every user-defined category key carries, so a user category can
# never collide with a built-in one and the two are always tellable apart.
USER_CATEGORY_PREFIX = "u_"


def is_user_category(category: str) -> bool:
    return bool(category) and category.startswith(USER_CATEGORY_PREFIX)

# Money coming back, not money earned.
#
# A refund used to be labelled "income", which quietly inflated earnings: buy a
# ₹5,000 phone, return it, and the statement showed ₹5,000 of income you never
# earned — along with a savings rate, a health score and an income forecast all
# built on it.
#
# It is deliberately NOT netted off the spending total either. Matching a
# refund to the purchase it reverses needs a merchant, an amount and a date
# window that frequently do not line up, and a total that is silently wrong is
# worse than one that is visibly separate. Refunds are excluded from income,
# reported in their own category, and left for the reader to net themselves.
REFUND = "refund"

# Who decided a transaction's category.
#
# These live here for the same reason the category names do: they are a
# vocabulary the database, the API and the UI all have to agree on, and three
# copies of a string literal is three places for them to disagree.
#
# NONE is the honest answer for a row no rule matched and the model either
# never saw or was not confident enough to label. It used to be recorded as
# RULE, which made the rules look like they covered every row imported —
# the coverage figure on the model page counted its own failures as successes.
SOURCE_RULE = "rule"
SOURCE_MODEL = "model"
SOURCE_USER = "user"
SOURCE_NONE = "none"

# Display order: the labellers that did something, then the rows nothing could.
CATEGORY_SOURCES = [SOURCE_RULE, SOURCE_MODEL, SOURCE_USER, SOURCE_NONE]

# The sources whose labels are worth training on. A model row is excluded
# because training on the model's own output teaches it nothing, and a NONE row
# has no label to learn from.
TRAINABLE_SOURCES = (SOURCE_RULE, SOURCE_USER)

# Ordered list of (regex pattern, category).
# Order matters: the first pattern that matches wins, so put specific
# merchants above generic words. Patterns are matched against the
# NORMALIZED description (see services/normalize.py), which is lowercase
# and stripped of UPI/NEFT prefixes and reference numbers.
KEYWORD_RULES = [
    # --- income (check before generic transfer words) ---
    (r"\bsalary\b|\bsal cr\b|\bpayroll\b", "income"),
    (r"\binterest (credit|paid)\b|\bint\.?cr\b", "income"),
    # Money coming back, not money earned — see REFUND above for why this is
    # its own category rather than income.
    (r"\brefund\b|\bcashback\b|\breversal\b|\bchargeback\b", "refund"),
    (r"\bdividend\b", "income"),

    # --- rent ---
    (r"\brent\b|\bhouse rent\b|\blandlord\b|\bpg rent\b", "rent"),

    # --- food & dining ---
    (r"\bswiggy\b|\bzomato\b|\bdunzo food\b|\beatsure\b|\bbox8\b", "food"),
    (r"\bdominos\b|\bpizza hut\b|\bkfc\b|\bmcdonald|\bburger king\b|\bsubway\b", "food"),
    (r"\bstarbucks\b|\bccd\b|\bcafe coffee\b|\bchaayos\b|\bchai point\b", "food"),
    (r"\bcafe\b|\brestaurant\b|\bdhaba\b|\bbakery\b|\bsweets\b|\bbiryani\b", "food"),
    (r"\bhotel .*(food|dining)\b|\bfoodcourt\b|\bcanteen\b", "food"),

    # --- groceries ---
    (r"\bblinkit\b|\bzepto\b|\bbigbasket\b|\bgrofers\b|\binstamart\b", "groceries"),
    (r"\bdmart\b|\bd mart\b|\breliance fresh\b|\bmore supermarket\b|\bspencer", "groceries"),
    (r"\bkirana\b|\bgeneral store\b|\bsupermarket\b|\bprovision\b|\bvegetable", "groceries"),
    (r"\bmilk\b|\bamul\b|\bmother dairy\b|\bdairy\b", "groceries"),

    # --- transport ---
    (r"\buber\b|\bola\b|\brapido\b|\bblusmart\b", "transport"),
    (r"\birctc\b|\bredbus\b|\bindigo\b|\bspicejet\b|\bair india\b|\bvistara\b", "transport"),
    (r"\bpetrol\b|\bfuel\b|\bhpcl\b|\biocl\b|\bbpcl\b|\bindian oil\b|\bshell\b", "transport"),
    (r"\bfastag\b|\btoll\b|\bparking\b|\bmetro\b|\bdmrc\b|\bbmtc\b|\brto\b", "transport"),

    # --- shopping ---
    (r"\bamazon\b|\bflipkart\b|\bmyntra\b|\bajio\b|\bmeesho\b|\bnykaa\b", "shopping"),
    (r"\bdecathlon\b|\bcroma\b|\breliance digital\b|\bibell\b|\bzudio\b|\bmax fashion\b", "shopping"),
    (r"\bshoppers stop\b|\blifestyle\b|\bpantaloons\b|\btrends\b|\bstore\b", "shopping"),

    # --- bills & utilities ---
    (r"\bjio\b|\bairtel\b|\bvodafone\b|\bvi recharge\b|\bbsnl\b|\brecharge\b", "bills_utilities"),
    (r"\bbroadband\b|\bwifi\b|\bact fibernet\b|\bhathway\b", "bills_utilities"),
    (r"\belectricity\b|\bpspcl\b|\bbescom\b|\bmseb\b|\btorrent power\b|\bpower bill\b", "bills_utilities"),
    (r"\bgas bill\b|\bindane\b|\bhp gas\b|\bwater bill\b|\bmunicipal\b", "bills_utilities"),
    (r"\binsurance\b|\blic\b|\bpremium\b", "bills_utilities"),

    # --- entertainment ---
    (r"\bnetflix\b|\bspotify\b|\bhotstar\b|\bprime video\b|\bsonyliv\b|\bzee5\b", "entertainment"),
    (r"\bbookmyshow\b|\bpvr\b|\binox\b|\bcinema\b|\bcineplex\b", "entertainment"),
    (r"\bsteam\b|\bplaystation\b|\bxbox\b|\bgaming\b", "entertainment"),

    # --- health ---
    (r"\bapollo\b|\bpharmeasy\b|\b1mg\b|\bnetmeds\b|\bmedplus\b|\bwellness forever\b", "health"),
    (r"\bpharmacy\b|\bchemist\b|\bmedical\b|\bhospital\b|\bclinic\b|\bdiagnostic", "health"),
    (r"\bdental\b|\bpathlab\b|\blab test\b|\bgym\b|\bfitness\b|\bcult\b", "health"),

    # --- education ---
    (r"\bbyju|\bunacademy\b|\bvedantu\b|\bphysicswallah\b|\bpw\b", "education"),
    (r"\bcoursera\b|\budemy\b|\bupgrad\b|\bscaler\b|\bgreat learning\b", "education"),
    (r"\bcollege\b|\buniversity\b|\bschool fee\b|\btuition\b|\bexam fee\b|\bhostel fee\b", "education"),
    (r"\bbook (store|house)\b|\bstationery\b", "education"),

    # --- transfers (last: these words are generic) ---
    (r"\bself transfer\b|\bown account\b|\bto self\b", "transfer"),
    (r"\batm (wdl|withdrawal|cash)\b|\bcash wdl\b|\bcash withdrawal\b", "transfer"),
]
