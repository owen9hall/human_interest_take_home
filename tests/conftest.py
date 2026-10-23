"""Shared pytest fixtures.

Each test gets its own temporary SQLite *file* database. A file (not
":memory:") is required because every thread/connection must see the same
database, which the concurrency tests depend on.

Setup helpers insert rows directly through the models instead of calling the
services, so a bug in one service cannot break the setup of an unrelated test.
"""

import itertools

import pytest

from app import create_app, db
from app.models import DebitCard, HsaAccount


@pytest.fixture
def app(tmp_path):
    """Flask app bound to a fresh temporary database file."""
    database_path = (tmp_path / "test.db").as_posix()
    flask_app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": f"sqlite:///{database_path}",
        }
    )
    yield flask_app
    with flask_app.app_context():
        db.session.remove()
        db.engine.dispose()


@pytest.fixture
def app_ctx(app):
    """Push an application context for the duration of a test."""
    with app.app_context():
        yield


@pytest.fixture
def make_account(app_ctx):
    """Factory: insert an account with a given starting balance (in cents)."""

    def _make(balance_cents: int = 0, holder: str = "Test Holder") -> HsaAccount:
        account = HsaAccount(account_holder=holder, balance_cents=balance_cents)
        db.session.add(account)
        db.session.commit()
        return account

    return _make


@pytest.fixture
def make_card(app_ctx):
    """Factory: insert a debit card with a unique number for an account."""
    counter = itertools.count(1)

    def _make(account: HsaAccount) -> DebitCard:
        card = DebitCard(
            account_id=account.id,
            card_number=f"{next(counter):016d}",
        )
        db.session.add(card)
        db.session.commit()
        return card

    return _make
