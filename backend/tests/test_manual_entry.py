"""Manually entered transactions, user categories and tags.

The theme running through these: a manual entry is an ORDINARY transaction.
Most of what is tested here is that it behaves like one — it lands in the same
totals, obeys the same ownership, and is protected by the same rules about
never overwriting a person's own decision.
"""

import datetime as dt
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.core.s01_constants import (
    ENTRY_MANUAL,
    SOURCE_MODEL,
    SOURCE_NONE,
    SOURCE_RULE,
    SOURCE_USER,
)
from app.core.s03_db import Base
from app.core.s04_models import Transaction, User
from app.pipeline.s10h_manual import InvalidEntry, build_manual_transaction
from app.store import s12_aggregations as aggregations
from app.store.s11b_categories import (
    CategoryError,
    create_category,
    delete_category,
    list_categories,
    update_category,
    valid_categories,
)
from app.store.s11c_tags import (
    TagError,
    clean_name,
    delete_tag,
    list_tags,
    set_tags,
    tags_for,
    transaction_ids_with_tag,
)
from app.store.s11d_manual import (
    create_manual,
    delete_manual,
    manual_summary,
    suggest_category,
    update_manual,
)
from app.store.s15b_accounts_store import create_account

TODAY = dt.date(2026, 8, 16)


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


@pytest.fixture
def other(session):
    account = User(email="b@example.com", display_name="B", password_hash="x")
    session.add(account)
    session.commit()
    return account


def add_manual(session, user, **overrides):
    fields = {
        "amount": "250.00", "date": TODAY, "direction": "expense",
        "merchant": "Swiggy", "today": TODAY,
    }
    fields.update(overrides)
    return create_manual(session, user.id, **fields)


# --- validation ------------------------------------------------------------


def test_an_expense_becomes_an_ordinary_debit(session, user):
    row = add_manual(session, user, amount="250.50", direction="expense")
    assert row.direction == "debit"
    assert row.amount == Decimal("250.50")
    assert row.entry_source == ENTRY_MANUAL


def test_income_becomes_an_ordinary_credit(session, user):
    row = add_manual(session, user, direction="income", merchant="Employer")
    assert row.direction == "credit"


def test_a_negative_amount_is_refused_with_an_explanation(session, user):
    """Sign is carried by the Expense/Income choice, not by a minus."""
    with pytest.raises(InvalidEntry, match="more than zero"):
        add_manual(session, user, amount="-250")


def test_a_future_date_is_refused(session, user):
    with pytest.raises(InvalidEntry, match="future"):
        add_manual(session, user, date=dt.date(2027, 1, 1))


def test_a_nonsense_amount_is_refused(session, user):
    with pytest.raises(InvalidEntry):
        add_manual(session, user, amount="two hundred")


def test_an_unknown_payment_method_is_refused(session, user):
    with pytest.raises(InvalidEntry, match="payment method"):
        add_manual(session, user, payment_method="pigeon")


def test_optional_fields_stay_optional(session, user):
    """Recording ₹100 must not require filling a form."""
    row = create_manual(session, user.id, amount="100", date=TODAY,
                        direction="expense", today=TODAY)
    assert row.amount == Decimal("100.00")
    assert row.notes is None


# --- fingerprints ----------------------------------------------------------


def test_two_identical_entries_on_one_day_are_both_kept(session, user):
    """Two ₹120 coffees are two payments. The import fingerprint would have
    called the second one a duplicate and dropped it."""
    first = add_manual(session, user, amount="120", merchant="Chai Point")
    second = add_manual(session, user, amount="120", merchant="Chai Point")

    assert first.id != second.id
    assert first.fingerprint != second.fingerprint
    assert session.query(Transaction).count() == 2


# --- categorisation --------------------------------------------------------


def test_a_chosen_category_is_recorded_as_the_users_own(session, user):
    row = add_manual(session, user, category="food")
    assert row.category == "food"
    assert row.category_source == SOURCE_USER


def test_a_blank_category_gets_a_suggestion_from_the_existing_rules(session, user):
    row = add_manual(session, user, merchant="Swiggy", category=None)
    assert row.category == "food"
    # Recorded as the rule's answer, not as the user's — they never said it.
    assert row.category_source == SOURCE_RULE


def test_an_unrecognised_merchant_is_left_uncategorised_not_guessed(session, user):
    row = add_manual(session, user, merchant="Xyzzy Traders", category=None)
    assert row.category == "other"
    assert row.category_source == SOURCE_NONE


def test_the_users_choice_beats_the_suggestion(session, user):
    """Swiggy would suggest food. They said shopping. Shopping wins."""
    row = add_manual(session, user, merchant="Swiggy", category="shopping")
    assert row.category == "shopping"
    assert row.category_source == SOURCE_USER


def test_suggestion_returns_nothing_rather_than_guessing(session, user):
    assert suggest_category(session, user.id, "Blinkit") == "groceries"
    assert suggest_category(session, user.id, "Xyzzy Traders") is None
    assert suggest_category(session, user.id, "") is None


# --- merchant --------------------------------------------------------------


def test_a_typed_merchant_is_kept_exactly_as_written(session, user):
    """Normalisation exists to decode bank narrations. A name a person typed
    is already the answer it would be trying to reach."""
    row = add_manual(session, user, merchant="Ramu Chai Stall")
    assert row.merchant_name == "Ramu Chai Stall"
    assert row.merchant == "Ramu Chai Stall"


def test_an_imported_row_still_derives_its_merchant(session, user):
    imported = Transaction(
        user_id=user.id, date=TODAY,
        description="UPI/DR/566223197902/BLINKIT/HDFC/blinkit@ybl/Groceries",
        normalized_description="blinkit groceries",
        amount=Decimal("500.00"), direction="debit", category="groceries",
        fingerprint="imported-1",
    )
    session.add(imported)
    session.commit()

    assert imported.merchant_name is None
    assert imported.merchant == "Blinkit"


# --- editing and deleting --------------------------------------------------


def test_a_manual_row_can_be_edited(session, user):
    row = add_manual(session, user, amount="250")
    updated = update_manual(session, user.id, row.id, amount="300",
                            category="food", today=TODAY)

    assert updated.amount == Decimal("300.00")
    assert updated.category == "food"
    assert updated.category_source == SOURCE_USER
    assert updated.updated_at is not None


def test_editing_keeps_the_same_row_and_fingerprint(session, user):
    """A verdict already recorded about this row must keep pointing at it."""
    row = add_manual(session, user)
    fingerprint = row.fingerprint

    updated = update_manual(session, user.id, row.id, amount="999", today=TODAY)
    assert updated.id == row.id
    assert updated.fingerprint == fingerprint


def test_an_edit_cannot_write_what_create_would_have_refused(session, user):
    row = add_manual(session, user)
    with pytest.raises(InvalidEntry):
        update_manual(session, user.id, row.id, amount="-5", today=TODAY)


def test_an_imported_row_cannot_be_edited_here(session, user):
    """Its amount and date came from a bank. This app does not rewrite those."""
    imported = Transaction(
        user_id=user.id, date=TODAY, description="POS SOMETHING",
        normalized_description="something", amount=Decimal("100.00"),
        direction="debit", category="other", fingerprint="imported-2",
    )
    session.add(imported)
    session.commit()

    assert update_manual(session, user.id, imported.id, amount="999") is None
    assert delete_manual(session, user.id, imported.id) is None
    assert session.query(Transaction).count() == 1


def test_a_manual_row_can_be_deleted(session, user):
    row = add_manual(session, user)
    assert delete_manual(session, user.id, row.id)["id"] == row.id
    assert session.query(Transaction).count() == 0


# --- ownership -------------------------------------------------------------


def test_one_user_cannot_touch_anothers_manual_row(session, user, other):
    row = add_manual(session, user)

    assert update_manual(session, other.id, row.id, amount="1") is None
    assert delete_manual(session, other.id, row.id) is None
    session.refresh(row)
    assert row.amount == Decimal("250.00")


def test_a_manual_row_cannot_be_filed_under_someone_elses_account(session, user, other):
    theirs = create_account(session, other.id, "Their HDFC")
    with pytest.raises(CategoryError):
        add_manual(session, user, account_id=theirs.id)


# --- it is an ordinary transaction -----------------------------------------


def test_manual_entries_land_in_the_existing_totals(session, user):
    add_manual(session, user, amount="500", category="food")
    add_manual(session, user, amount="80000", direction="income",
               category="income", merchant="Employer")

    summary = aggregations.summary(session, None, user_id=user.id)
    assert summary["total_spent"] == Decimal("500.00")
    assert summary["total_income"] == Decimal("80000.00")
    assert summary["transaction_count"] == 2


def test_the_source_filter_separates_them_without_a_second_system(session, user):
    add_manual(session, user, amount="500", category="food")
    session.add(Transaction(
        user_id=user.id, date=TODAY, description="POS SHOP",
        normalized_description="shop", amount=Decimal("1500.00"),
        direction="debit", category="shopping", fingerprint="imported-3",
    ))
    session.commit()

    both = aggregations.total_spent(session, None, user_id=user.id)
    manual = aggregations.total_spent(session, None, user_id=user.id,
                                      entry_source="manual")
    statement = aggregations.total_spent(session, None, user_id=user.id,
                                         entry_source="statement")

    assert both == Decimal("2000.00")
    assert manual == Decimal("500.00")
    assert statement == Decimal("1500.00")


def test_a_row_imported_before_manual_entry_existed_counts_as_a_statement(session, user):
    """entry_source is NULL on every pre-existing row. Reading that as
    'not a statement' would hide a hundred thousand transactions."""
    session.add(Transaction(
        user_id=user.id, date=TODAY, description="OLD ROW",
        normalized_description="old row", amount=Decimal("700.00"),
        direction="debit", category="other", fingerprint="legacy-1",
        entry_source=None,
    ))
    session.commit()

    assert aggregations.total_spent(session, None, user_id=user.id,
                                    entry_source="statement") == Decimal("700.00")


# --- user categories -------------------------------------------------------


def test_a_custom_category_can_be_created_and_used(session, user):
    gym = create_category(session, user.id, "Gym", emoji="🏋️")
    assert gym.key == "u_gym"

    row = add_manual(session, user, category=gym.key)
    assert row.category == "u_gym"


def test_renaming_a_category_does_not_move_any_transaction(session, user):
    """Display names are not database keys."""
    gym = create_category(session, user.id, "Gym")
    row = add_manual(session, user, category=gym.key)

    update_category(session, user.id, gym.id, label="Fitness")
    session.refresh(row)

    assert list_categories(session, user.id)[0].label == "Fitness"
    assert row.category == "u_gym"


def test_a_custom_category_cannot_collide_with_a_built_in_one(session, user):
    with pytest.raises(CategoryError, match="built-in"):
        create_category(session, user.id, "Food")


def test_the_same_custom_category_twice_is_refused(session, user):
    create_category(session, user.id, "Gym")
    with pytest.raises(CategoryError, match="already have"):
        create_category(session, user.id, "gym")


def test_one_users_categories_are_invisible_to_another(session, user, other):
    create_category(session, user.id, "Gym")

    assert list_categories(session, other.id) == []
    assert "u_gym" not in valid_categories(session, other.id)
    assert update_category(session, other.id, 1, label="Theirs") is None


def test_a_category_in_use_cannot_simply_be_deleted(session, user):
    gym = create_category(session, user.id, "Gym")
    add_manual(session, user, category=gym.key)

    with pytest.raises(CategoryError, match="used by"):
        delete_category(session, user.id, gym.id)

    assert session.query(Transaction).count() == 1


def test_a_category_in_use_can_be_deleted_by_moving_its_transactions(session, user):
    gym = create_category(session, user.id, "Gym")
    row = add_manual(session, user, category=gym.key)

    result = delete_category(session, user.id, gym.id, move_to="health")
    assert result["moved"] == 1

    session.refresh(row)
    assert row.category == "health"


def test_archiving_keeps_a_category_working_for_existing_rows(session, user):
    gym = create_category(session, user.id, "Gym")
    row = add_manual(session, user, category=gym.key)

    update_category(session, user.id, gym.id, archived=True)

    assert list_categories(session, user.id) == []              # not offered
    assert "u_gym" in valid_categories(session, user.id)        # still valid
    session.refresh(row)
    assert row.category == "u_gym"                              # untouched


def test_an_unknown_category_cannot_be_put_on_a_transaction(session, user):
    with pytest.raises(CategoryError, match="Unknown category"):
        add_manual(session, user, category="u_not_mine")


# --- tags ------------------------------------------------------------------


def test_tags_are_normalised_so_one_tag_is_one_tag():
    assert clean_name("#Delhi Trip!") == "delhi trip"
    assert clean_name("  DELHI trip ") == "delhi trip"


def test_tags_attach_and_detach(session, user):
    row = add_manual(session, user)

    set_tags(session, user.id, row.id, ["#Delhi Trip", "friends"])
    assert tags_for(session, user.id, row.id) == ["delhi trip", "friends"]

    set_tags(session, user.id, row.id, ["friends"])
    assert tags_for(session, user.id, row.id) == ["friends"]


def test_the_same_tag_twice_on_one_row_is_stored_once(session, user):
    row = add_manual(session, user)
    set_tags(session, user.id, row.id, ["trip", "Trip", "#trip"])
    assert tags_for(session, user.id, row.id) == ["trip"]


def test_transactions_can_be_found_by_tag(session, user):
    first = add_manual(session, user, merchant="Hotel")
    add_manual(session, user, merchant="Coffee")
    set_tags(session, user.id, first.id, ["delhi trip"])

    assert transaction_ids_with_tag(session, user.id, "delhi trip") == [first.id]


def test_deleting_a_tag_leaves_the_transactions_alone(session, user):
    row = add_manual(session, user)
    set_tags(session, user.id, row.id, ["trip"])
    tag_id = list_tags(session, user.id)[0]["id"]

    assert delete_tag(session, user.id, tag_id) is True
    assert session.query(Transaction).count() == 1
    assert tags_for(session, user.id, row.id) == []


def test_one_users_tags_are_invisible_to_another(session, user, other):
    row = add_manual(session, user)
    set_tags(session, user.id, row.id, ["private"])

    assert list_tags(session, other.id) == []
    assert set_tags(session, other.id, row.id, ["theirs"]) is None


def test_too_many_tags_on_one_transaction_is_refused(session, user):
    row = add_manual(session, user)
    with pytest.raises(TagError, match="more than"):
        set_tags(session, user.id, row.id, [f"tag{n}" for n in range(20)])


# --- the Personal Expenses summary -----------------------------------------


def test_the_summary_says_nothing_recorded_rather_than_zero(session, user):
    """'No data' and '₹0 spent' are different statements."""
    summary = manual_summary(session, user.id, today=TODAY)
    assert summary["available"] is False
    assert summary["total_count"] == 0


def test_the_summary_counts_only_manual_rows(session, user):
    add_manual(session, user, amount="250")
    session.add(Transaction(
        user_id=user.id, date=TODAY, description="POS SHOP",
        normalized_description="shop", amount=Decimal("9999.00"),
        direction="debit", category="shopping", fingerprint="imported-4",
    ))
    session.commit()

    summary = manual_summary(session, user.id, today=TODAY)
    assert summary["available"] is True
    assert summary["total_count"] == 1
    assert summary["month_total"] == Decimal("250.00")
    assert summary["today_total"] == Decimal("250.00")


def test_the_summary_is_scoped_to_its_owner(session, user, other):
    add_manual(session, user, amount="250")
    assert manual_summary(session, other.id, today=TODAY)["available"] is False
