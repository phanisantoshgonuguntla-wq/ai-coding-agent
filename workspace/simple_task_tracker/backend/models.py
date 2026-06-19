
from database import get_connection


def get_items():
    connection = get_connection()
    items = connection.execute(
        "SELECT id, title, description FROM items ORDER BY id DESC"
    ).fetchall()
    connection.close()
    return [dict(item) for item in items]


def add_item(title, description=""):
    connection = get_connection()
    connection.execute(
        "INSERT INTO items (title, description) VALUES (?, ?)",
        (title, description)
    )
    connection.commit()
    connection.close()
