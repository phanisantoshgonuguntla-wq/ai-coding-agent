from flask import url_for, redirect, render_template

def register_routes(app):
    # Define the route for index page which is rendered by 'index.html' template
    @app.route("/")
    def home():
        return render_template("index.html")