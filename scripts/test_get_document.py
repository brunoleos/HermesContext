#!/usr/bin/env python3
"""Test rag_get_document endpoint"""
from src.database import Database
db = Database()
db.connect()
doc = db.get_document(44)  # Use document ID from test 2
import json
print(json.dumps(doc, indent=2, default=str))
db.close()
