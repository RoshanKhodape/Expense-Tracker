# Expense Tracker Web App (Flask + SQLite)

A complete Expense Tracker Web Application built using:
- Flask (Python)
- SQLite Database
- Email OTP verification
- Forgot Password with expiry + attempts
- Analytics Dashboard (Charts)
- Currency support
- Backup & Restore
- Category management

---

## ✅ Features
- Register + Email OTP verification
- Login system with sessions
- Add / Edit / Delete expenses
- Category management (Add/Edit/Delete)
- Analytics page (Monthly trend + category chart)
- Currency selector (INR/USD/EUR/GBP)
- Export CSV
- Export PDF
- Forgot password OTP reset
- Backup & restore (JSON)
- Custom Error Pages (404 / 500)
- Logging system (login attempts / deletions / password reset)

---

## ✅ How to Run (Windows)

### 1) Extract ZIP
Extract the downloaded file.
### 2) Open Terminal in project folder
    Example:
    ```bash
    cd expense_tracker_web

### 3) Create virtual environment (recommended)
python -m venv venv
venv\Scripts\activate

### 4) Install requirements
 pip install -r requirements.txt

### 5) Create database
Run:
python database.py

### 6) Setup Email OTP (.env file)
Create a file named .env in the root folder:
EMAIL_USER=your_email@gmail.com
EMAIL_PASS=your_gmail_app_password

NOTE: Use Gmail App Password (Not normal Gmail password)

### 7) Run Flask app
python app.py

### 8) Open browser
Go to:
http://127.0.0.1:5000