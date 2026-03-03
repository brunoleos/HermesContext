#!/usr/bin/env python3
"""Test rag_list_documents endpoint"""
from src.database import Database
db = Database()
db.connect()
data = db.list_documents(limit=5)
import json
print(json.dumps(data, indent=2, default=str))
db.close()
