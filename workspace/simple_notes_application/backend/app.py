from flask import Flask
from routes import register_routes
from database import init_db

app = Flask(__name__)

init_db()
register_routes(app)

@app.after_request
def add_cors_headers(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
    return response

if __name__ == "__main__":
    app.run(debug=True)