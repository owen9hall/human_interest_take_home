"""HTTP routes for the server-rendered HSA simulator."""

from decimal import Decimal, InvalidOperation
import threading

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from sqlalchemy import select

from . import db, services
from .models import Category, DebitCard, HsaAccount, Transaction, TransactionStatus


bp = Blueprint("main", __name__)


def to_cents(text: str) -> int:
    """Parse a dollar string into integer cents."""
    try:
        amount = Decimal(text.strip())
    except InvalidOperation as exc:
        raise ValueError("Enter a valid dollar amount (max 2 decimals)") from exc
    if not amount.is_finite() or max(0, -amount.as_tuple().exponent) > 2:
        raise ValueError("Enter a valid dollar amount (max 2 decimals)")
    return int(amount * 100)


def money_text(cents: int | None) -> str:
    if cents is None:
        return ""
    sign = "-" if cents < 0 else ""
    absolute_cents = abs(cents)
    dollars, remainder = divmod(absolute_cents, 100)
    return f"${sign}{dollars:,}.{remainder:02d}"


@bp.app_template_filter("money")
def money(cents: int | None) -> str:
    return money_text(cents)


@bp.get("/")
def index():
    """Render the account and transaction dashboard."""
    accounts = list(db.session.scalars(select(HsaAccount).order_by(HsaAccount.id)))
    transactions = list(
        db.session.scalars(
            select(Transaction)
            .order_by(Transaction.transaction_id.desc())
            .limit(100)
        )
    )
    categories = list(Category)
    return render_template(
        "index.html",
        accounts=accounts,
        transactions=transactions,
        categories=categories,
    )


@bp.post("/accounts")
def create_account():
    """Create an HSA account."""
    holder = request.form.get("account_holder", "")
    try:
        account = services.create_account(holder)
        flash(f"Created account {account.id} for {holder.strip()}", "success")
    except (services.ServiceError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.index"))


@bp.post("/accounts/<int:account_id>/deposit")
def deposit(account_id: int):
    """Deposit funds into an HSA account."""
    try:
        amount = to_cents(request.form.get("amount", ""))
        services.deposit(account_id, amount)
        flash(f"Deposited {money_text(amount)} into account {account_id}", "success")
    except (services.ServiceError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.index"))


@bp.post("/accounts/<int:account_id>/cards")
def issue_card(account_id: int):
    """Issue a debit card for an HSA account."""
    try:
        card = services.issue_card(account_id)
        flash(f"Issued card {card.card_number} to account {account_id}", "success")
    except (services.ServiceError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.index"))


@bp.post("/purchase")
def purchase():
    """Process one card purchase."""
    try:
        card_id = int(request.form.get("card_id", ""))
        amount = to_cents(request.form.get("amount", ""))
        category = Category(request.form.get("category", ""))
        txn = services.process_purchase(card_id, amount, category)
        message = f"Purchase {txn.status.value}"
        if txn.status == TransactionStatus.DECLINED:
            message += f": {txn.decline_reason}"
            level = "warning"
        else:
            level = "success"
        flash(message, level)
    except (services.ServiceError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.index"))


@bp.post("/simulate")
def simulate():
    """Process concurrent purchases against one card."""
    try:
        card_id = int(request.form.get("card_id", ""))
        amount_texts = request.form.get("amounts", "").split(",")
        if not 1 <= len(amount_texts) <= 50:
            raise ValueError("Enter between 1 and 50 amounts")
        amounts = [to_cents(amount_text) for amount_text in amount_texts]
        category = Category(request.form.get("category", ""))
        card = db.session.get(DebitCard, card_id)
        if card is None:
            raise services.ServiceError("Unknown card")
        account_id = card.account_id

        app = current_app._get_current_object()
        barrier = threading.Barrier(len(amounts))
        results: list[tuple[TransactionStatus, str | None] | None] = [
            None
        ] * len(amounts)
        errors: list[BaseException] = []

        def worker(index: int, amount: int) -> None:
            try:
                with app.app_context():
                    barrier.wait(timeout=10)
                    txn = services.process_purchase(card_id, amount, category)
                    results[index] = (txn.status, txn.decline_reason)
            except BaseException as exc:
                errors.append(exc)
                barrier.abort()

        threads = [
            threading.Thread(target=worker, args=(index, amount), daemon=True)
            for index, amount in enumerate(amounts)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=30)
        if any(thread.is_alive() for thread in threads):
            raise ValueError("A simulated purchase did not finish")
        if errors:
            raise ValueError(str(errors[0]))

        balance = db.session.scalar(
            select(HsaAccount.balance_cents).where(HsaAccount.id == account_id)
        )
        approved = sum(
            status == TransactionStatus.APPROVED
            for status, _reason in results
            if status is not None
        )
        declined = sum(
            status == TransactionStatus.DECLINED
            for status, _reason in results
            if status is not None
        )
        flash(
            f"Simulated {len(amounts)} concurrent purchases: {approved} approved, "
            f"{declined} declined. Final balance: {money_text(balance)}",
            "success",
        )
    except (services.ServiceError, ValueError) as exc:
        flash(str(exc), "error")
    return redirect(url_for("main.index"))