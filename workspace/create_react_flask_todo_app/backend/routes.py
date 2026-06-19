from flask import jsonify, request

from database import get_db


def register_routes(app):

    @app.after_request
    def add_cors_headers(response):
        response.headers["Access-Control-Allow-Origin"] = "*"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
        return response

    @app.route("/todo", methods=["GET"])
    def list_todos():
        db = get_db()

        cursor = db.execute(
            "SELECT id, title FROM todo"
        )

        todos = [
            {
                "id": row["id"],
                "title": row["title"]
            }
            for row in cursor.fetchall()
        ]

        db.close()

        return jsonify(todos)

    @app.route("/todo", methods=["POST", "OPTIONS"])
    def create_todo():
        if request.method == "OPTIONS":
            return jsonify({}), 200

        data = request.get_json()

        if not data or "title" not in data:
            return jsonify({
                "error": "title is required"
            }), 400

        db = get_db()

        cursor = db.execute(
            "INSERT INTO todo (title) VALUES (?)",
            [data["title"]]
        )

        db.commit()

        todo_id = cursor.lastrowid

        db.close()

        return jsonify({
            "id": todo_id,
            "title": data["title"]
        }), 201