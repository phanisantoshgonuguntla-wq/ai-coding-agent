def get_db_connection():
    conn = sqlite3.connect('database.db')
    db.row_factory = sqlite3.Row
    return conn

file: backend/models.py (commented out as it's not needed for this simple project)

from sqlalch0emy import Column, Integer, String
import uuid
from models import BaseModel
BaseClass=BaseModel()
class Item(BaseClass):
    __tablename__ = 'items'
    
    id = Column(Integer(), primary_key=True)
    title = Column(String(120), index=True, unique=True, nullable=False)
    description = Column(String())