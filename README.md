# Human Interest HSA Take-Home

A small Flask application that simulates HSA accounts, deposits, virtual debit
cards, and card purchases.

## Setup

Requires Python 3.11 or newer (developed and tested on 3.14).

From the project directory, create and activate a virtual environment:

**Windows:**

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux**
```powershell
python3 -m venv .venv
source .venv/bin/activate
```

Install the dependencies:

```powershell
python -m pip install -r requirements.txt
```

If PowerShell prevents activation scripts from running, run this once for your
user account and then activate the environment again:

```powershell
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

## Run the application

Start the development server:

```powershell
flask --app app run --debug
```

Open <http://127.0.0.1:5000> in a browser.

The SQLite database is stored at `instance/hsa.db`. Tables are created
automatically when the application starts.

## Use the application

1. Create an HSA account.
2. Deposit funds into the account.
3. Issue a virtual debit card.
4. Submit an individual purchase, or use **Simulate concurrent purchases** to
   submit several amounts at the same time.
5. Review account balances and transaction results on the dashboard.

`PHARMACY` and `HOSPITAL` purchases are qualified. `RESTAURANT` and
`ELECTRONICS` purchases are declined as non-qualified expenses.

## Run the tests

With the virtual environment activated:

```powershell
python -m pytest
```

## Project layout

```text
app/
  __init__.py       Flask app factory and database setup
  models.py         SQLAlchemy models and transaction enums
  routes.py         Web routes and form handling
  services.py       Account, card, deposit, and purchase logic
  templates/        HTML templates
  static/           CSS
tests/              Application and service tests
instance/hsa.db    Local SQLite database
```
