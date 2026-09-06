from app.db.database import Database, get_mongodb_uri

# Alias MongoDB to Database for backward compatibility across modules
MongoDB = Database

__all__ = ["Database", "MongoDB", "get_mongodb_uri"]
