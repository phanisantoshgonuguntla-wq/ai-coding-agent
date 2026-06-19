from flask import Flask, jsonify
app = Flask(__name__)
todos = [
    {'id': 1, 'text': 'Do laundry', 'completed': False},
    {'id': 2, 'text': 'Buy groceries', 'completed': True}
]

@app.route('/api/todos')
def get_todos():
    return jsonify(todos)



#