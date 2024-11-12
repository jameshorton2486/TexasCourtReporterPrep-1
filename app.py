import os
from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

# Create the app
app = Flask(__name__)

# Configure the application
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    from models import User
    return User.query.get(int(id))

with app.app_context():
    import models  # noqa: F401
    import routes  # noqa: F401
    
    db.create_all()

    # Create default categories if they don't exist
    from models import Category
    default_categories = [
        {"name": "Legal & Judicial Terminology", "description": "Common legal terms, court procedures, and Latin phrases"},
        {"name": "Professional Standards & Ethics", "description": "Court reporter responsibilities and ethical guidelines"},
        {"name": "Grammar & Vocabulary", "description": "Legal writing, punctuation, and specialized terminology"},
        {"name": "Transcription Standards", "description": "Formatting rules and transcript preparation guidelines"}
    ]
    
    for category in default_categories:
        if not Category.query.filter_by(name=category["name"]).first():
            new_category = Category(**category)
            db.session.add(new_category)
    
    db.session.commit()
