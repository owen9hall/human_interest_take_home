"""Flask app factory and SQLite database setup."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import event
from sqlalchemy.engine import Engine
import sqlite3

db = SQLAlchemy()


@event.listens_for(Engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _record):
    if isinstance(dbapi_conn, sqlite3.Connection):
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA foreign_keys=ON") # enable foreign key enforcement
        cur.execute("PRAGMA journal_mode=WAL") # improve performance for concurrent writes
        cur.execute("PRAGMA busy_timeout=5000") # 5 second timeout for db operations
        cur.close()


def create_app(config: dict | None = None):
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hsa.db"
    app.config["SECRET_KEY"] = "a8f3b2e9c1d47f6a0b3e8c9d2f1a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a"
    if config:
        app.config.update(config)
    db.init_app(app)

    from .routes import bp
    app.register_blueprint(bp)

    with app.app_context():
        from . import models  # noqa: F401
        db.create_all()

    return app
