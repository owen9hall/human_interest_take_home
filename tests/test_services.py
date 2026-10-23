"""Service-layer tests: spec rules, boundaries, failure paths, invariants.

All amounts are integer cents. Expected values are hand-computed from the
test plan and are never derived from the service implementation. Test names
carry the plan number (e.g. test_10_...).
"""

import re

import pytest
from sqlalchemy import func, select

from app import db, services
from app.models import (
    Category,
    DebitCard,
    HsaAccount,
    Transaction,
    TransactionStatus,
    TransactionType,
)
from helpers import balance_of, transactions_for

NOT_QUALIFIED = "Not a qualified medical expense"
INSUFFICIENT_FUNDS = "Insufficient funds"


def _count(model) -> int:
    return db.session.scalar(select(func.count()).select_from(model))


# --------------------------------------------------------------------------
# A. Spec rules (happy paths)
# --------------------------------------------------------------------------


def test_01_create_account_trims_name_and_starts_at_zero(app_ctx):
    account = services.create_account("  Alice  ")

    assert account.account_holder == "Alice"
    assert balance_of(account.id) == 0


def test_02_deposit_increases_balance_and_records_approved_deposit(
    app_ctx, make_account
):
    account = make_account(balance_cents=0)

    services.deposit(account.id, 10_000)

    assert balance_of(account.id) == 10_000
    txns = transactions_for(account.id)
    assert len(txns) == 1
    assert txns[0].type == TransactionType.DEPOSIT
    assert txns[0].status == TransactionStatus.APPROVED
    assert txns[0].amount_cents == 10_000
    assert txns[0].card_id is None
    assert txns[0].category is None


def test_03_issue_card_generates_unique_16_digit_numbers(app_ctx, make_account):
    account = make_account()

    first = services.issue_card(account.id)
    second = services.issue_card(account.id)

    assert re.fullmatch(r"\d{16}", first.card_number)
    assert re.fullmatch(r"\d{16}", second.card_number)
    assert first.card_number != second.card_number
    cards = db.session.scalars(
        select(DebitCard).where(DebitCard.account_id == account.id)
    ).all()
    assert len(cards) == 2


@pytest.mark.parametrize(
    "category",
    [Category.PHARMACY, Category.HOSPITAL],
    ids=["pharmacy", "hospital"],
)
def test_04_05_qualified_purchase_is_approved_and_debits_balance(
    app_ctx, make_account, make_card, category
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    txn = services.process_purchase(card.id, 3_000, category)

    assert txn.status == TransactionStatus.APPROVED
    assert txn.decline_reason is None
    assert balance_of(account.id) == 7_000
    assert len(transactions_for(account.id)) == 1


@pytest.mark.parametrize(
    "category",
    [Category.RESTAURANT, Category.ELECTRONICS],
    ids=["restaurant", "electronics"],
)
def test_06_07_unqualified_purchase_is_declined_and_balance_untouched(
    app_ctx, make_account, make_card, category
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    txn = services.process_purchase(card.id, 3_000, category)

    assert txn.status == TransactionStatus.DECLINED
    assert txn.decline_reason == NOT_QUALIFIED
    assert balance_of(account.id) == 10_000


def test_08_insufficient_funds_purchase_is_declined(
    app_ctx, make_account, make_card
):
    account = make_account(balance_cents=1_000)
    card = make_card(account)

    txn = services.process_purchase(card.id, 3_000, Category.PHARMACY)

    assert txn.status == TransactionStatus.DECLINED
    assert txn.decline_reason == INSUFFICIENT_FUNDS
    assert balance_of(account.id) == 1_000


@pytest.mark.parametrize(
    ("starting_balance", "category", "expected_reason"),
    [
        (10_000, Category.RESTAURANT, NOT_QUALIFIED),
        (1_000, Category.PHARMACY, INSUFFICIENT_FUNDS),
    ],
    ids=["unqualified", "insufficient_funds"],
)
def test_09_declined_purchase_is_recorded_as_transaction_row(
    app_ctx, make_account, make_card, starting_balance, category, expected_reason
):
    account = make_account(balance_cents=starting_balance)
    card = make_card(account)

    services.process_purchase(card.id, 3_000, category)

    txns = transactions_for(account.id)
    assert len(txns) == 1
    assert txns[0].type == TransactionType.PURCHASE
    assert txns[0].status == TransactionStatus.DECLINED
    assert txns[0].decline_reason == expected_reason
    assert txns[0].amount_cents == 3_000
    assert txns[0].category == category
    assert txns[0].card_id == card.id


# --------------------------------------------------------------------------
# B. Boundaries
# --------------------------------------------------------------------------


def test_10_purchase_equal_to_balance_is_approved_and_zeroes_balance(
    app_ctx, make_account, make_card
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    txn = services.process_purchase(card.id, 10_000, Category.PHARMACY)

    assert txn.status == TransactionStatus.APPROVED
    assert balance_of(account.id) == 0


def test_11_purchase_one_cent_over_balance_is_declined(
    app_ctx, make_account, make_card
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    txn = services.process_purchase(card.id, 10_001, Category.PHARMACY)

    assert txn.status == TransactionStatus.DECLINED
    assert txn.decline_reason == INSUFFICIENT_FUNDS
    assert balance_of(account.id) == 10_000


def test_12_purchase_one_cent_under_balance_is_approved(
    app_ctx, make_account, make_card
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    txn = services.process_purchase(card.id, 9_999, Category.PHARMACY)

    assert txn.status == TransactionStatus.APPROVED
    assert balance_of(account.id) == 1


def test_13_one_cent_purchase_is_approved(app_ctx, make_account, make_card):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    txn = services.process_purchase(card.id, 1, Category.PHARMACY)

    assert txn.status == TransactionStatus.APPROVED
    assert balance_of(account.id) == 9_999


@pytest.mark.parametrize("amount", [0, -1])
def test_14_purchase_rejects_non_positive_amount(
    app_ctx, make_account, make_card, amount
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    with pytest.raises(services.ServiceError):
        services.process_purchase(card.id, amount, Category.PHARMACY)


@pytest.mark.parametrize("amount", [0, -1])
def test_14_deposit_rejects_non_positive_amount(app_ctx, make_account, amount):
    account = make_account(balance_cents=10_000)

    with pytest.raises(services.ServiceError):
        services.deposit(account.id, amount)


# --------------------------------------------------------------------------
# C. Failure paths
# --------------------------------------------------------------------------


@pytest.mark.parametrize("name", ["", "   "], ids=["empty", "whitespace"])
def test_15_create_account_rejects_blank_name(app_ctx, name):
    with pytest.raises(services.ServiceError):
        services.create_account(name)

    assert _count(HsaAccount) == 0


def test_16_unknown_account_or_card_is_rejected(app_ctx):
    with pytest.raises(services.ServiceError):
        services.deposit(999, 1_000)
    with pytest.raises(services.ServiceError):
        services.issue_card(999)
    with pytest.raises(services.ServiceError):
        services.process_purchase(999, 1_000, Category.PHARMACY)


def test_17_service_errors_leave_no_rows_and_balances_unchanged(
    app_ctx, make_account, make_card
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)

    with pytest.raises(services.ServiceError):
        services.deposit(account.id, 0)
    with pytest.raises(services.ServiceError):
        services.process_purchase(card.id, 0, Category.PHARMACY)
    with pytest.raises(services.ServiceError):
        services.process_purchase(999, 1_000, Category.PHARMACY)

    assert _count(Transaction) == 0
    assert balance_of(account.id) == 10_000


# --------------------------------------------------------------------------
# D. Invariants
# --------------------------------------------------------------------------


def _run_mixed_sequence(account, card) -> None:
    """Deposit 10000, then four purchases against it (plan test 18)."""
    services.deposit(account.id, 10_000)  # balance 10000
    services.process_purchase(card.id, 3_000, Category.PHARMACY)  # approved -> 7000
    services.process_purchase(card.id, 2_000, Category.RESTAURANT)  # declined -> 7000
    services.process_purchase(card.id, 9_000, Category.HOSPITAL)  # declined -> 7000
    services.process_purchase(card.id, 7_000, Category.HOSPITAL)  # approved -> 0


def test_18_mixed_sequence_has_expected_statuses_balance_and_row_count(
    app_ctx, make_account, make_card
):
    account = make_account()
    card = make_card(account)

    _run_mixed_sequence(account, card)

    txns = transactions_for(account.id)
    assert [t.status for t in txns] == [
        TransactionStatus.APPROVED,  # deposit 10000
        TransactionStatus.APPROVED,  # pharmacy 3000
        TransactionStatus.DECLINED,  # restaurant 2000 (not qualified)
        TransactionStatus.DECLINED,  # hospital 9000 (insufficient funds)
        TransactionStatus.APPROVED,  # hospital 7000
    ]
    assert len(txns) == 5
    assert balance_of(account.id) == 0


def test_19_ledger_matches_balance_after_mixed_sequence(
    app_ctx, make_account, make_card
):
    account = make_account()
    card = make_card(account)

    _run_mixed_sequence(account, card)

    approved = [
        t
        for t in transactions_for(account.id)
        if t.status == TransactionStatus.APPROVED
    ]
    deposits = sum(t.amount_cents for t in approved if t.type == TransactionType.DEPOSIT)
    purchases = sum(t.amount_cents for t in approved if t.type == TransactionType.PURCHASE)
    assert deposits == 10_000
    assert purchases == 10_000
    assert deposits - purchases == balance_of(account.id)


def test_20_purchase_on_one_account_does_not_affect_another(
    app_ctx, make_account, make_card
):
    account_a = make_account(balance_cents=10_000)
    account_b = make_account(balance_cents=10_000)
    card_a = make_card(account_a)

    services.process_purchase(card_a.id, 3_000, Category.PHARMACY)

    assert balance_of(account_a.id) == 7_000
    assert balance_of(account_b.id) == 10_000
    assert transactions_for(account_b.id) == []
