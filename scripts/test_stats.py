from src.database import Database
db = Database()
db.connect()
stats = db.get_stats()
import json
print(json.dumps(stats, indent=2))
db.close()
