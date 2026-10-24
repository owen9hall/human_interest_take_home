# HSA Application Architecture

This application is a small server-rendered Flask application that simulates
HSA accounts, deposits, virtual debit cards, and card purchases.

## System architecture

```text
Browser
   |
   v
Flask routes       - validate form input and render/redirect
   |
   v
Service layer      - apply account, deposit, card, and purchase rules
   |
   v
SQLAlchemy models  - read and write the SQLite database
```

- **Routes** are in `app/routes.py`. They handle HTTP requests, convert dollar
  amounts to cents, and display success or error messages.
- **Services** are in `app/services.py`. They contain the business rules and
  database updates.
- **Models** are in `app/models.py`. They define accounts, cards, and
  transactions.
- **SQLite** stores the data in `instance/hsa.db`. SQLAlchemy creates the
  tables when the Flask app starts.

All money is stored as integer cents. This avoids floating-point rounding
problems.

## Request flow

### Normal request

1. A user submits a form in the dashboard.
2. A Flask route reads and validates the form values.
3. The route calls the relevant service function.
4. The service checks the account/card and applies the business rules.
5. The service updates the balance and records a transaction in one database
   transaction.
6. The route flashes the result and redirects back to the dashboard.
7. The dashboard loads the current accounts and recent transactions.

### Purchase request

For a purchase, the service:

1. Validates the amount and card.
2. Declines unqualified categories without changing the balance.
3. For a qualified category, atomically subtracts the amount only when the
   account has enough money.
4. Records either an `APPROVED` or `DECLINED` purchase transaction.

All attempted purchases are recorded, regardless of approval or denial status.

## Data model

```text
HsaAccount 1 ──── * DebitCard
HsaAccount 1 ──── * Transaction
DebitCard  1 ──── * Transaction
```

### `HsaAccount`

- `id`
- `account_holder`
- `balance_cents`

A database constraint prevents the balance from becoming negative.

### `DebitCard`

- `id`
- unique 16-digit `card_number`
- `account_id`

Each card belongs to one HSA account.

### `Transaction`

- `transaction_id`
- `account_id`
- optional `card_id`
- `amount_cents`
- `type`: `DEPOSIT` or `PURCHASE`
- optional purchase `category`
- `status`: `APPROVED` or `DECLINED`
- optional `decline_reason`
- `created_at`

Deposits do not use a card. Purchases reference both the account and the card.

## Concurrency handling

The risk is if two purchases spend from the balance at the same time. In order to prevent, a purchase is a single, atomic SQL statement that subtracts the amount if the balance is great enough:

```sql
UPDATE hsa_accounts
SET balance_cents = balance_cents - :amount
WHERE id = :account_id
  AND balance_cents >= :amount;
```

SQLite only runs one write at a time, so simultaneous purchases are executed one at a time.

If the row was updated, the transaction was successful, if not, the transaction was declined for insufficient funds. (Deposits follow this pattern)

The hsa_accounts table has an additional constraint that enforces the balance to be non-negative, for an added layer of protection.

SQLite is configured with:

- WAL mode: improves read/write concurrency.
- timeout: allowing a short wait when another write is in progress.
- foreign-key enforcement: for valid relationships.

## Design tradeoffs

- **SQLite instead of a server database:** fast and simple to stand up for a 
  take-home assignment, but server database better for production application.
- **Choosing an ORM (SQLAlchemy) over sqlite3:** allowed for more intuitive modeling of entities and relationships, but added an additional layer of abstraction to handle.
- **Using Flask to build HTML page instead of separate frontend API layer:** more lightweight frontend, optimal for a simple webapp, however, every action requires a full page reload and concurrent purchases cant be sent from the browser (had to create threads instead of send parallel requests).
- **Integer cents instead of decimal values:** avoids floating point errors, but requires extra code to convert to/from user's dollar input and maintain consistency throughout system.
