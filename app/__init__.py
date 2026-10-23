"""Flask app factory and SQLite database setup."""

from flask import Flask
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


def create_app():
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///hsa.db"
    db.init_app(app)

    with app.app_context():
        from . import models 

        db.create_all()

    return app
