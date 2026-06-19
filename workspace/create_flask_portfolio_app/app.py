from flask import Flask

app = Flask(__name__)

from routes import register_routes

register_routes(app)

if __name__ == "__main__":
    app.run(debug=True)