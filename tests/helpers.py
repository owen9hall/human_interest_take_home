"""Read-only query helpers shared by the test modules.

These always query the database directly (column selects, not ORM identity
map lookups) so assertions reflect what is actually persisted.
"""

from sqlalchemy import select

from app import db
from app.models import HsaAccount, Transaction, TransactionType


def balance_of(account_id: int) -> int:
    """Return the persisted balance of an account, in cents."""
    return db.session.scalar(
        select(HsaAccount.balance_cents).where(HsaAccount.id == account_id)
    )


def transactions_for(
    account_id: int, txn_type: TransactionType | None = None
) -> list[Transaction]:
    """Return an account's transactions in creation order, optionally by type."""
    query = select(Transaction).where(Transaction.account_id == account_id)
    if txn_type is not None:
        query = query.where(Transaction.type == txn_type)
    # Ordered by primary key; rename here if the PK column is not `transaction_id`.
    return list(db.session.scalars(query.order_by(Transaction.transaction_id)))
