import os

from cs50 import SQL
from flask import Flask, flash, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd, time

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

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


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

    # define variable user ID from session ID
    session_user_id = session["user_id"]

    # SQL query to get shares owned by current user
    shares_owned = db.execute(
        "SELECT stock_name, symbol, SUM(shares) FROM transactions WHERE username_id = (?) GROUP BY symbol HAVING SUM(shares) > 0", session_user_id)

    # SQL query to get User's cash balance in USD format
    cash_balance = db.execute("SELECT cash FROM users WHERE users.id = (?)", session_user_id)
    balance = cash_balance[0]["cash"]
    USD_balance = usd(balance)

    total_positions_value = 0

    # loop through dictionaires of currently owned stocks of user
    for share in shares_owned:
        # Call Lookup function to get current stock price using 'symbol' value from dict
        stock_lookup = lookup(share['symbol'])

        if not stock_lookup:
            break

        # Pull "price" from the dict the lookup function returns and store
        stock_price = stock_lookup["price"]

        # Convert to USD format
        usd_stock_price = usd(stock_price)

        # Store current stock price in current loops dictionary
        share["price"] = usd_stock_price

        # Calculate current value of shares owned, convert to USD, and store in current loops dict
        current_value = stock_price * share["SUM(shares)"]
        usd_current_value = usd(current_value)
        share["current_value"] = usd_current_value

        # add current share value to users total portfolio value
        total_positions_value += current_value

    # Calculate total value current user has (cash + positions)
    total_user_value = balance + total_positions_value
    usd_total_user_value = usd(total_user_value)

    return render_template("index.html", shares_owned=shares_owned, cash_balance=USD_balance, total_user_value=usd_total_user_value)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        # store share input into variable
        shares = request.form.get("shares")

        # Ensure shares is an whole, positive integer
        if not shares.isdigit():
            return apology("Shares must be a whole, positive, numerical number", 400)

        # Call lookup function passing in symbol entered by user
        stock = lookup(request.form.get("symbol"))

        # Ensure stock symbol exists
        if not stock:
            return apology("Stock Symbol doesn't exist", 400)

        # define variables to insert into database
        symbol = stock["symbol"]
        shares = int(request.form.get("shares"))
        price = int(stock["price"])
        stock_name = stock["name"]

        # Calculate stock purchase
        calculated_stock_purchase = price * shares

        # Ensure user has enough cash to purchase stock
        session_user_id = session["user_id"]
        user_cash = db.execute("SELECT cash FROM users WHERE users.id = (?)", session_user_id)
        if user_cash[0]["cash"] < calculated_stock_purchase:
            return apology("Cannot purchase stock, insufficient cash", 403)

        # INSERT transaction into Database
        db.execute("INSERT INTO transactions (username_id, symbol, shares, share_price, share_purchase_amount, stock_name, type) VALUES (?, ?, ?, ?, ?, ?, 'Buy')",
                   session_user_id, symbol, shares, price, calculated_stock_purchase, stock_name)

        # Subtract purchase from users cash balance
        new_cash_balance = user_cash[0]["cash"] - calculated_stock_purchase
        db.execute("UPDATE users SET cash = (?) WHERE users.id = (?)", new_cash_balance, session_user_id)

        # Store flash message to dispaly
        flash('Successfuly bought!')

        # redirect user to index page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    # define variable user ID from session ID
    session_user_id = session["user_id"]

    # SQL Query to get users transaction history
    transaction_history = db.execute(
        "SELECT stock_name, symbol, type, share_price, shares, share_purchase_amount, purchased_at FROM transactions WHERE username_id = (?)", session_user_id)

    # Loop through list of dictionairies of transactions
    for share in transaction_history:
        # Call USD function to format
        share['share_price'] = usd(share['share_price'])
        share['share_purchase_amount'] = usd(share['share_purchase_amount'])
        # format all shares to positive integer
        share['shares'] = abs(share['shares'])
        # format date time
        share['purchased_at'] = time(share['purchased_at'])

    # Render History html
    return render_template("history.html", transaction_history=transaction_history)


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

        # Call lookup function passing in symbol entered by user
        stock_quote = lookup(request.form.get("symbol"))

        # Ensure stock symbol exists
        if not stock_quote:
            return apology("Stock Symbol doesn't exist", 400)

        # Call USD formatting function
        stock_price = usd(stock_quote["price"])

        # Render Quoted webpage with values
        return render_template("quoted.html", name=stock_quote["name"], price=stock_price, symbol=stock_quote["symbol"])

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("quote.html")


@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 400)

        # Ensure username doesn't already exist
        usernames = db.execute("SELECT username FROM users")
        for username in usernames:
            if request.form.get("username") == username["username"]:
                return apology("Sorry username already exists", 400)

        # Ensure password was submitted
        if not request.form.get("password"):
            return apology("must provide password", 400)

        # Ensure password confirmation matches password
        if request.form.get("password") != request.form.get("confirmation"):
            return apology("confirmation must match password", 400)

        # define variable to store username and password of registrant
        submitted_username = request.form.get("username")
        password_hash = generate_password_hash(request.form.get("password"))

        # Insert username and password into database
        db.execute("INSERT INTO users (username, hash) VALUES (?, ?)", submitted_username, password_hash)
        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""
    # Define user id from session
    session_user_id = session["user_id"]

    if request.method == "POST":

        # Ensure shares is a positive number
        if int(request.form.get("shares")) < 0:
            return apology("Cannot sell negative stocks", 400)

        # Call lookup function passing in symbol entered by user
        stock = lookup(request.form.get("symbol"))

        # Ensure stock symbol exists
        if not stock:
            return apology("Stock Symbol doesn't exist", 400)

        # define variables to insert into database
        symbol = stock["symbol"]
        shares = int(request.form.get("shares"))
        price = int(stock["price"])
        stock_name = stock["name"]
        negative_shares = -abs(shares)

        # SQL Query to get User's cash balance
        user_cash = db.execute("SELECT cash FROM users WHERE users.id = (?)", session_user_id)

        # SQL queries to get shares owned by current user and current cash balance
        user_shares = db.execute(
            "SELECT stock_name, symbol, SUM(shares) FROM transactions WHERE username_id = (?) AND symbol = (?)", session_user_id, symbol)

        # Ensure user owns stock they are trying to sell
        found = False
        # Loop through list of dictionaries
        for share in user_shares:
            if share["symbol"] == symbol:
                found = True
                break

        # Throw error is symbol not found
        if found == False:
            return apology("Cannot sell stock you don't own", 400)

        # Ensure user has enough shares to sell
        if user_shares[0]["SUM(shares)"] < shares:
            return apology("Cannot sell stock, insufficient shares", 400)

        # Calculate stock sale
        calculated_stock_sale = price * shares

        # INSERT transaction into Database
        db.execute("INSERT INTO transactions (username_id, symbol, shares, share_price, share_purchase_amount, stock_name, type) VALUES (?, ?, ?, ?, ?, ?, 'Sell')",
                   session_user_id, symbol, negative_shares, price, calculated_stock_sale, stock_name)

        # Subtract purchase from user
        new_cash_balance = user_cash[0]["cash"] + calculated_stock_sale
        db.execute("UPDATE users SET cash = (?) WHERE users.id = (?)", new_cash_balance, session_user_id)

        # Store flash message to dispaly
        flash('Successfuly sold!')

        # redirect user to index page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        # SQL queries to get shares owned by current user and current cash balance
        user_shares = db.execute(
            "SELECT symbol FROM transactions WHERE username_id = (?) GROUP BY symbol", session_user_id)
        return render_template("sell.html", user_shares=user_shares)
