import datetime

import matplotlib.pyplot as plt
import yfinance as yf
from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from werkzeug.security import check_password_hash, generate_password_hash

from flask_session import Session
from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")


@app.after_request
def after_request(response):
    """Ensure responses aren't cached"""
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    transactions = db.execute(
        "SELECT SUM(quantity) AS total_quantity, symbol FROM 'Transaction' WHERE userID = (?) AND type != 'fee' GROUP BY symbol HAVING total_quantity > 0 ORDER BY symbol",
        session["user_id"])
    cash = db.execute("SELECT cash FROM 'users' WHERE id = (?)", session["user_id"])[0]["cash"]
    stockvalue = 0.0

    for transaction in transactions:
        transaction["current_price"] = lookup(transaction["symbol"])["price"]
        transaction["value"] = transaction["total_quantity"] * transaction["current_price"]
        stockvalue += transaction["value"]

        # Calculate the average buy cost for each stock - weighted average, as not every quantity is equal
        total_quantity = 0.0
        total_price = 0.0
        calc = db.execute(
            "SELECT price, quantity FROM 'Transaction' WHERE userID = (?) AND symbol = (?) AND type = 'buy'",
            session["user_id"], transaction["symbol"])

        for c in calc:
            total_quantity += c["quantity"]
            total_price += c["price"] * c["quantity"]

        transaction["avg_price"] = total_price / total_quantity
        transaction["purchase_value"] = transaction["total_quantity"] * transaction["avg_price"]
        transaction["current_value"] = transaction["total_quantity"] * transaction["current_price"]
        transaction["difference"] = f"{transaction['current_value'] * 100 / transaction['purchase_value'] - 100:.2f}"

    total = (cash + stockvalue)

    return render_template("index.html", cash=cash, stockvalue=stockvalue, total=total, transactions=transactions)


@app.route("/settings", methods=["GET"])
@login_required
def settings():
    """Settings page"""
    buy_tax = db.execute("SELECT buy_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["buy_tax"]
    sell_tax = db.execute("SELECT sell_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["sell_tax"]
    fee = db.execute("SELECT account_fee FROM 'users' WHERE id = (?)", session["user_id"])[0]["account_fee"]

    return render_template("settings.html", buy_tax=buy_tax, sell_tax=sell_tax, fee=fee)


@app.route("/buy-tax", methods=["POST"])
@login_required
def buy_tax():
    """Change buy tax percentage"""
    tax = request.form.get("buy-tax")

    if tax == None:
        return apology("invalid tax", 400)

    if not tax.isdigit() or int(tax) < 0:
        return apology("tax must be a positive integer", 400)

    db.execute("UPDATE 'users' SET buy_tax = (?) WHERE id = (?)", tax, session["user_id"])

    flash(f"Successfully updated buy tax to {tax}%!")

    buy_tax = db.execute("SELECT buy_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["buy_tax"]
    sell_tax = db.execute("SELECT sell_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["sell_tax"]
    fee = db.execute("SELECT account_fee FROM 'users' WHERE id = (?)", session["user_id"])[0]["account_fee"]

    return render_template("settings.html", buy_tax=buy_tax, sell_tax=sell_tax, fee=fee)


@app.route("/sell-tax", methods=["POST"])
@login_required
def sell_tax():
    """Change sell tax percentage"""
    tax = request.form.get("sell-tax")

    if tax == None:
        return apology("invalid tax", 400)

    if not tax.isdigit() or int(tax) < 0:
        return apology("tax must be a positive integer", 400)

    db.execute("UPDATE 'users' SET sell_tax = (?) WHERE id = (?)", tax, session["user_id"])

    flash(f"Successfully updated sell tax to {tax}%!")

    buy_tax = db.execute("SELECT buy_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["buy_tax"]
    sell_tax = db.execute("SELECT sell_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["sell_tax"]
    fee = db.execute("SELECT account_fee FROM 'users' WHERE id = (?)", session["user_id"])[0]["account_fee"]

    return render_template("settings.html", buy_tax=buy_tax, sell_tax=sell_tax, fee=fee)


@app.route("/account-fee", methods=["POST"])
@login_required
def account_fee():
    """Change account fee percentage"""
    fee = request.form.get("account-fee")

    if fee == None:
        return apology("invalid fee", 400)

    if not fee.isdigit() or int(fee) < 0:
        return apology("fee must be a positive integer", 400)

    db.execute("UPDATE 'users' SET account_fee = (?) WHERE id = (?)", fee, session["user_id"])

    flash(f"Successfully updated the yearly account fee to {fee}$!")

    buy_tax = db.execute("SELECT buy_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["buy_tax"]
    sell_tax = db.execute("SELECT sell_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["sell_tax"]
    fee = db.execute("SELECT account_fee FROM 'users' WHERE id = (?)", session["user_id"])[0]["account_fee"]

    return render_template("settings.html", buy_tax=buy_tax, sell_tax=sell_tax, fee=fee)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    if request.method == "POST":
        buy = lookup(request.form.get("symbol"))

        if buy == None:
            return apology("invalid symbol", 400)

        user_id = session["user_id"]
        # name = buy["name"].upper()
        price = buy["price"]
        shares = request.form.get("shares")
        symbol = request.form.get("symbol").upper()

        if not shares.isdigit() or int(shares) <= 0:
            return apology("share amount must be a positive integer", 400)

        shares = int(shares)
        cash_db = db.execute("SELECT cash, buy_tax FROM users WHERE id = (?)", user_id)
        user_cash = (cash_db[0]["cash"])
        buy_tax = (cash_db[0]["buy_tax"])
        purchase = price * shares
        purchase *= 1.0 + buy_tax / 100.0
        update_user_cash = user_cash - purchase

        if user_cash < purchase:
            return apology("insufficient fund in your account", 400)

        db.execute("UPDATE users SET cash = (?) WHERE id = (?);", update_user_cash, user_id)
        db.execute(
            "INSERT INTO 'Transaction' (userID, symbol, name, quantity, price, type, tax) VALUES (?, ?, ?, ?, ?, ?, ?)",
            user_id, symbol, symbol, shares, price, "buy", (price * shares * buy_tax / 100.0))

        flash(f"Successfully bought {shares} shares of {symbol} at {price} for {purchase:.2f} (with tax)!")

        return redirect("/")

    return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    transactions = db.execute("SELECT * FROM 'Transaction' WHERE userID = (?)", session["user_id"])

    return render_template("history.html", transactions=transactions)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Check if yearly fee has to be paid (retrieve current year)
        year_last_fee = db.execute("SELECT year_last_fee FROM 'users' WHERE id = (?)", session["user_id"])[0][
            "year_last_fee"]
        current_year = datetime.date.today().year

        if year_last_fee < current_year:
            account_fee = db.execute("SELECT account_fee FROM 'users' WHERE id = (?)", session["user_id"])[0][
                "account_fee"]
            cash = db.execute("SELECT cash FROM 'users' WHERE id = (?)", session["user_id"])[0]["cash"]
            cash -= account_fee
            db.execute("UPDATE 'users' SET cash = (?), year_last_fee = (?) WHERE id = (?)", cash, current_year,
                       session["user_id"])
            # Insert into transaction history
            db.execute(
                "INSERT INTO 'Transaction' (userID, symbol, name, quantity, price, type) VALUES (?, ?, ?, ?, ?, ?)",
                session["user_id"], "account_fee", "account_fee", 1, account_fee, "fee")

            flash(f"Yearly account fee of {account_fee}$ has been deducted from your account!")

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure symbol was submitted
        if not request.form.get("symbol"):
            return apology("must provide symbol", 400)

        symbol = request.form.get("symbol")

        if lookup(symbol) is None:
            return apology("symbol cannot be found", 400)

        session["symbol"] = lookup(symbol)["price"]

        data = yf.Ticker(symbol)

        # Fetch key data
        country = data.info['country']
        state = data.info['state']
        website = data.info['website']
        sector = data.info['sector']
        marketCap = human_readable(data.info['marketCap'])
        fiftyTwoWeekHigh = data.info['fiftyTwoWeekHigh']
        fiftyTwoWeekLow = data.info['fiftyTwoWeekLow']
        currency = data.info['currency']
        longName = data.info['longName']
        open = data.info['open']
        dayLow = data.info['dayLow']
        dayHigh = data.info['dayHigh']

        # Fetch historical data for the last year
        df = data.history(period="1y")

        # Plot the historical data using matplotlib
        plt.figure(figsize=(14, 7))
        plt.plot(df.index, df['Open'])
        plt.xlabel('Date')
        plt.ylabel('Open Price')
        plt.title('1y price history for ' + symbol + ' in ' + currency)
        plt.grid(True)
        plt.savefig('static/plot.png')

        flash(f"Fetched price for {symbol}: {session["symbol"]} {currency}!")

        # Redirect user to home page
        return render_template("quoted.html", symbol=symbol, price=session["symbol"], country=country, state=state,
                               website=website, sector=sector, marketCap=marketCap, fiftyTwoWeekHigh=fiftyTwoWeekHigh,
                               fiftyTwoWeekLow=fiftyTwoWeekLow, currency=currency, longName=longName, open=open,
                               dayLow=dayLow, dayHigh=dayHigh)

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


def human_readable(num):
    magnitude = 0
    while abs(num) >= 1000:
        magnitude += 1
        num /= 1000.0
    return '%.2f%s' % (num, [' ', ' Thousand', ' Million', ' Billion', ' Trillion'][magnitude])


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user account"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation was submitted
        elif not request.form.get("confirmation"):
            return apology("must provide password confirmation", 400)

        # Ensure password and confirmation are equal
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 400)

        # Query database for username
        rows = db.execute("SELECT * FROM Users WHERE username = ?", request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 0:
            return apology("username already exists", 400)

        username = request.form.get("username")
        hash = generate_password_hash(request.form.get("password"))

        db.execute("INSERT INTO Users (username, hash) VALUES (?, ?)", username, hash)

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    if request.method == "GET":
        symbols = db.execute(
            "SELECT symbol FROM 'Transaction' WHERE userID = (?) AND type != 'fee' GROUP BY symbol HAVING SUM(quantity) > 0",
            session["user_id"])

        return render_template("sell.html", symbols=symbols)

    if not request.form.get("symbol"):
        return apology("must provide symbol", 403)

    symbol = request.form.get("symbol")
    if symbol == None:
        return apology("invalid symbol")

    shares = int(request.form.get("shares"))
    if shares <= 0:
        return apology("share amount to sell must be positive")

    stockdata = lookup(symbol)
    price = stockdata["price"]

    query = db.execute("SELECT cash, sell_tax FROM 'users' WHERE id = (?)", session["user_id"])
    user_cash = query[0]["cash"]
    sell_tax = query[0]["sell_tax"]
    share_quantity = db.execute(
        "SELECT symbol, SUM(quantity) AS total_quantity FROM 'Transaction' WHERE userID = (?) AND symbol = (?)",
        session["user_id"], symbol)[0]["total_quantity"]
    if shares > share_quantity:
        return apology(f"insufficient share quantity to sell {share_quantity} pieces")

    # Get average buy price for the stock
    transactions = db.execute(
        "SELECT SUM(quantity) AS total_quantity, symbol FROM 'Transaction' WHERE userID = (?) AND symbol = (?) AND type != 'fee' GROUP BY symbol HAVING total_quantity > 0 ORDER BY symbol",
        session["user_id"], symbol)
    stockvalue = 0.0
    for transaction in transactions:
        transaction["current_price"] = lookup(transaction["symbol"])["price"]
        transaction["value"] = transaction["total_quantity"] * transaction["current_price"]
        stockvalue += transaction["value"]

        # Calculate the average buy cost for each stock - weighted average, as not every quantity is equal
        total_quantity = 0.0
        total_price = 0.0
        calc = db.execute(
            "SELECT price, quantity FROM 'Transaction' WHERE userID = (?) AND symbol = (?) AND type = 'buy'",
            session["user_id"], transaction["symbol"])

        for c in calc:
            total_quantity += c["quantity"]
            total_price += c["price"] * c["quantity"]

        transaction["avg_price"] = total_price / total_quantity
        transaction["purchase_value"] = transaction["total_quantity"] * transaction["avg_price"]

    avg_price = transactions[0]["avg_price"]

    if price <= avg_price:
        selling_price = price * shares
        user_cash += selling_price

        db.execute("UPDATE 'users' SET cash = (?) WHERE id = (?)", user_cash, session["user_id"])
        db.execute("INSERT INTO 'Transaction' (userID, symbol, name, quantity, price, type) VALUES (?, ?, ?, ?, ?, ?)",
                   session["user_id"], symbol, symbol, shares * (-1), price, "sell")

        flash(f"Successfully sold {shares} shares of {symbol} at {price} (no tax)!")

        return redirect("/")

    sell_tax = db.execute("SELECT sell_tax FROM 'users' WHERE id = (?)", session["user_id"])[0]["sell_tax"]

    purchase_price = avg_price * shares
    sell_price = price * shares
    profit = sell_price - purchase_price
    tax = profit * sell_tax / 100.0
    user_cash = user_cash + sell_price - tax

    db.execute("UPDATE 'users' SET cash = (?) WHERE id = (?)", user_cash, session["user_id"])
    db.execute(
        "INSERT INTO 'Transaction' (userID, symbol, name, quantity, price, type, tax) VALUES (?, ?, ?, ?, ?, ?, ?)",
        session["user_id"], symbol, symbol, shares * (-1), price, "sell", tax)

    flash(f"Successfully sold {shares} shares of {symbol} at {price} (with tax totaling {tax:.2f})!")

    return redirect("/")


@app.route("/cash", methods=["GET", "POST"])
@login_required
def add_cash():
    """Add cash to user account"""

    if request.method == "POST":
        amount = request.form.get("amount")

        if amount == None:
            return apology("invalid amount", 403)

        if not amount.isdigit() or int(amount) <= 0:
            return apology("amount must be a positive integer")

        new_balance = db.execute("SELECT cash FROM users where id = (?)", session["user_id"])[0]["cash"] + int(amount)

        db.execute("UPDATE 'users' SET cash = (?) WHERE id = (?);", new_balance, session["user_id"])

        flash(f"Successfully added {amount}$ to balance!")

        return redirect("/")

    return render_template("cash.html")
