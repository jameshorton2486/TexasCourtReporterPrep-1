from flask import Flask, render_template, redirect, url_for
from flask_login import current_user
from extensions import db, login_manager
from flask_mail import Mail
import random
import os
import logging
from logging.handlers import RotatingFileHandler
from pythonjsonlogger import jsonlogger

# Create Flask app first
app = Flask(__name__)

# Configure app
app.config.update(
    SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "default_secret_key"),
    SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
    SQLALCHEMY_TRACK_MODIFICATIONS=False,
    # Mail settings
    MAIL_SERVER='smtp.gmail.com',
    MAIL_PORT=587,
    MAIL_USE_TLS=True,
    MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
    MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
    MAIL_DEFAULT_SENDER=os.environ.get('MAIL_USERNAME'),
    # Additional settings for security
    SESSION_COOKIE_SECURE=True,
    REMEMBER_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    REMEMBER_COOKIE_HTTPONLY=True,
    # Flask-Mail timeout settings
    MAIL_MAX_EMAILS=None,
    MAIL_TIMEOUT=30,
    # Development settings
    DEBUG=True,
    # Server settings
    SERVER_NAME=None  # Allow all hostnames
)

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

def shuffle_filter(seq):
    try:
        result = list(seq)
        random.shuffle(result)
        return result
    except Exception as e:
        app.logger.warning(f'Shuffle filter failed: {str(e)}')
        return seq

# Set up logging
setup_logging(app)

# Add custom filters
app.jinja_env.filters['shuffle'] = shuffle_filter

# Initialize extensions
db.init_app(app)
login_manager.init_app(app)
login_manager.login_view = 'main.login'

# Initialize Mail
mail = Mail(app)

# Import models
from models import User, Category, Question, Test
from routes import create_admin_user, bp as main_bp

@login_manager.user_loader
def load_user(id):
    return User.query.get(int(id))

# Register blueprints
app.register_blueprint(main_bp)

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

# Initialize database and create default categories
with app.app_context():
    try:
        db.create_all()
        app.logger.info('Database tables created successfully')
        
        # Create admin user if not exists
        admin_user = create_admin_user()
        if not admin_user:
            app.logger.error('Failed to create admin user')
        
        # Create default categories if they don't exist
        default_categories = [
            {"name": "Legal & Judicial Terminology", "description": "Common legal terms, court procedures, and Latin phrases"},
            {"name": "Professional Standards & Ethics", "description": "Court reporter responsibilities and ethical guidelines"},
            {"name": "Grammar & Vocabulary", "description": "Legal writing, punctuation, and specialized terminology"},
            {"name": "Transcription Standards", "description": "Formatting rules and transcript preparation guidelines"}
        ]
        
        for category_data in default_categories:
            if not Category.query.filter_by(name=category_data["name"]).first():
                category = Category()
                category.name = category_data["name"]
                category.description = category_data["description"]
                db.session.add(category)
                app.logger.info(f'Added new category: {category_data["name"]}')
        
        db.session.commit()
        app.logger.info('Initial setup completed successfully')
        
    except Exception as e:
        app.logger.error(f'Error during initialization: {str(e)}')
        db.session.rollback()
        raise

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
