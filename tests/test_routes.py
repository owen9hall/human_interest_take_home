"""Route smoke tests: every POST endpoint, using Flask's test client.

These check the HTTP layer only (redirect, flash message, resulting DB state).
Redirects are NOT followed, so no templates are needed to run them. Business
rules are covered in test_services.py and test_concurrency.py.
"""

from urllib.parse import urlparse

import pytest
from sqlalchemy import select

from app import db
from app.models import DebitCard, HsaAccount, Transaction, TransactionStatus, TransactionType
from helpers import balance_of, transactions_for


@pytest.fixture
def client(app):
    app.config["SECRET_KEY"] = "test"
    return app.test_client()


def post(client, path, **data):
    """POST a form, assert it redirects to the index, and return its flashes.

    Returns a list of (category, message) tuples.
    """
    response = client.post(path, data=data)
    assert response.status_code == 302
    assert urlparse(response.headers["Location"]).path == "/"
    with client.session_transaction() as session:
        return [tuple(f) for f in session.pop("_flashes", [])]


def only(flashes):
    assert len(flashes) == 1, flashes
    return flashes[0]


# ---- POST /accounts -------------------------------------------------------


def test_create_account_success(client, app_ctx):
    category, message = only(post(client, "/accounts", account_holder="Alice"))
    assert category == "success"
    assert "Alice" in message
    assert db.session.scalar(select(HsaAccount.account_holder)) == "Alice"


def test_create_account_blank_name_errors(client, app_ctx):
    category, _ = only(post(client, "/accounts", account_holder="   "))
    assert category == "error"
    assert db.session.scalars(select(HsaAccount)).all() == []


def test_create_account_missing_field_errors_not_400(client, app_ctx):
    category, _ = only(post(client, "/accounts"))
    assert category == "error"


# ---- POST /accounts/<id>/deposit -----------------------------------------


def test_deposit_success_converts_dollars_to_cents(client, app_ctx, make_account):
    account = make_account()
    category, message = only(
        post(client, f"/accounts/{account.id}/deposit", amount="100.50")
    )
    assert category == "success"
    assert "$100.50" in message
    assert balance_of(account.id) == 10_050


@pytest.mark.parametrize("amount", ["abc", "", "1.234", "nan", "inf", "0", "-5"])
def test_deposit_bad_amount_errors_and_changes_nothing(
    client, app_ctx, make_account, amount
):
    account = make_account(balance_cents=500)
    category, _ = only(post(client, f"/accounts/{account.id}/deposit", amount=amount))
    assert category == "error"
    assert balance_of(account.id) == 500
    assert transactions_for(account.id) == []


def test_deposit_unknown_account_errors(client, app_ctx):
    category, _ = only(post(client, "/accounts/999/deposit", amount="10"))
    assert category == "error"


# ---- POST /accounts/<id>/cards -------------------------------------------


def test_issue_card_success(client, app_ctx, make_account):
    account = make_account()
    category, message = only(post(client, f"/accounts/{account.id}/cards"))
    assert category == "success"
    card = db.session.scalars(select(DebitCard)).one()
    assert card.account_id == account.id
    assert card.card_number in message


def test_issue_card_unknown_account_errors(client, app_ctx):
    category, _ = only(post(client, "/accounts/999/cards"))
    assert category == "error"
    assert db.session.scalars(select(DebitCard)).all() == []


# ---- POST /purchase -------------------------------------------------------


def test_purchase_approved(client, app_ctx, make_account, make_card):
    account = make_account(balance_cents=10_000)
    card = make_card(account)
    category, message = only(
        post(client, "/purchase", card_id=card.id, amount="80", category="PHARMACY")
    )
    assert category == "success"
    assert "APPROVED" in message
    assert balance_of(account.id) == 2_000


def test_purchase_declined_insufficient_funds_is_warning(
    client, app_ctx, make_account, make_card
):
    account = make_account(balance_cents=2_000)
    card = make_card(account)
    category, message = only(
        post(client, "/purchase", card_id=card.id, amount="50", category="PHARMACY")
    )
    assert category == "warning"
    assert "DECLINED" in message and "Insufficient funds" in message
    assert balance_of(account.id) == 2_000


def test_purchase_declined_unqualified_is_warning(
    client, app_ctx, make_account, make_card
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)
    category, message = only(
        post(client, "/purchase", card_id=card.id, amount="10", category="RESTAURANT")
    )
    assert category == "warning"
    assert "Not a qualified medical expense" in message
    assert balance_of(account.id) == 10_000


@pytest.mark.parametrize(
    "form",
    [
        {"card_id": "999", "amount": "10", "category": "PHARMACY"},  # unknown card
        {"card_id": "abc", "amount": "10", "category": "PHARMACY"},  # bad card id
        {"card_id": "1", "amount": "", "category": "PHARMACY"},  # missing amount
        {"card_id": "1", "amount": "10", "category": "GROCERIES"},  # bad category
        {"card_id": "1", "amount": "0", "category": "PHARMACY"},  # non-positive
    ],
    ids=["unknown_card", "bad_card_id", "missing_amount", "bad_category", "zero"],
)
def test_purchase_bad_input_errors_and_changes_nothing(
    client, app_ctx, make_account, make_card, form
):
    account = make_account(balance_cents=10_000)
    make_card(account)  # card id 1 exists
    category, _ = only(post(client, "/purchase", **form))
    assert category == "error"
    assert balance_of(account.id) == 10_000
    assert transactions_for(account.id) == []


# ---- POST /simulate -------------------------------------------------------


def test_simulate_80_and_50_against_100_approves_exactly_one(
    client, app_ctx, make_account, make_card
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)
    category, message = only(
        post(client, "/simulate", card_id=card.id, amounts="80, 50", category="PHARMACY")
    )
    assert category == "success"
    assert "1 approved, 1 declined" in message
    assert balance_of(account.id) in (2_000, 5_000)
    purchases = transactions_for(account.id, TransactionType.PURCHASE)
    assert len(purchases) == 2
    assert [p.status for p in purchases].count(TransactionStatus.APPROVED) == 1


@pytest.mark.parametrize(
    "amounts",
    ["", "abc", "80,,50", "80, abc", ",".join(["1"] * 51)],
    ids=["empty", "non_numeric", "blank_entry", "one_bad_entry", "too_many"],
)
def test_simulate_bad_amounts_error_and_run_nothing(
    client, app_ctx, make_account, make_card, amounts
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)
    category, _ = only(
        post(client, "/simulate", card_id=card.id, amounts=amounts, category="PHARMACY")
    )
    assert category == "error"
    assert balance_of(account.id) == 10_000
    assert transactions_for(account.id) == []


def test_simulate_unknown_card_errors(client, app_ctx):
    category, _ = only(
        post(client, "/simulate", card_id="999", amounts="10", category="PHARMACY")
    )
    assert category == "error"


# ---- Method restrictions --------------------------------------------------


@pytest.mark.parametrize("path", ["/accounts", "/purchase", "/simulate"])
def test_post_only_routes_reject_get(client, app_ctx, path):
    assert client.get(path).status_code == 405
