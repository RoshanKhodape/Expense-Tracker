import os, shutil, json, random,smtplib, sqlite3
from flask import render_template
from flask import flash
from flask import Flask, render_template, request,send_file, redirect, url_for, session
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from email.message import EmailMessage
from dotenv import load_dotenv
from flask import abort

load_dotenv()

app = Flask(__name__)
app.config.update(
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=False
)
app.secret_key = "expensetracker_very_secret_key_123456"

# ---------------- CURRENCY SETTINGS ----------------
CURRENCIES = {
    "INR": "₹",
    "USD": "$",
    "EUR": "€",
    "GBP": "£"
}

# ✅ INR base conversion (approx)
RATES = {
    "INR": 1.0,
    "USD": 0.012,   # ₹1 = $0.012  (approx)
    "EUR": 0.011,
    "GBP": 0.0095
}

def get_currency():
    code = session.get("currency", "INR")
    symbol = CURRENCIES.get(code, "₹")
    rate = RATES.get(code, 1.0)
    return code, symbol, rate

def convert_amount(amount_in_inr, rate):
    return round(float(amount_in_inr) * rate, 2)

# ---------------- SET CURRENCY ----------------
@app.route("/set-currency", methods=["POST"])
def set_currency():
    if "user_id" not in session:
        return redirect(url_for("login"))

    currency = request.form.get("currency", "INR")

    if currency not in CURRENCIES:
        currency = "INR"

    session["currency"] = currency
    flash(f"Currency set to {currency} ✅", "success")

    return redirect(request.referrer or url_for("index"))


# ---------------- DB CONNECTION ----------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "app.db")
def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn
# ---------------- INIT LOGS TABLE ----------------
def init_logs_table():
    conn = get_db_connection()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            event TEXT NOT NULL,
            details TEXT,
            ip TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    conn.close()


# ---------------- LOGGING FUNCTION ----------------
def add_log(user_id, event, details=""):
    try:
        ip = request.remote_addr if request else "unknown"
    except:
        ip = "unknown"

    try:
        conn = get_db_connection()
        conn.execute("""
            INSERT INTO logs (user_id, event, details, ip)
            VALUES (?, ?, ?, ?)
        """, (user_id, event, details, ip))
        conn.commit()
        conn.close()
    except Exception as e:
        print("❌ LOG ERROR:", e)


# ---------------- OTP GENERATION ----------------
def generate_otp():
    return str(random.randint(100000, 999999))

# ---------------- REGISTER ----------------
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"].strip().lower()
        email = request.form["email"].strip().lower()
        password = request.form["password"]

        otp = str(random.randint(100000, 999999))
        hashed_password = generate_password_hash(password)

        conn = get_db_connection()
        try:
            conn.execute("""
                INSERT INTO users (username, email, password, email_otp)
                VALUES (?, ?, ?, ?)
            """, (username, email, hashed_password, otp))
            conn.commit()

            send_otp(email, otp)   # 📧 send email

            flash("OTP sent to your email 📧", "success")
            return redirect(url_for("verify_email"))

        except:
            flash("User already exists ❌", "error")

        finally:
            conn.close()

    return render_template("register.html")

# ---------------- SEND OTP EMAIL FUNCTION ----------------
def send_otp(email, otp):
    EMAIL_USER = os.getenv("khodaperoshan97@gmail.com")
    EMAIL_PASS = os.getenv("Roshan@123")

    if not EMAIL_USER or not EMAIL_PASS:
        raise RuntimeError("EMAIL_USER and EMAIL_PASS are missing in .env")    # Gmail App Password

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
        smtp.login(EMAIL_USER, EMAIL_PASS)
        smtp.sendmail(
            EMAIL_USER,
            email,
            f"Subject: OTP Reset\n\nYour OTP is {otp}"
        )

# ---------------- VERIFY EMAIL ----------------
@app.route("/verify-email", methods=["GET", "POST"])
def verify_email():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        otp = request.form["otp"]

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE email=? AND email_otp=?",
            (email, otp)
        ).fetchone()

        if user:
            conn.execute("""
                UPDATE users
                SET is_verified=1, email_otp=NULL
                WHERE email=?
            """, (email,))
            conn.commit()
            conn.close()

            flash("Email verified successfully ✅", "success")
            return redirect(url_for("login"))
        else:
            conn.close()
            flash("Invalid OTP ❌", "error")

    return render_template("verify_email.html")

# ---------------- FORGOT PASSWORD ----------------
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if request.method == "POST":
        email = request.form["email"].strip().lower()

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not user:
            conn.close()
            flash("Email not registered ❌", "error")
            return redirect(url_for("forgot_password"))

        otp = generate_otp()

        expiry_time = datetime.now() + timedelta(minutes=5)

        conn.execute("""
            UPDATE users 
            SET reset_otp = ?, reset_otp_expiry = ?, reset_otp_attempts = 0
            WHERE email = ?
        """, (otp, expiry_time.strftime("%Y-%m-%d %H:%M:%S"), email))
        conn.commit()
        add_log(user["id"], "RESET_OTP_SENT", f"email={email}")
        conn.close()

        # ✅ Send OTP on email
        send_otp(email, otp)

        session["reset_email"] = email
        flash("OTP sent to email ✅", "success")
        return redirect(url_for("verify_otp"))

    return render_template("forgot_password.html")

# ---------------- VERIFY OTP ----------------
@app.route("/verify-otp", methods=["GET", "POST"])
def verify_otp():
    if "reset_email" not in session:
        flash("Session expired. Try again ❌", "error")
        return redirect(url_for("forgot_password"))

    email = session["reset_email"]

    if request.method == "POST":
        entered_otp = request.form["otp"].strip()

        conn = get_db_connection()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        if not user:
            conn.close()
            flash("User not found ❌", "error")
            return redirect(url_for("forgot_password"))

        # ✅ Attempts limit
        attempts = user["reset_otp_attempts"] or 0
        if attempts >= 3:
            conn.close()
            flash("Too many wrong attempts. Generate OTP again ❌", "error")
            return redirect(url_for("forgot_password"))

        # ✅ Expiry check
        expiry_str = user["reset_otp_expiry"]
        if not expiry_str:
            conn.close()
            flash("OTP expired. Generate again ❌", "error")
            return redirect(url_for("forgot_password"))

        expiry_time = datetime.strptime(expiry_str, "%Y-%m-%d %H:%M:%S")

        if datetime.now() > expiry_time:
            conn.close()
            flash("OTP expired ⏳ Generate again", "error")
            return redirect(url_for("forgot_password"))

        # ✅ OTP match
        if entered_otp == user["reset_otp"]:
            conn.close()
            flash("OTP verified ✅ Now reset password", "success")
            return redirect(url_for("reset_password"))

        # ❌ Wrong OTP → attempts increase
        conn.execute("""
            UPDATE users
            SET reset_otp_attempts = reset_otp_attempts + 1
            WHERE email = ?
        """, (email,))
        conn.commit()
        conn.close()

        add_log(user["id"], "RESET_OTP_WRONG", f"email={email}, attempt={attempts+1}")


        flash("Wrong OTP ❌", "error")
        return redirect(url_for("verify_otp"))

    return render_template("verify_otp.html")


# ---------------- RESET PASSWORD ----------------
@app.route("/reset-password", methods=["GET", "POST"])
def reset_password():
    if "reset_email" not in session:
        flash("Session expired. Try again ❌", "error")
        return redirect(url_for("forgot_password"))

    email = session["reset_email"]

    if request.method == "POST":
        new_password = request.form["new_password"].strip()
        confirm_password = request.form["confirm_password"].strip()

        if new_password != confirm_password:
            flash("Passwords do not match ❌", "error")
            return redirect(url_for("reset_password"))

        hashed_password = generate_password_hash(new_password)

        conn = get_db_connection()
        conn.execute("""
            UPDATE users
            SET password = ?, reset_otp = NULL, reset_otp_expiry = NULL, reset_otp_attempts = 0
            WHERE email = ?
        """, (hashed_password, email))
        conn.commit()
        user = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        if user:
            add_log(user["id"], "PASSWORD_RESET", f"email={email}")

        conn.close()

        session.pop("reset_email", None)

        flash("Password reset successful ✅", "success")
        return redirect(url_for("login"))

    return render_template("reset_password.html")


# ---------------- LOGIN ----------------
@app.route("/login", methods=["GET", "POST"])
def login():
    print("✅ LOGIN SESSION:", session)

    if request.method == "POST":
        username = request.form["username"].strip().lower()
        password = request.form["password"].strip()

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM users WHERE username = ?",
            (username,)
        ).fetchone()

        # ✅ invalid username
        if not user:
            conn.close()
            add_log(None, "LOGIN_FAILED", f"username={username} (user not found)")
            flash("Invalid username or password ❌", "error")
            return redirect(url_for("login"))

        # ✅ password wrong
        if not check_password_hash(user["password"], password):
            conn.close()
            add_log(user["id"], "LOGIN_FAILED", f"username={username} (wrong password)")
            flash("Invalid username or password ❌", "error")
            return redirect(url_for("login"))

        # ✅ email verification check
        if not user["is_verified"]:
            conn.close()
            add_log(user["id"], "LOGIN_BLOCKED", "Email not verified")
            flash("Verify email before login ❌", "error")
            return redirect(url_for("login"))

        conn.close()

        # ✅ login success
        session["user"] = user["username"]
        session["user_id"] = user["id"]

        add_log(user["id"], "LOGIN_SUCCESS", f"username={username}")

        flash("Login successful 👋", "success")
        return redirect(url_for("index"))

    return render_template("login.html")


# ---------------- DASHBOARD ----------------

@app.route("/")
def index():
    print("📌 SESSION AT INDEX:", session)

    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]
    username = session["user"]

    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("SELECT IFNULL(SUM(amount),0) FROM expenses WHERE user_id=?", (user_id,))
    overall_total = cur.fetchone()[0]

    current_month = datetime.now().strftime("%Y-%m")
    cur.execute("""
        SELECT IFNULL(SUM(amount),0)
        FROM expenses
        WHERE user_id=? AND substr(date,1,7)=?
    """, (user_id, current_month))
    monthly_total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM expenses WHERE user_id=?", (user_id,))
    total_transactions = cur.fetchone()[0]

    conn.close()
    currency_code, currency_symbol, rate = get_currency()
    return render_template(
    "index.html",
    username=username,
    monthly_total = convert_amount(monthly_total, rate),
    overall_total = convert_amount(overall_total, rate),
    total_transactions=total_transactions,
    currency_code=currency_code,
    currency_symbol=currency_symbol
)


# ---------------- PROFILE ----------------
@app.route("/profile", methods=["GET", "POST"])
def profile():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    user = conn.execute(
        "SELECT * FROM users WHERE id=?",
        (session["user_id"],)
    ).fetchone()

    if request.method == "POST":
        new_username = request.form["username"].strip()
        old_password = request.form["old_password"]
        new_password = request.form["new_password"]

        # ✅ Old password check
        if not check_password_hash(user["password"], old_password):
            flash("Old password is incorrect ❌", "error")
            conn.close()
            return redirect(url_for("profile"))

        # ✅ Update username
        if new_username:
            conn.execute(
                "UPDATE users SET username=? WHERE id=?",
                (new_username, session["user_id"])
            )
            session["user"] = new_username  # update session

        # ✅ Update password
        if new_password:
            hashed = generate_password_hash(new_password)
            conn.execute(
                "UPDATE users SET password=? WHERE id=?",
                (hashed, session["user_id"])
            )

        conn.commit()
        conn.close()

        flash("Profile updated successfully ✅", "success")
        return redirect(url_for("profile"))

    conn.close()
    return render_template("profile.html", user=user)

# ---------------- ADD EXPENSE ----------------
@app.route("/add", methods=["GET", "POST"])
def add_expense():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    # ✅ Always fetch categories for dropdown
    cats = conn.execute(
        "SELECT name FROM categories WHERE user_id=? ORDER BY name",
        (session["user_id"],)
    ).fetchall()

    if request.method == "POST":
        date = request.form["date"]
        amount = request.form["amount"]
        category = request.form["category"]
        note = request.form["note"]

        if not date or not amount or not category:
            flash("Date, Amount and Category are required ❗", "error")
            conn.close()
            return render_template("add.html", categories=cats)

        conn.execute("""
            INSERT INTO expenses (user_id, date, amount, category, note)
            VALUES (?, ?, ?, ?, ?)
        """, (session["user_id"], date, amount, category, note))

        conn.commit()
        conn.close()

        flash("Expense added successfully ✅", "success")
        return redirect(url_for("view_expenses"))

    conn.close()
    return render_template("add.html", categories=cats)


# ---------------- VIEW EXPENSES ----------------
@app.route("/view")
def view_expenses():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    expenses = conn.execute(
        """
        SELECT id,date, amount, category, note
        FROM expenses
        WHERE user_id = ?
        ORDER BY date DESC
        """,
        (session["user_id"],)
    ).fetchall()

    total = conn.execute(
        "SELECT IFNULL(SUM(amount), 0) FROM expenses WHERE user_id = ?",
        (session["user_id"],)
    ).fetchone()[0]

    conn.close()

    currency_code, currency_symbol, rate = get_currency()

    converted_expenses = []
    for e in expenses:
        converted_expenses.append({
            "id": e["id"],
            "date": e["date"],
            "amount": convert_amount(e["amount"], rate),
            "category": e["category"],
            "note": e["note"]
        })
    total = convert_amount(total, rate)

    return render_template("view.html",
                       expenses=converted_expenses,
                       total=total,
                       currency_symbol=currency_symbol)

# ---------------- EDIT EXPENSE ----------------
@app.route("/edit/<int:id>", methods=["GET", "POST"])
def edit_expense(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    if request.method == "POST":
        date = request.form["date"]
        amount = request.form["amount"]
        category = request.form["category"]
        note = request.form["note"]

        conn.execute("""
            UPDATE expenses
            SET date=?, amount=?, category=?, note=?
            WHERE id=? AND user_id=?
        """, (date, amount, category, note, id, session["user_id"]))

        conn.commit()
        conn.close()

        flash("Expense updated successfully ✏️", "success")
        return redirect(url_for("view_expenses"))

    expense = conn.execute(
        "SELECT * FROM expenses WHERE id=? AND user_id=?",
        (id, session["user_id"])
    ).fetchone()

    conn.close()

    if expense is None:
        flash("Expense not found ❌", "error")
        return redirect(url_for("view_expenses"))

    return render_template("edit.html", expense=expense)

   
# ---------------- DELETE EXPENSE ----------------
@app.route("/delete/<int:id>")
def delete_expense(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    exp = conn.execute(
        "SELECT * FROM expenses WHERE id=? AND user_id=?",
        (id, session["user_id"])
    ).fetchone()

    if not exp:
        conn.close()
        flash("Expense not found ❌", "error")
        return redirect(url_for("view_expenses"))

    add_log(session["user_id"], "EXPENSE_DELETE",
            f"id={id}, amount={exp['amount']}, category={exp['category']}, date={exp['date']}")

    conn.execute(
        "DELETE FROM expenses WHERE id = ? AND user_id = ?",
        (id, session["user_id"])
    )
    conn.commit()
    conn.close()

    flash("Expense deleted successfully 🗑️", "success")
    return redirect(url_for("view_expenses"))

# ---------------- MANAGE CATEGORIES ----------------
@app.route("/categories", methods=["GET", "POST"])
def categories():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    # ✅ Add Category
    if request.method == "POST":
        name = request.form["name"].strip()

        if not name:
            flash("Category name required ❌", "error")
            return redirect(url_for("categories"))

        try:
            conn.execute(
                "INSERT INTO categories (user_id, name) VALUES (?, ?)",
                (session["user_id"], name)
            )
            conn.commit()
            flash("Category added ✅", "success")
        except:
            flash("Category already exists ❌", "error")

        return redirect(url_for("categories"))

    # ✅ Fetch Categories
    categories = conn.execute(
        "SELECT * FROM categories WHERE user_id=? ORDER BY name",
        (session["user_id"],)
    ).fetchall()

    conn.close()
    return render_template("categories.html", categories=categories)

# ---------------- EDIT CATEGORY ----------------
@app.route("/categories/edit/<int:id>", methods=["GET", "POST"])
def edit_category(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    category = conn.execute(
        "SELECT * FROM categories WHERE id=? AND user_id=?",
        (id, session["user_id"])
    ).fetchone()

    if not category:
        conn.close()
        flash("Category not found ❌", "error")
        return redirect(url_for("categories"))

    if request.method == "POST":
        new_name = request.form["name"].strip()

        if not new_name:
            flash("Category name required ❌", "error")
            return redirect(url_for("edit_category", id=id))

        try:
            conn.execute(
                "UPDATE categories SET name=? WHERE id=? AND user_id=?",
                (new_name, id, session["user_id"])
            )
            conn.commit()
            flash("Category updated ✅", "success")
        except:
            flash("Category already exists ❌", "error")

        conn.close()
        return redirect(url_for("categories"))

    conn.close()
    return render_template("edit_category.html", category=category)

# ---------------- DELETE CATEGORY ----------------
@app.route("/categories/delete/<int:id>")
def delete_category(id):
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    conn.execute(
        "DELETE FROM categories WHERE id=? AND user_id=?",
        (id, session["user_id"])
    )
    conn.commit()
    conn.close()

    flash("Category deleted 🗑️", "success")
    return redirect(url_for("categories"))


# ---------------- MONTHLY CHART ----------------
@app.route("/chart")
def chart():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    data = conn.execute(
        """
        SELECT substr(date, 1, 7) AS month,
               SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?
        GROUP BY month
        ORDER BY month
        """,
        (session["user_id"],)
    ).fetchall()
    conn.close()

    months = [row["month"] for row in data]
    totals = [row["total"] for row in data]

    return render_template("chart.html", months=months, totals=totals)

# ---------------- CATEGORY WISE PIE CHART ----------------
@app.route("/category-chart")
def category_chart():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()

    data = conn.execute(
        """
        SELECT category, SUM(amount) AS total
        FROM expenses
        WHERE user_id = ?
        GROUP BY category
        """,
        (session["user_id"],)
    ).fetchall()

    conn.close()

    categories = [row["category"] for row in data]
    totals = [row["total"] for row in data]

    return render_template(
        "category_chart.html",
        categories=categories,
        totals=totals
    )

# ---------------- ANALYTICS DASHBOARD ----------------
@app.route("/analytics")
def analytics():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    # ✅ Month selector value
    selected_month = request.args.get("month", "all")

    conn = get_db_connection()

    # ✅ Available months list (Dropdown)
    months_list = conn.execute("""
        SELECT DISTINCT substr(date,1,7) AS month
        FROM expenses
        WHERE user_id=?
        ORDER BY month DESC
    """, (user_id,)).fetchall()
    months_list = [row["month"] for row in months_list]

    # ✅ Filter condition
    month_condition = ""
    params = [user_id]

    if selected_month != "all":
        month_condition = " AND substr(date,1,7) = ? "
        params.append(selected_month)

    # ✅ Monthly totals (Line chart)
    monthly_data = conn.execute(f"""
        SELECT substr(date,1,7) as month, SUM(amount) as total
        FROM expenses
        WHERE user_id = ? {month_condition}
        GROUP BY month
        ORDER BY month
    """, tuple(params)).fetchall()

    months = [row["month"] for row in monthly_data]
    monthly_totals = [row["total"] for row in monthly_data]

    # ✅ Category totals (Bar chart)
    category_data = conn.execute(f"""
        SELECT category, SUM(amount) as total
        FROM expenses
        WHERE user_id = ? {month_condition}
        GROUP BY category
        ORDER BY total DESC
        LIMIT 6
    """, tuple(params)).fetchall()

    categories = [row["category"] for row in category_data]
    category_totals = [row["total"] for row in category_data]

    # ✅ Overall Total
    overall_total = conn.execute(f"""
        SELECT IFNULL(SUM(amount), 0)
        FROM expenses
        WHERE user_id = ? {month_condition}
    """, tuple(params)).fetchone()[0]

    # ✅ Avg daily spending
    avg_daily = conn.execute(f"""
        SELECT IFNULL(AVG(daily_total), 0) 
        FROM (
            SELECT date, SUM(amount) as daily_total
            FROM expenses
            WHERE user_id = ? {month_condition}
            GROUP BY date
        )
    """, tuple(params)).fetchone()[0]

    # ✅ Highest expense day
    best_day = conn.execute(f"""
        SELECT date, SUM(amount) as total
        FROM expenses
        WHERE user_id = ? {month_condition}
        GROUP BY date
        ORDER BY total DESC
        LIMIT 1
    """, tuple(params)).fetchone()

    # ✅ Top category
    top_category = conn.execute(f"""
        SELECT category, SUM(amount) as total
        FROM expenses
        WHERE user_id = ? {month_condition}
        GROUP BY category
        ORDER BY total DESC
        LIMIT 1
    """, tuple(params)).fetchone()

    conn.close()

    highest_day = best_day["date"] if best_day else "-"
    highest_day_amount = best_day["total"] if best_day else 0

    top_cat_name = top_category["category"] if top_category else "-"
    top_cat_amount = top_category["total"] if top_category else 0

    currency_code, currency_symbol, rate = get_currency()

    return render_template(
        "analytics.html",
        months=months,
        monthly_totals=monthly_totals,
        categories=categories,
        category_totals=category_totals,
        overall_total=overall_total,
        avg_daily=round(avg_daily, 2),
        highest_day=highest_day,
        highest_day_amount=highest_day_amount,
        top_cat_name=top_cat_name,
        top_cat_amount=top_cat_amount,
        months_list=months_list,              
        selected_month=selected_month,
        currency_code=currency_code,
        currency_symbol=currency_symbol
    )


# ---------------- DATE FILTER ----------------
@app.route("/filter", methods=["GET", "POST"])
def filter_expenses():
    if "user_id" not in session:
        return redirect(url_for("login"))

    expenses = []
    total = 0
    from_date = ""
    to_date = ""

    if request.method == "POST":
        from_date = request.form["from_date"]
        to_date = request.form["to_date"]

        conn = get_db_connection()
        expenses = conn.execute(
            """
            SELECT date, amount, category, note
            FROM expenses
            WHERE user_id = ?
            AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            (session["user_id"], from_date, to_date)
        ).fetchall()

        total = conn.execute(
            """
            SELECT IFNULL(SUM(amount), 0)
            FROM expenses
            WHERE user_id = ?
            AND date BETWEEN ? AND ?
            """,
            (session["user_id"], from_date, to_date)
        ).fetchone()[0]

        conn.close()

    return render_template(
        "filter.html",
        expenses=expenses,
        total=total,
        from_date=from_date,
        to_date=to_date
    )
# ---------------- EXPORT CSV ----------------
@app.route("/export-csv")
def export_csv():
    if "user_id" not in session:
        return redirect(url_for("login"))

    conn = get_db_connection()
    expenses = conn.execute(
        """
        SELECT date, amount, category, note
        FROM expenses
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchall()
    conn.close()

    def generate():
        yield "Date,Amount,Category,Note\n"
        for e in expenses:
            yield f"{e['date']},{e['amount']},{e['category']},{e['note']}\n"

    return app.response_class(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment;filename=expenses.csv"}
    )

# ---------------- EXPORT PDF ----------------
@app.route("/export-pdf")
def export_pdf():
    if "user_id" not in session:
        return redirect(url_for("login"))

    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    conn = get_db_connection()
    expenses = conn.execute(
        """
        SELECT date, amount, category, note
        FROM expenses
        WHERE user_id = ?
        """,
        (session["user_id"],)
    ).fetchall()
    conn.close()

    file_path = "expenses.pdf"
    c = canvas.Canvas(file_path, pagesize=A4)
    width, height = A4

    y = height - 40
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, "Expense Report")
    y -= 30

    c.setFont("Helvetica", 10)
    for e in expenses:
        line = f"{e['date']} | ₹{e['amount']} | {e['category']} | {e['note']}"
        c.drawString(40, y, line)
        y -= 15

        if y < 40:
            c.showPage()
            c.setFont("Helvetica", 10)
            y = height - 40

    c.save()

    return send_file(file_path, as_attachment=True)

# ---------------- PDF GENERATION FUNCTION ----------------
def generate_pdf(start_date, end_date, pdf_path):
    conn = get_db_connection()

    expenses = conn.execute(
        """
        SELECT date, amount, category, note
        FROM expenses
        WHERE user_id = ?
        AND date BETWEEN ? AND ?
        ORDER BY date
        """,
        (session["user_id"], start_date, end_date)
    ).fetchall()

    conn.close()

    doc = SimpleDocTemplate(pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Title
    elements.append(Paragraph("Expense Report", styles["Title"]))
    elements.append(
        Paragraph(f"From <b>{start_date}</b> To <b>{end_date}</b>", styles["Normal"])
    )
    elements.append(Paragraph("<br/>", styles["Normal"]))

    # Table data
    data = [["Date", "Amount", "Category", "Note"]]
    total = 0

    for e in expenses:
        data.append([
            e["date"],
            f"₹ {e['amount']}",
            e["category"],
            e["note"] or ""
        ])
        total += e["amount"]

    data.append(["", "", "Total", f"₹ {total}"])

    table = Table(data, colWidths=[80, 80, 100, 180])
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.darkblue),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.whitesmoke),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("FONT", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BACKGROUND", (0, 1), (-1, -2), colors.beige),
        ("BACKGROUND", (-2, -1), (-1, -1), colors.lightgrey),
        ("FONT", (-2, -1), (-1, -1), "Helvetica-Bold"),
    ]))

    elements.append(table)
    doc.build(elements)


# ---------------- EXPORT PDF (DATE RANGE) ----------------
@app.route("/export-pdf-range", methods=["GET", "POST"])
def export_pdf_range():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        from_date = request.form["from_date"]
        to_date = request.form["to_date"]

        if not from_date or not to_date:
            flash("Please select both dates ❗", "error")
            return redirect(url_for("export_pdf_range"))

        from reportlab.lib.pagesizes import A4
        from reportlab.pdfgen import canvas

        conn = get_db_connection()
        expenses = conn.execute(
            """
            SELECT date, amount, category, note
            FROM expenses
            WHERE user_id = ?
            AND date BETWEEN ? AND ?
            ORDER BY date
            """,
            (session["user_id"], from_date, to_date)
        ).fetchall()
        conn.close()

        file_path = f"expenses_{from_date}_to_{to_date}.pdf"
        c = canvas.Canvas(file_path, pagesize=A4)
        width, height = A4

        y = height - 40
        c.setFont("Helvetica-Bold", 16)
        c.drawString(40, y, "Expense Report")
        y -= 20

        c.setFont("Helvetica", 10)
        c.drawString(40, y, f"From: {from_date}   To: {to_date}")
        y -= 30

        total = 0
        for e in expenses:
            line = f"{e['date']} | ₹{e['amount']} | {e['category']} | {e['note']}"
            c.drawString(40, y, line)
            total += e["amount"]
            y -= 15

            if y < 40:
                c.showPage()
                c.setFont("Helvetica", 10)
                y = height - 40

        y -= 20
        c.setFont("Helvetica-Bold", 12)
        c.drawString(40, y, f"Total Expense: ₹ {total}")

        c.save()

        return send_file(file_path, as_attachment=True)

    return render_template("export_pdf_range.html")

# ---------------- PDF PREVIEW ----------------
@app.route('/export-pdf-preview', methods=['POST'])
def export_pdf_preview():
    start_date = request.form['start_date']
    end_date = request.form['end_date']

    REPORT_FOLDER = os.path.join(app.root_path, 'static', 'reports')
    os.makedirs(REPORT_FOLDER, exist_ok=True)

    filename = f"expense_{start_date}_to_{end_date}.pdf"
    pdf_path = os.path.join(REPORT_FOLDER, filename)

    generate_pdf(start_date, end_date, pdf_path)

    return render_template(
        "pdf_preview.html",
        pdf_file=f"static/reports/{filename}"
    )

# ---------------- BACKUP SETTINGS ----------------
BACKUP_FOLDER = os.path.join(app.root_path, "backups")
os.makedirs(BACKUP_FOLDER, exist_ok=True)

# ✅ Backup Download
@app.route("/backup")
def backup():
    if "user_id" not in session:
        return redirect(url_for("login"))

    user_id = session["user_id"]

    conn = get_db_connection()
    expenses = conn.execute("""
        SELECT date, amount, category, note
        FROM expenses
        WHERE user_id=?
        ORDER BY date
    """, (user_id,)).fetchall()
    conn.close()

    backup_data = {
        "user": session.get("user"),
        "user_id": user_id,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "expenses": []
    }

    for e in expenses:
        backup_data["expenses"].append({
            "date": e["date"],
            "amount": e["amount"],
            "category": e["category"],
            "note": e["note"]
        })

    os.makedirs("backups", exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"backup_user_{user_id}_{timestamp}.json"
    filepath = os.path.join("backups", filename)

    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(backup_data, f, indent=4)

    flash("Backup created successfully ✅", "success")
    return send_file(filepath, as_attachment=True)

# ✅ Restore Upload Form
@app.route("/restore", methods=["GET", "POST"])
def restore():
    if "user_id" not in session:
        return redirect(url_for("login"))

    if request.method == "POST":
        if "backup_file" not in request.files:
            flash("No file selected ❌", "error")
            return redirect(url_for("restore"))

        file = request.files["backup_file"]
        if file.filename == "":
            flash("No file selected ❌", "error")
            return redirect(url_for("restore"))

        filename = secure_filename(file.filename)

        if not filename.endswith(".json"):
            flash("Only .json backup file allowed ❌", "error")
            return redirect(url_for("restore"))

        os.makedirs("backups", exist_ok=True)
        temp_path = os.path.join("backups", filename)
        file.save(temp_path)

        # ✅ Load JSON backup
        with open(temp_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if "expenses" not in data:
            flash("Invalid backup file ❌", "error")
            return redirect(url_for("restore"))

        conn = get_db_connection()

        # ✅ Restore expenses into CURRENT user only
        current_user_id = session["user_id"]

        # Optional: clear old expenses first (you can remove this if you want merge)
        conn.execute("DELETE FROM expenses WHERE user_id=?", (current_user_id,))

        for e in data["expenses"]:
            conn.execute("""
                INSERT INTO expenses (user_id, date, amount, category, note)
                VALUES (?, ?, ?, ?, ?)
            """, (
                current_user_id,
                e.get("date"),
                e.get("amount"),
                e.get("category"),
                e.get("note")
            ))

        conn.commit()
        conn.close()

        flash("Backup restored successfully ✅", "success")
        return redirect(url_for("view_expenses"))

    return render_template("restore.html")

# ---------------- LOGOUT ----------------
@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully 👋", "success")
    return redirect(url_for("login"))


# ---------------- ERROR HANDLERS ----------------
# ✅ Custom Error Pages
@app.errorhandler(404)
def page_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def internal_server_error(e):
    return render_template("500.html"), 500


# ✅ Test routes (optional)
@app.route("/test404")
def test404():
    return "This route intentionally not found", 404

@app.route("/test500")
def test500():
    1/0

if __name__ == "__main__":
    init_logs_table()
    app.run(host="0.0.0.0", port=5000, debug=False)



