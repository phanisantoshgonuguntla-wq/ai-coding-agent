from flask import Flask
from routes import register_routes
from database import init_db
import pandas
import requests

app = Flask(__name__)

init_db()
register_routes(app)

if __name__ == "__main__":
    app.run(debug=True)