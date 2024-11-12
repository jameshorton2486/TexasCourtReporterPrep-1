import os
import logging
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger
from flask import Flask, render_template
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
login_manager = LoginManager()

def setup_logging(app):
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Set up JSON formatter
    formatter = jsonlogger.JsonFormatter(
        '%(asctime)s %(levelname)s %(name)s %(message)s'
    )

    # Set up file handler with rotation
    file_handler = RotatingFileHandler(
        'logs/app.log', maxBytes=10485760, backupCount=10
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Set up console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Configure Flask logger
    app.logger.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)

# Create the app
app = Flask(__name__)

# Configure the application
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
}

# Set up logging
setup_logging(app)

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'login'

@login_manager.user_loader
def load_user(id):
    from models import User
    return User.query.get(int(id))

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    app.logger.warning(f'Page not found: {error}')
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'Server Error: {error}')
    db.session.rollback()
    return render_template('errors/500.html'), 500

with app.app_context():
    app.logger.info('Initializing application...')
    
    import models  # noqa: F401
    import routes  # noqa: F401
    
    try:
        db.create_all()
        app.logger.info('Database tables created successfully')
        
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
                app.logger.info(f'Added new category: {category["name"]}')
        
        db.session.commit()
        app.logger.info('Initial setup completed successfully')
        
    except Exception as e:
        app.logger.error(f'Error during initialization: {str(e)}')
        raise
