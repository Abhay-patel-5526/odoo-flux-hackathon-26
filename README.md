# Brightloop Subscription Management — Backend Foundation

A Flask + SQLite + SQLAlchemy foundation for the Odoo × FLUX hackathon Subscription Management System.

## Included

- Flask application factory (`app.create_app`)
- SQLite database configured in `instance/brightloop.db`
- SQLAlchemy models for users, customers, products, variants, plans, tax rules, quotation templates, subscriptions, invoice lines, invoices, billing records, discounts, discount usage, payments and company settings
- Flask-Login integration and password hashing helpers
- Role-protection decorators (`admin_required`, `staff_or_admin_required`, `customer_required`)
- Flask-Migrate integration for schema migrations
- CSRF protection for future form routes
- CLI commands to initialize the database and create an admin
- Health-check endpoints (`/` and `/health`)

## 1. Create and activate a virtual environment

Windows PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

Windows CMD:

```cmd
py -m venv .venv
.venv\Scripts\activate.bat
```

macOS/Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install dependencies and configure environment

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env`, then replace `SECRET_KEY` with a long random value. Keep `.env` private; it is ignored by Git.

PowerShell copy command:

```powershell
Copy-Item .env.example .env
```

## 3. Initialize the database

```bash
flask --app wsgi:app init-db
```

## 4. Create the admin account

```bash
flask --app wsgi:app create-admin
```

The command prompts for name, email and password. Use a strong password.

## 5. Run the application

```bash
flask --app wsgi:app run --debug
```

Open `http://127.0.0.1:5000/`. The `/health` endpoint should return `{"status":"ok"}`.

## 6. Database migrations

For the initial hackathon scaffold, `init-db` uses `db.create_all()` to create tables. When models change after the database already exists, use migrations instead of expecting `create_all()` to alter existing tables:

```bash
flask --app wsgi:app db init
flask --app wsgi:app db migrate -m "describe schema change"
flask --app wsgi:app db upgrade
```

Only run `db init` once; the generated `migrations/` directory should be committed to Git.

## Project layout

```text
brightloop_backend/
├── app/
│   └── __init__.py          # Application factory and extension setup
├── instance/                # Local SQLite database (ignored by Git)
├── config.py
├── extensions.py
├── models.py                # SQLAlchemy models and relationships
├── permissions.py           # Role-protection decorators
├── cli.py                   # init-db and create-admin commands
├── wsgi.py                  # Flask application entry point
├── requirements.txt
├── .env.example
└── .gitignore
```

## Adding routes later

Create a blueprint, for example `routes/products.py`:

```python
from flask import Blueprint, render_template
from flask_login import login_required
from permissions import staff_or_admin_required

products_bp = Blueprint("products", __name__)

@products_bp.get("/")
@staff_or_admin_required
def list_products():
    # Query Product records and render a template here.
    ...
```

Then register it in `app/__init__.py` inside `create_app()`:

```python
from routes.products import products_bp
app.register_blueprint(products_bp, url_prefix="/products")
```

When adding HTML forms, include a CSRF token (`{{ csrf_token() }}`) in each POST form. For customer-owned records, always filter queries by `current_user.customer_profile.id`; never trust a customer ID supplied by the browser.

## Important implementation notes

- Money columns use `Numeric` and Python `Decimal`, not float.
- `BillingRecord` has a unique constraint on subscription + billing period to help prevent duplicate recurring invoices. The billing service must still handle transaction/unique-constraint errors safely.
- Payments are recorded individually, allowing partial payments. The payment service must update `Invoice.paid_amount` and invoice status transactionally.
- Invoice overdue state is derived from due date and outstanding balance; it is not a replacement invoice status.
- The schema is a starting point. Add tests and business-rule validation in service functions before relying on financial workflows.
- The reset-password token delivery mechanism, recurring billing scheduler, tax/discount calculations, and payment processing are not implemented yet; these are feature modules to add next.
