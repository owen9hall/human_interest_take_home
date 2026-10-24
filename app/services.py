"""Business logic for HSA accounts, deposits, cards, and purchases."""

import secrets

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from . import db
from .models import (
    QUALIFIED_CATEGORIES,
    Category,
    DebitCard,
    HsaAccount,
    Transaction,
    TransactionStatus,
    TransactionType,
)


class ServiceError(Exception):
    """Raised when a request is malformed or refers to a missing entity."""


def create_account(account_holder: str) -> HsaAccount:
    """Create an HSA account with a zero balance."""
    name = account_holder.strip()
    if not name:
        raise ServiceError("Account holder name is required")
    account = HsaAccount(account_holder=name, balance_cents=0)
    db.session.add(account)
    db.session.commit()
    return account


def deposit(account_id: int, amount_cents: int) -> Transaction:
    """Deposit funds into an account atomically and record an approved deposit."""
    if amount_cents <= 0:
        raise ServiceError("Amount must be greater than 0")
    account = db.session.get(HsaAccount, account_id)
    if account is None:
        raise ServiceError("Unknown account")

    # making the update as a db query so it is atomic
    db.session.execute(
        update(HsaAccount)
        .where(HsaAccount.id == account_id)
        .values(balance_cents=HsaAccount.balance_cents + amount_cents)
    )
    txn = Transaction(
        account_id=account_id,
        card_id=None,
        amount_cents=amount_cents,
        type=TransactionType.DEPOSIT,
        category=None,
        status=TransactionStatus.APPROVED,
    )
    db.session.add(txn)
    db.session.commit()
    return txn


def issue_card(account_id: int) -> DebitCard:
    """Issue a virtual debit card with a unique 16-digit number."""
    account = db.session.get(HsaAccount, account_id)
    if account is None:
        raise ServiceError("Unknown account")

    for attempt in range(5):
        card = DebitCard(
            account_id=account_id,
            card_number=f"{secrets.randbelow(10**16):016d}",
        )
        db.session.add(card)
        try:
            db.session.commit()
            return card
        except IntegrityError:
            db.session.rollback()
            if attempt == 4:
                raise


def process_purchase(card_id: int, amount_cents: int, category: Category) -> Transaction:
    """Process a card purchase; decline without raising if it is invalid or underfunded."""
    if amount_cents <= 0:
        raise ServiceError("Amount must be greater than 0")
    card = db.session.get(DebitCard, card_id)
    if card is None:
        raise ServiceError("Unknown card")

    account_id = card.account_id

    # decline if the category is not qualified or is unknown
    if category not in QUALIFIED_CATEGORIES:
        txn = Transaction(
            account_id=account_id,
            card_id=card_id,
            amount_cents=amount_cents,
            type=TransactionType.PURCHASE,
            category=category,
            status=TransactionStatus.DECLINED,
            decline_reason="Not a qualified medical expense",
        )
        db.session.add(txn)
        db.session.commit()
        return txn

    # making the update as a db query so it is atomic
    result = db.session.execute(
        update(HsaAccount)
        .where(
            HsaAccount.id == account_id,
            HsaAccount.balance_cents >= amount_cents,
        )
        .values(balance_cents=HsaAccount.balance_cents - amount_cents)
    )
    if result.rowcount == 1:
        status = TransactionStatus.APPROVED
        decline_reason = None
    else:
        status = TransactionStatus.DECLINED
        decline_reason = "Insufficient funds"

    txn = Transaction(
        account_id=account_id,
        card_id=card_id,
        amount_cents=amount_cents,
        type=TransactionType.PURCHASE,
        category=category,
        status=status,
        decline_reason=decline_reason,
    )
    db.session.add(txn)
    db.session.commit()
    return txn
