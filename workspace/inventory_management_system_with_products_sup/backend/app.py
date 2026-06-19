from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
from backend.database import get_db_connection, item_schema

app = Flask(__name__)
CORS(app)

@app.route('/api/items', methods=['GET'])
def get_items():
    conn = get_db_connection()
    cursor = conn.execute('SELECT * FROM items')
    results = [dict(zip([col[0] for col in cursor.description], row)) for row in cursor.fetchall()]
    return jsonify(results)

@app.route('/api/items', methods=['POST'])
def create_item():
    data = request.get_json()
    item = {
        'id': str(uuid.uuid5(Namespace, f"{data['title']}#{data['description']}")),
        **data
    }
    
    conn = get_db_connection()
    new_item = next((row for row in conn.execute('INSERT INTO items (id, title, description) VALUES (?, ?, ?)', 
                           [item['id'], item['title'], item['description']])), None)
    
    if not new_item:
        return jsonify({'error': 'Item already exists.'}), 409
        
    conn.commit()
    cursor = conn.execute('SELECT * FROM items WHERE id=?', [new_item['id']])
    item = dict(cursor.fetchone())
    
    return jsonify({'item': item})

def get_db_connection():
    db = sqlite3.connect('database.db')
    db.row_factory = sqlite3.Row
    return db