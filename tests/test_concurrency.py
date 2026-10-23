"""Concurrency tests for the no-overdraft requirement.

Each scenario launches real threads, released together by a barrier so their
database operations genuinely overlap. Every thread runs in its own Flask
application context, which gives it its own SQLAlchemy session and connection.
Scenarios repeat REPEATS times, because a race that fails once in fifty runs
would otherwise pass unnoticed. All amounts are integer cents.
"""

import threading
from collections.abc import Callable
from typing import Any

import pytest

from app import services
from app.models import Category, TransactionStatus, TransactionType
from helpers import balance_of, transactions_for

REPEATS = range(20)
BARRIER_TIMEOUT_SECONDS = 10
JOIN_TIMEOUT_SECONDS = 30
INSUFFICIENT_FUNDS = "Insufficient funds"


def run_concurrently(app, jobs: list[Callable[[], Any]]) -> list[Any]:
    """Run each job on its own thread, started together; return results in job order.

    Fails the test if any job raises or any thread does not finish in time.
    """
    barrier = threading.Barrier(len(jobs))
    results: list[Any] = [None] * len(jobs)
    errors: list[BaseException] = []

    def worker(index: int, job: Callable[[], Any]) -> None:
        try:
            with app.app_context():
                barrier.wait(timeout=BARRIER_TIMEOUT_SECONDS)
                results[index] = job()
        except BaseException as exc:  # noqa: BLE001 - surfaced to the test below
            errors.append(exc)
            barrier.abort()

    threads = [
        threading.Thread(target=worker, args=(i, job), daemon=True)
        for i, job in enumerate(jobs)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=JOIN_TIMEOUT_SECONDS)

    assert not any(t.is_alive() for t in threads), "a worker thread did not finish"
    assert not errors, f"worker thread raised: {errors[0]!r}"
    return results


def purchase_job(card_id: int, amount_cents: int, category: Category):
    """Job that makes a purchase and returns (status, decline_reason).

    The result is read inside the worker's app context, before its session
    is torn down.
    """

    def job():
        txn = services.process_purchase(card_id, amount_cents, category)
        return txn.status, txn.decline_reason

    return job


def deposit_job(account_id: int, amount_cents: int):
    """Job that makes a deposit and returns its status."""

    def job():
        return services.deposit(account_id, amount_cents).status

    return job


@pytest.mark.parametrize("repeat", REPEATS)
def test_21_two_competing_purchases_only_one_is_approved(
    app, app_ctx, make_account, make_card, repeat
):
    amounts = [8_000, 5_000]
    account = make_account(balance_cents=10_000)
    card = make_card(account)
    account_id, card_id = account.id, card.id

    results = run_concurrently(
        app, [purchase_job(card_id, a, Category.PHARMACY) for a in amounts]
    )

    statuses = [status for status, _ in results]
    assert statuses.count(TransactionStatus.APPROVED) == 1
    assert statuses.count(TransactionStatus.DECLINED) == 1
    declined_reason = next(
        reason for status, reason in results if status == TransactionStatus.DECLINED
    )
    assert declined_reason == INSUFFICIENT_FUNDS

    approved_amount = amounts[statuses.index(TransactionStatus.APPROVED)]
    assert balance_of(account_id) == 10_000 - approved_amount
    assert balance_of(account_id) >= 0
    assert len(transactions_for(account_id, TransactionType.PURCHASE)) == 2


@pytest.mark.parametrize("repeat", REPEATS)
def test_22_twenty_purchases_of_1000_against_10000_approve_exactly_ten(
    app, app_ctx, make_account, make_card, repeat
):
    account = make_account(balance_cents=10_000)
    card = make_card(account)
    account_id, card_id = account.id, card.id

    results = run_concurrently(
        app, [purchase_job(card_id, 1_000, Category.PHARMACY) for _ in range(20)]
    )

    statuses = [status for status, _ in results]
    assert statuses.count(TransactionStatus.APPROVED) == 10
    assert statuses.count(TransactionStatus.DECLINED) == 10
    assert all(
        reason == INSUFFICIENT_FUNDS
        for status, reason in results
        if status == TransactionStatus.DECLINED
    )
    assert balance_of(account_id) == 0
    assert len(transactions_for(account_id, TransactionType.PURCHASE)) == 20


@pytest.mark.parametrize("repeat", REPEATS)
def test_23_twenty_concurrent_deposits_of_500_lose_no_updates(
    app, app_ctx, make_account, repeat
):
    account = make_account(balance_cents=0)
    account_id = account.id

    results = run_concurrently(app, [deposit_job(account_id, 500) for _ in range(20)])

    assert results == [TransactionStatus.APPROVED] * 20
    assert balance_of(account_id) == 10_000
    deposits = transactions_for(account_id, TransactionType.DEPOSIT)
    assert len(deposits) == 20
    assert all(d.status == TransactionStatus.APPROVED for d in deposits)
