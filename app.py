"""FIKA Loan App - Flask + MySQL backend.

Quick-start:
  1. pip install -r requirements.txt
  2. mysql -u root -p < schema.sql
  3. cp example.env .env  (then fill in your real values)
  4. python app.py
  python app.py create-admin
"""
import os, sys, sqlite3, datetime as dt
from decimal import Decimal, ROUND_HALF_UP
from functools import wraps
import jwt, pymysql
from dotenv import load_dotenv
from flask import Flask, g, jsonify, request, send_from_directory
from werkzeug.security import check_password_hash, generate_password_hash

load_dotenv()
# Serve the frontend HTML from the project root directory
app = Flask(__name__, static_folder=".", static_url_path="")
SECRET = os.environ.get("SECRET_KEY", "")
if not SECRET:
    raise RuntimeError(
        "SECRET_KEY is not set. Copy example.env to .env and fill in a strong secret."
    )
RATE = Decimal(os.getenv("INTEREST_RATE_MONTHLY", "0.08"))
MAX_LOAN = Decimal(os.getenv("MAX_LOAN", "5000"))
CURRENCY = os.getenv("CURRENCY", "ZMW")
USE_SQLITE = os.getenv("USE_SQLITE", "1").lower() in ("1", "true", "yes", "y") or not (os.getenv("DB_HOST") and os.getenv("DB_USER"))
SQLITE_DB = os.path.join(os.path.dirname(__file__), "fika_loans.db")
q2 = lambda x: Decimal(x).quantize(Decimal("0.01"), ROUND_HALF_UP)


def connect_db():
    if USE_SQLITE:
        conn = sqlite3.connect(SQLITE_DB)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    return pymysql.connect(
        host=os.getenv("DB_HOST"), user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME"),
        cursorclass=pymysql.cursors.DictCursor, autocommit=False)


def db():
    if "db" not in g:
        g.db = connect_db()
    return g.db


@app.teardown_appcontext
def close_db(_):
    conn = g.pop("db", None)
    if conn:
        conn.close()


def ensure_schema():
    conn = connect_db()
    try:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS users (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              full_name TEXT NOT NULL,
              phone TEXT NOT NULL UNIQUE,
              email TEXT NOT NULL UNIQUE,
              national_id TEXT NOT NULL UNIQUE,
              password_hash TEXT NOT NULL,
              role TEXT DEFAULT 'customer',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS loans (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              user_id INTEGER NOT NULL,
              principal DECIMAL(12,2) NOT NULL,
              term_months INTEGER NOT NULL,
              interest_rate DECIMAL(5,4) NOT NULL,
              total_payable DECIMAL(12,2) NOT NULL,
              monthly_installment DECIMAL(12,2) NOT NULL,
              amount_paid DECIMAL(12,2) DEFAULT 0.00,
              purpose TEXT,
              status TEXT DEFAULT 'pending',
              created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              disbursed_at DATETIME NULL,
              FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS repayments (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              loan_id INTEGER NOT NULL,
              amount DECIMAL(12,2) NOT NULL,
              paid_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
              FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE CASCADE
            );
        """)
        conn.commit()
    finally:
        conn.close()


def query(sql, args=(), one=False):
    conn = db()
    c = conn.cursor()
    try:
        if USE_SQLITE:
            args = tuple(str(value) if isinstance(value, Decimal) else value for value in args)
        sql_for_db = sql.replace("%s", "?") if USE_SQLITE else sql
        c.execute(sql_for_db, args)
        if sql.strip().lower().startswith(("select", "with")):
            rows = c.fetchall()
            if not rows:
                return None if one else []
            result = [dict(r) for r in rows]
            return result[0] if one else result
        conn.commit()
        return c.rowcount
    finally:
        c.close()


ensure_schema()


def auth(role=None):
    def deco(fn):
        @wraps(fn)
        def wrap(*a, **kw):
            token = request.headers.get("Authorization", "").replace("Bearer ", "")
            try:
                data = jwt.decode(token, SECRET, algorithms=["HS256"])
            except jwt.PyJWTError:
                return jsonify(error="Please sign in again."), 401
            user = query("SELECT id, role, full_name FROM users WHERE id=%s", (data.get("id"),), one=True)
            if not user or user["role"] != data.get("role"):
                return jsonify(error="Your account access has changed. Please sign in again."), 401
            if role and user["role"] != role:
                return jsonify(error="You don't have access to this."), 403
            data["role"] = user["role"]
            data["name"] = user["full_name"]
            g.user = data
            return fn(*a, **kw)
        return wrap
    return deco


def calc(principal, months):
    total = q2(principal * (1 + RATE * months))  # flat interest
    return total, q2(total / months)


def clean(row):
    return {k: (str(v) if isinstance(v, (Decimal, dt.datetime)) else v) for k, v in row.items()}


@app.get("/")
def index():
    """Serve the single-page frontend."""
    return send_from_directory(".", "index.html")


@app.get("/api/health")
def health():
    """Simple liveness check – returns 200 if the server is running."""
    return jsonify(status="ok")


@app.get("/api/config")
def config():
    return jsonify(rate=str(RATE), max_loan=str(MAX_LOAN), currency=CURRENCY)


@app.post("/api/register")
def register():
    d = request.get_json(silent=True) or {}
    if not isinstance(d, dict):
        return jsonify(error="Enter your details in the expected format."), 400
    need = ["full_name", "phone", "email", "national_id", "password"]
    if not all(isinstance(d.get(k), str) and d[k].strip() for k in need) or len(d["password"]) < 8:
        return jsonify(error="Fill every field. Password needs 8+ characters."), 400
    try:
        query("INSERT INTO users(full_name,phone,email,national_id,password_hash) VALUES(%s,%s,%s,%s,%s)",
              (d["full_name"], d["phone"], d["email"], d["national_id"], generate_password_hash(d["password"])))
        db().commit()
    except (sqlite3.IntegrityError, pymysql.err.IntegrityError):
        return jsonify(error="Phone, email or ID is already registered."), 409
    return jsonify(ok=True), 201


@app.post("/api/login")
def login():
    d = request.get_json(silent=True) or {}
    if not isinstance(d, dict):
        return jsonify(error="Enter your phone number and password."), 400
    u = query("SELECT * FROM users WHERE phone=%s", (d.get("phone", ""),), one=True)
    if not u or not check_password_hash(u["password_hash"], d.get("password", "")):
        return jsonify(error="Phone or password is incorrect."), 401
    token = jwt.encode({"id": u["id"], "role": u["role"], "name": u["full_name"],
                        "exp": dt.datetime.utcnow() + dt.timedelta(hours=8)}, SECRET, algorithm="HS256")
    return jsonify(token=token, name=u["full_name"], role=u["role"])


@app.post("/api/loans")
@auth("customer")
def apply():
    d = request.get_json(silent=True) or {}
    if not isinstance(d, dict):
        return jsonify(error="Enter a valid amount and term."), 400
    try:
        amount, months = q2(d["amount"]), int(d["months"])
    except (KeyError, TypeError, ValueError, ArithmeticError):
        return jsonify(error="Enter a valid amount and term."), 400
    if not amount.is_finite() or not (Decimal(50) <= amount <= MAX_LOAN) or not (1 <= months <= 12):
        return jsonify(error=f"Borrow between 50 and {MAX_LOAN} for 1 to 12 months."), 400
    purpose = d.get("purpose", "")
    if purpose is not None and not isinstance(purpose, str):
        return jsonify(error="Enter a short description for the loan purpose."), 400
    if query("SELECT id FROM loans WHERE user_id=%s AND status IN ('pending','active')", (g.user["id"],), one=True):
        return jsonify(error="Finish your current loan before applying again."), 409
    total, monthly = calc(amount, months)
    query("""INSERT INTO loans(user_id,principal,term_months,interest_rate,total_payable,monthly_installment,purpose)
             VALUES(%s,%s,%s,%s,%s,%s,%s)""",
          (g.user["id"], amount, months, RATE, total, monthly, (purpose or "").strip()[:160]))
    db().commit()
    return jsonify(ok=True, total=str(total), monthly=str(monthly)), 201


@app.get("/api/loans")
@auth()
def my_loans():
    rows = query("SELECT * FROM loans WHERE user_id=%s ORDER BY id DESC", (g.user["id"],))
    return jsonify([clean(r) for r in rows])


@app.post("/api/loans/<int:loan_id>/repay")
@auth("customer")
def repay(loan_id):
    data = request.get_json(silent=True) or {}
    if not isinstance(data, dict):
        return jsonify(error="Enter a valid payment amount."), 400
    try:
        amt = q2(data.get("amount", 0))
    except (TypeError, ValueError, ArithmeticError):
        return jsonify(error="Enter a valid payment amount."), 400
    loan = query("SELECT * FROM loans WHERE id=%s AND user_id=%s AND status='active'",
                 (loan_id, g.user["id"]), one=True)
    if not loan:
        return jsonify(error="No active loan found."), 404
    balance = q2(loan["total_payable"]) - q2(loan["amount_paid"])
    if not amt.is_finite() or amt <= 0 or amt > balance:
        return jsonify(error=f"Pay between 0.01 and {balance}."), 400
    # In production, confirm the payment with your mobile money / card gateway here first.
    new_paid = q2(loan["amount_paid"]) + amt
    query("INSERT INTO repayments(loan_id,amount) VALUES(%s,%s)", (loan_id, amt))
    query("UPDATE loans SET amount_paid=%s, status=%s WHERE id=%s",
          (new_paid, "paid" if new_paid >= q2(loan["total_payable"]) else "active", loan_id))
    db().commit()
    return jsonify(ok=True, balance=str(q2(balance - amt)))


@app.get("/api/admin/loans")
@auth("admin")
def admin_loans():
    rows = query("""SELECT l.*, u.full_name, u.phone FROM loans l JOIN users u ON u.id=l.user_id
                    ORDER BY CASE l.status
                        WHEN 'pending' THEN 1
                        WHEN 'active' THEN 2
                        WHEN 'paid' THEN 3
                        WHEN 'rejected' THEN 4
                        ELSE 5
                    END, l.id DESC""")
    return jsonify([clean(r) for r in rows])


@app.post("/api/admin/loans/<int:loan_id>/<action>")
@auth("admin")
def decide(loan_id, action):
    if action not in ("approve", "reject"):
        return jsonify(error="Unknown action."), 400
    if action == "approve":  # replace with a real disbursement call to your payout provider
        n = query("UPDATE loans SET status='active', disbursed_at=CURRENT_TIMESTAMP WHERE id=%s AND status='pending'", (loan_id,))
    else:
        n = query("UPDATE loans SET status='rejected' WHERE id=%s AND status='pending'", (loan_id,))
    db().commit()
    if not n:
        return jsonify(error="This application was not found or is no longer pending."), 409
    return jsonify(ok=True)


@app.get("/api/admin/stats")
@auth("admin")
def stats():
    r = query("""SELECT COUNT(*) loans, COALESCE(SUM(CASE WHEN status IN ('active','paid') THEN principal END),0) disbursed,
                 COALESCE(SUM(amount_paid),0) collected, SUM(status='pending') pending FROM loans""", one=True)
    return jsonify(clean(r) | {"pending": int(r["pending"] or 0)})


def create_admin():
    import getpass
    ensure_schema()
    if USE_SQLITE:
        conn = sqlite3.connect(SQLITE_DB)
        try:
            conn.execute(
                "INSERT INTO users(full_name,phone,email,national_id,password_hash,role) VALUES(?,?,?,?,?, 'admin')",
                (input("Name: "), input("Phone: "), input("Email: "), input("ID: "),
                 generate_password_hash(getpass.getpass("Password: "))))
            conn.commit()
        finally:
            conn.close()
        return
    conn = pymysql.connect(host=os.getenv("DB_HOST"), user=os.getenv("DB_USER"),
                           password=os.getenv("DB_PASSWORD"), database=os.getenv("DB_NAME"))
    with conn.cursor() as c:
        c.execute("INSERT INTO users(full_name,phone,email,national_id,password_hash,role) VALUES(%s,%s,%s,%s,%s,'admin')",
                  (input("Name: "), input("Phone: "), input("Email: "), input("ID: "),
                   generate_password_hash(getpass.getpass("Password: "))))
    conn.commit()


def promote_admin():
    """Grant admin access to an existing account after local operator confirmation."""
    phone = input("Registered account phone number: ").strip()
    if not phone:
        print("A phone number is required.")
        return
    with app.app_context():
        user = query("SELECT id, full_name, role FROM users WHERE phone=%s", (phone,), one=True)
        if not user:
            print("No registered account found with that phone number. Register the account first.")
            return
        if user["role"] == "admin":
            print(f"{user['full_name']} already has administrator access.")
            return
        if input(f"Grant administrator access to {user['full_name']}? Type 'yes' to confirm: ").strip().lower() != "yes":
            print("No changes made.")
            return
        query("UPDATE users SET role='admin' WHERE id=%s", (user["id"],))
        print(f"Administrator access granted to {user['full_name']}.")


if __name__ == "__main__":
    if sys.argv[1:] == ["create-admin"]:
        create_admin()
    elif sys.argv[1:] == ["promote-admin"]:
        promote_admin()
    else:
        app.run(debug=False, port=5000)