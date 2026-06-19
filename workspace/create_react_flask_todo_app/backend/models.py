from .database import get_db, connect_to_db

def init_db():
    with sqlite3.connect("todo.db") as conn:
        with closing(conn):
            cursorObj=conn.cursor()
            cursorObj.execute('''CREATE TABLE IF NOT EXISTS todo (
                                id INTEGER PRIMARY KEY, 
                                task TEXT NOT NULL)''' )