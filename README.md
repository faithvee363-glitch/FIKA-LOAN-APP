# FIKA Loan App 🏦

A clean, full-stack micro-lending web app built with **Flask** (Python) and **MySQL**, with a single-page HTML/CSS/JS frontend.

---

## Features

| Feature | Details |
|---|---|
| Customer and admin sign-in | Role-specific access; create admins with `python app.py create-admin` or promote an existing account with `python app.py promote-admin` |
| Loan application | Type a custom amount (50–5000 ZMW), select a 1–12 month term, and review eligibility and agreement terms |
| Live loan calculator | Automatically calculates flat-rate interest, instalments, and total repayment before submitting |
| Repayment reminders | Optional browser notifications one day before monthly instalments while FIKA is open |
| Repayments | Track balance, mark loan paid when settled |
| Admin panel | Dedicated admin sign-in, responsive application review, approve / reject, portfolio stats |
| Responsive UI | Works on mobile and desktop |

---

## Quick Start

### 1. Prerequisites
- Python 3.9+
- MySQL 8+ or MariaDB 10.6+

### 2. Install dependencies
```bash
pip install -r requirements.txt
```

### 3. Set up the database
```bash
mysql -u root -p < schema.sql
```

### 4. Configure environment
```bash
cp example.env .env
```
Open `.env` and set at minimum:
- `SECRET_KEY` – a long random string (see comment inside)
- `DB_HOST`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`

### 5. Create an admin account
To create a new administrator account:
```bash
python app.py create-admin
```
To grant administrator access to an existing registered account, run this command locally, enter the account's registered phone number, and confirm the account name:
```bash
python app.py promote-admin
```
Public sign-up always creates customer accounts. Only accounts explicitly granted the `admin` role through these local commands can sign in as administrators or access admin APIs. If admin sign-in reports that an account lacks administrator access, promote the correct registered account and sign in using its phone number with the **Admin** sign-in option.

### 6. Run the app
```bash
python app.py
```
Visit **http://localhost:5000**

---

## Project Structure

```
FIKA LOAN APP/
├── app.py          # Flask backend – all API routes
├── index.html      # Single-page frontend (HTML + CSS + JS)
├── schema.sql      # MySQL database schema
├── requirements.txt
├── example.env     # Template – copy to .env and fill in values
├── .env            # Your local secrets (git-ignored)
└── .gitignore
```

---

## API Endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| GET | `/` | – | Frontend SPA |
| GET | `/api/health` | – | Liveness check |
| GET | `/api/config` | – | Rate, max loan, currency |
| POST | `/api/register` | – | Register new customer |
| POST | `/api/login` | – | Login, returns JWT |
| GET | `/api/loans` | customer | My loans |
| POST | `/api/loans` | customer | Apply for loan |
| POST | `/api/loans/<id>/repay` | customer | Make a repayment |
| GET | `/api/admin/loans` | admin | All applications |
| POST | `/api/admin/loans/<id>/approve` | admin | Approve loan |
| POST | `/api/admin/loans/<id>/reject` | admin | Reject loan |
| GET | `/api/admin/stats` | admin | Portfolio stats |

---

## Environment Variables

| Variable | Default | Description |
|---|---|---|
| `SECRET_KEY` | **required** | JWT signing secret |
| `DB_HOST` | `localhost` | MySQL host |
| `DB_USER` | – | MySQL username |
| `DB_PASSWORD` | – | MySQL password |
| `DB_NAME` | `fika_loans` | Database name |
| `INTEREST_RATE_MONTHLY` | `0.08` | Flat monthly rate (8%) |
| `MAX_LOAN` | `5000` | Max borrowable amount |
| `CURRENCY` | `ZMW` | Currency label in UI |

---

## Security Notes

- Passwords are hashed with **Werkzeug/bcrypt** – never stored plain.
- JWTs expire after **8 hours**.
- The `.env` file is git-ignored – never commit secrets.
- For production: use HTTPS, a WSGI server (gunicorn), and a reverse proxy (nginx).
- Repayment reminders use the browser Notifications API and only run while the app is open; production deployments need HTTPS. Final repayment dates must be confirmed in the loan agreement.
