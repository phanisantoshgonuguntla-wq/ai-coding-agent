from flask import request, redirect, url_for
from app import app

todos = []

@app.route("/")
def home():
    return "Todo app is running"

@app.route("/add-todo", methods=["POST"])
def add_todo():
    todo = {
        "text": request.form["text"],
        "completed": False
    }
    todos.append(todo)
    return redirect(url_for("home"))