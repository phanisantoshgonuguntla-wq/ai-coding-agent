from flask import request, jsonify
from models import get_items, add_item


def register_routes(app):

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        return response

    @app.route("/api/todos", methods=["GET"])
    def list_items():
        return jsonify(get_items())

    @app.route("/api/items", methods=["POST", "OPTIONS"])
    def create_item():
        if request.method == "OPTIONS":
            return jsonify({}), 200

        data = request.get_json() or {}
        title = data.get("title")
        description = data.get("description", "")

        if not title:
            return jsonify({"error": "title is required"}), 400

        add_item(title, description)
        return jsonify({"message": "item added"}), 201