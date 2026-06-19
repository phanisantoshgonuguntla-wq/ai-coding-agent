
from database import get_connection


def get_items():
    connection = get_connection()
    items = connection.execute(
        "SELECT id, title, description, email, phone FROM items ORDER BY id DESC"
    ).fetchall()
    connection.close()
    return [dict(item) for item in items]


def add_item(title, description="", email="", phone=""):
    connection = get_connection()
    connection.execute(
        "INSERT INTO items (title, description, email, phone) VALUES (?, ?, ?, ?)",
        (title, description, email, phone)
    )
    connection.commit()
    connection.close()
