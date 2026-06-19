from flask import Flask
from routes import register_routes
import sqlite3

def get_db_connection():
    conn = sqlite3.connect('notes.db')
    return conn

def create_app():
    app = Flask(__name__)
    
    # Call the function to initialize DB connections and tables before running application
    init_db(get_db_connection())
    
    register_routes(app)
    
    return app