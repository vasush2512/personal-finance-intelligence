"""User-written rules and bank accounts.

The rule that matters most here: applying a rule must never overwrite a
category the user set by hand. A correction is the strongest evidence in the
database, and a rule written afterwards silently undoing it would be the worst
kind of bug — invisible, and about someone's money.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s01_constants import SOURCE_NONE, SOURCE_RULE, SOURCE_USER
from app.core.s03_db import Base
from app.core.s04_models import Transaction, Upload, User
from app.pipeline.s08_rules import categorize_by_rules, match_user_rules
from app.store.s11a_rules import (
    RuleError,
    apply_rule,
    create_rule,
    delete_rule,
    list_rules,
    preview_rule,
    update_rule,
)
from app.store.s15b_accounts_store import (
    AccountError,
    assign_upload,
    create_account,
    delete_account,
    list_accounts,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as open_session:
        yield open_session
    engine.dispose()


@pytest.fixture
def user(session):
    account = User(email="a@example.com", display_name="A", password_hash="x")
    session.add(account)
    session.commit()
    return account


def add(session, user, description, category="other", source=SOURCE_NONE,
        account_id=None, upload_id=None, counter=[0]):
    counter[0] += 1
    row = Transaction(
        user_id=user.id,
        account_id=account_id,
        upload_id=upload_id,
        date=dt.date(2026, 6, 1),
        description=description.upper(),
        normalized_description=description.lower(),
        amount=Decimal("450.00"),
        direction="debit",
        category=category,
        category_source=source,
        fingerprint=f"fp-{counter[0]}",
    )
    session.add(row)
    session.commit()
    return row


# --- matching --------------------------------------------------------------


def test_a_user_rule_beats_the_built_in_one():
    """Someone's rule about their own bank's narrations is better evidence
    than a general pattern shipped with the app."""
    assert categorize_by_rules("swiggy order") == "food"
    assert categorize_by_rules("swiggy order", [("swiggy", "shopping")]) == "shopping"


def test_rules_are_tried_in_order():
    rules = [("blinkit express", "groceries"), ("blinkit", "shopping")]
    assert match_user_rules("upi blinkit express payment", rules) == "groceries"


def test_matching_is_case_insensitive_and_a_substring():
    assert match_user_rules("upi/dr/BLINKIT/hdfc", [("blinkit", "groceries")]) == "groceries"


def test_no_match_falls_through_to_the_built_in_rules():
    assert categorize_by_rules("salary techcadd", [("netflix", "entertainment")]) == "income"


def test_a_keyword_that_matches_nothing_changes_nothing():
    assert match_user_rules("swiggy order", [("netflix", "entertainment")]) is None


# --- storing rules ---------------------------------------------------------


def test_a_rule_is_stored_and_listed(session, user):
    create_rule(session, user.id, "blinkit", "groceries")
    rules = list_rules(session, user.id)
    assert [(r.keyword, r.category) for r in rules] == [("blinkit", "groceries")]


def test_a_one_letter_keyword_is_refused(session, user):
    """It would match almost every transaction in the database."""
    with pytest.raises(RuleError, match="two characters"):
        create_rule(session, user.id, "b", "groceries")


def test_an_unknown_category_is_refused(session, user):
    with pytest.raises(RuleError, match="Unknown category"):
        create_rule(session, user.id, "blinkit", "not-a-category")


def test_the_same_keyword_twice_is_refused_with_the_existing_answer(session, user):
    create_rule(session, user.id, "blinkit", "groceries")
    with pytest.raises(RuleError, match="groceries"):
        create_rule(session, user.id, "blinkit", "shopping")


def test_a_rule_can_be_turned_off_without_losing_its_wording(session, user):
    rule = create_rule(session, user.id, "blinkit", "groceries")
    update_rule(session, user.id, rule.id, active=False)
    assert list_rules(session, user.id)[0].active is False
    assert list_rules(session, user.id)[0].keyword == "blinkit"


def test_one_user_cannot_touch_another_users_rule(session, user):
    other = User(email="b@example.com", display_name="B", password_hash="x")
    session.add(other)
    session.commit()

    rule = create_rule(session, user.id, "blinkit", "groceries")
    assert update_rule(session, other.id, rule.id, category="food") is None
    assert delete_rule(session, other.id, rule.id) is False
    assert list_rules(session, other.id) == []


# --- applying rules --------------------------------------------------------


def test_preview_counts_without_changing_anything(session, user):
    add(session, user, "upi blinkit groceries")
    add(session, user, "upi blinkit again")

    preview = preview_rule(session, user.id, "blinkit")
    assert preview["matches"] == 2
    assert len(preview["samples"]) == 2
    # Nothing was written.
    assert {row.category for row in session.query(Transaction).all()} == {"other"}


def test_applying_a_rule_relabels_the_uncategorised(session, user):
    add(session, user, "upi blinkit groceries")
    rule = create_rule(session, user.id, "blinkit", "groceries")

    assert apply_rule(session, user.id, rule.id) == 1
    row = session.query(Transaction).one()
    assert row.category == "groceries"
    assert row.category_source == SOURCE_RULE


def test_applying_a_rule_never_overwrites_a_hand_correction(session, user):
    """The most important test in this file."""
    corrected = add(session, user, "upi blinkit groceries",
                    category="shopping", source=SOURCE_USER)
    rule = create_rule(session, user.id, "blinkit", "groceries")

    assert apply_rule(session, user.id, rule.id, only_uncategorised=False) == 0
    session.refresh(corrected)
    assert corrected.category == "shopping"
    assert corrected.category_source == SOURCE_USER


def test_by_default_a_rule_leaves_already_categorised_rows_alone(session, user):
    already = add(session, user, "upi blinkit x", category="food", source=SOURCE_RULE)
    rule = create_rule(session, user.id, "blinkit", "groceries")

    assert apply_rule(session, user.id, rule.id) == 0
    session.refresh(already)
    assert already.category == "food"

    # Asked explicitly, it does take them over.
    assert apply_rule(session, user.id, rule.id, only_uncategorised=False) == 1
    session.refresh(already)
    assert already.category == "groceries"


def test_deleting_a_rule_leaves_the_categories_it_applied(session, user):
    """Reverting thousands of rows would be a far bigger surprise."""
    add(session, user, "upi blinkit groceries")
    rule = create_rule(session, user.id, "blinkit", "groceries")
    apply_rule(session, user.id, rule.id)

    assert delete_rule(session, user.id, rule.id) is True
    assert session.query(Transaction).one().category == "groceries"


def test_a_rule_only_ever_touches_its_owners_rows(session, user):
    other = User(email="b@example.com", display_name="B", password_hash="x")
    session.add(other)
    session.commit()
    theirs = add(session, other, "upi blinkit groceries")

    rule = create_rule(session, user.id, "blinkit", "groceries")
    assert apply_rule(session, user.id, rule.id) == 0
    session.refresh(theirs)
    assert theirs.category == "other"


# --- accounts --------------------------------------------------------------


def test_an_account_is_created_and_counted(session, user):
    account = create_account(session, user.id, "HDFC Salary", bank="HDFC")
    add(session, user, "swiggy", account_id=account.id)

    listed = list_accounts(session, user.id)
    assert listed[0]["name"] == "HDFC Salary"
    assert listed[0]["transaction_count"] == 1


def test_only_the_last_four_digits_are_kept(session, user):
    """A full account number has no use anywhere in this app."""
    account = create_account(session, user.id, "SBI", last4="123456789012")
    assert account.last4 == "9012"


def test_a_duplicate_account_name_is_refused(session, user):
    create_account(session, user.id, "HDFC")
    with pytest.raises(AccountError, match="already have"):
        create_account(session, user.id, "HDFC")


def test_rows_with_no_account_appear_as_unassigned(session, user):
    add(session, user, "old statement row")
    listed = list_accounts(session, user.id)

    unassigned = [entry for entry in listed if entry["id"] is None]
    assert unassigned and unassigned[0]["transaction_count"] == 1


def test_deleting_an_account_keeps_its_transactions(session, user):
    """Deleting a label must not delete a year of financial records."""
    account = create_account(session, user.id, "HDFC")
    row = add(session, user, "swiggy", account_id=account.id)

    result = delete_account(session, user.id, account.id)
    assert result["transactions_unassigned"] == 1

    session.refresh(row)
    assert row.account_id is None
    assert session.query(Transaction).count() == 1


def test_assigning_a_statement_moves_every_row_it_imported(session, user):
    upload = Upload(user_id=user.id, filename="hdfc.csv")
    session.add(upload)
    session.commit()

    add(session, user, "row one", upload_id=upload.id)
    add(session, user, "row two", upload_id=upload.id)
    account = create_account(session, user.id, "HDFC")

    result = assign_upload(session, user.id, upload.id, account.id)
    assert result["moved"] == 2
    assert {row.account_id for row in session.query(Transaction).all()} == {account.id}
    assert session.get(Upload, upload.id).account_id == account.id


def test_one_user_cannot_assign_into_another_users_account(session, user):
    other = User(email="b@example.com", display_name="B", password_hash="x")
    session.add(other)
    session.commit()
    theirs = create_account(session, other.id, "Theirs")

    upload = Upload(user_id=user.id, filename="mine.csv")
    session.add(upload)
    session.commit()

    assert assign_upload(session, user.id, upload.id, theirs.id) is None
