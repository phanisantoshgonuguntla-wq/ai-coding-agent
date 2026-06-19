from database import get_connection

def get_items():
    connection = get_connection()
    items = connection.execute("SELECT id, title FROM items ORDER BY id DESC").fetchall()
    connection.close()
    return items

def add_item(title):
    connection = get_connection()
    connection.execute("INSERT INTO items (title) VALUES (?)", (title,))
    connection.commit()
    connection.close()

def delete_item(item_id):
    connection = get_connection()
    connection.execute("DELETE FROM items WHERE id = ?", (item_id,))
    connection.commit()
    connection.close()