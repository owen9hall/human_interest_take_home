"""SQLAlchemy models for HSA accounts, virtual debit cards, and transactions."""

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import CheckConstraint
from sqlalchemy import Enum as SqlEnum
from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from . import db


class TransactionType(str, Enum):
    """A transaction can be a deposit or purchase"""
    DEPOSIT = "DEPOSIT"
    PURCHASE = "PURCHASE"


class TransactionStatus(str, Enum):
    """Transactions are either approved or declined"""
    APPROVED = "APPROVED"
    DECLINED = "DECLINED"


class Category(str, Enum):
    """List of all currently supported purchase categories"""
    PHARMACY = "PHARMACY"
    HOSPITAL = "HOSPITAL"
    RESTAURANT = "RESTAURANT"
    ELECTRONICS = "ELECTRONICS"


"""Purchase categories that will result in an approved transaction (assuming sufficient funds)"""
QUALIFIED_CATEGORIES = {Category.PHARMACY, Category.HOSPITAL}


class HsaAccount(db.Model):
    """HSA account that holds a balance for an account holder."""

    __tablename__ = "hsa_accounts"
    __table_args__ = (
        CheckConstraint("balance_cents >= 0", name="ck_hsa_accounts_balance_nonneg"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_holder: Mapped[str] = mapped_column(String(255), nullable=False)
    balance_cents: Mapped[int] = mapped_column(nullable=False, default=0)

    debit_cards: Mapped[list["DebitCard"]] = relationship(back_populates="account")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="account")


class DebitCard(db.Model):
    """Virtual debit card linked to an HSA account; spends against the account balance."""

    __tablename__ = "debit_cards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    card_number: Mapped[str] = mapped_column(String(16), unique=True, nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("hsa_accounts.id"), nullable=False)

    account: Mapped[HsaAccount] = relationship(back_populates="debit_cards")
    transactions: Mapped[list["Transaction"]] = relationship(back_populates="card")


class Transaction(db.Model):
    """An entry for a deposit or purchase, including declined attempts."""

    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("amount_cents > 0"),)

    transaction_id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("hsa_accounts.id"), nullable=False)
    card_id: Mapped[int | None] = mapped_column(ForeignKey("debit_cards.id"))
    amount_cents: Mapped[int] = mapped_column(nullable=False)
    type: Mapped[TransactionType] = mapped_column(
        SqlEnum(TransactionType), nullable=False
    )
    category: Mapped[Category | None] = mapped_column(SqlEnum(Category))
    status: Mapped[TransactionStatus] = mapped_column(
        SqlEnum(TransactionStatus), nullable=False
    )
    decline_reason: Mapped[str | None] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, default=lambda: datetime.now(timezone.utc)
    )

    account: Mapped[HsaAccount] = relationship(back_populates="transactions")
    card: Mapped[DebitCard | None] = relationship(back_populates="transactions")
