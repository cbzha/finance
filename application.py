import os
import re

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    data = db.execute("SELECT DISTINCT symbol, SUM (shares) FROM transacs WHERE users_id = :id GROUP BY symbol;",
                 id = session["user_id"])

    # query the current money
    cash = db.execute("SELECT cash FROM users where id = :id", id = session["user_id"])

    sum = 0

    # adiciona a chave price com o valor atual da ação no dicionario
    for dicts in data:
        current = lookup(dicts['symbol'])
        dicts["price"] = current['price']
        sum += dicts['SUM (shares)'] * current['price']

    # cria uma lista somente com dicionarios cuja quantidade seja maior que zero. impede que liste ações que o usuário não tem
    lista = []
    for dicts in data:
        if dicts['SUM (shares)'] > 0:
            lista.append(dicts)

    return render_template("index.html", datas = lista, cash = cash[0]['cash'], sum = sum)


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    if request.method == "POST":
        if not request.form.get("symbol") or not request.form.get("shares") or lookup(request.form.get("symbol")) is None:
            return apology("must provide valid symbol and shares ", 403)

        # query the current money
        cash = db.execute("SELECT cash FROM users where id = :id", id = session["user_id"])

        # query company's data
        value = lookup(request.form.get("symbol"))

        if value["price"] * int(request.form.get("shares")) > cash[0]['cash']:
            return apology("you don't have enough money", 403)

        # update money for after purchase
        money = cash[0]['cash'] - (value["price"] * int(request.form.get("shares")))

        # update cash
        db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash = money, id = session["user_id"])

        # register the transacion
        db.execute("INSERT INTO transacs (symbol, shares, price, users_id) VALUES (:symbol, :shares, :price, :id)",
                shares = int(request.form.get("shares")), price = value["price"], symbol = request.form.get("symbol"), id = session["user_id"] )

        # Redirect user to home page
        return redirect("/")

    else:
        return render_template("buy.html")


@app.route("/history")
@login_required
def history():

    data = db.execute("SELECT symbol, shares, price, date FROM transacs WHERE users_id = :id;",
                 id = session["user_id"])

    return render_template("history.html", data = data)


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
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

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
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))
        if stock is None:
            return apology("stock name was invalid", 403)

        return render_template("quoted.html", stock = stock)

    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
# User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password") or not request.form.get("repeatedpassword"):
            return apology("must provide password", 403)

        password = request.form.get("password")
        repeatedpassword = request.form.get('repeatedpassword')

        #verifica se as senhas não batem
        if password != repeatedpassword:
            return apology("passwords does not match", 403)

        # regex para caracteres especiais
        regex = re.compile('[@_!#$%^&*()<>?/\|}{~:]')

        # verifica as caracteres especiais
        if  regex.search(request.form.get("password")) is None:
            return apology("password must contain a special character")

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # verifica se já existe um usuário com o nome oferecido
        if len(rows) > 0:
            return apology("sorry, there is already an user with the name provided", 403)

        # se passar em todas as validações, insere o usuário no banco
        db.execute("INSERT INTO users (username, hash) VALUES (:username, :password)",
            username=request.form.get("username"), password = generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    if request.method == "POST":
        if not request.form.get("symbol")  or not request.form.get("shares"):
            return apology("you must select a symbol and quantity of shares", 400)

        data = db.execute("SELECT DISTINCT symbol, SUM (shares), cash FROM users JOIN transacs ON users.id = transacs.users_id WHERE users.id = :id GROUP BY symbol;",
                 id = session["user_id"])

        # quantidade  a ser vendida
        shares = int (request.form.get("shares"))

        for dicts in data:
            if request.form.get("symbol") == dicts["symbol"]:
                if shares <= dicts["SUM (shares)"]:
                    value = lookup(request.form.get("symbol"))
                    newcash = shares * value["price"] + dicts["cash"]

                    # register the transacion
                    db.execute("INSERT INTO transacs (symbol, shares, price, users_id) VALUES (:symbol, :shares, :price, :id)",
                    shares = -int(request.form.get("shares")), price = value["price"], symbol = request.form.get("symbol"), id = session["user_id"] )

                    # update cash
                    db.execute("UPDATE users SET cash = :cash WHERE id = :id", cash = newcash, id = session["user_id"])
                    break
                else:
                    return apology("you dont have enough shares", 400)

        return redirect("/")


    else:
        lista = []
        data = db.execute("SELECT DISTINCT symbol, SUM (shares) FROM transacs WHERE users_id = :id GROUP BY symbol;",
                 id = session["user_id"])

        for dicts in data:
            if dicts['SUM (shares)'] > 0:
                lista.append(dicts['symbol'])

        return render_template("sell.html", data = lista)

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
