from flask import Flask, render_template, redirect, url_for, request, g
from flask_login import current_user
from extensions import db, login_manager
from flask_mail import Mail
import random
import os
import logging
from logging.handlers import TimedRotatingFileHandler
from pythonjsonlogger import jsonlogger
import traceback
import time
import uuid
from functools import wraps

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

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            log_record['timestamp'] = self.formatTime(record)
        if record.exc_info:
            log_record['stack_trace'] = traceback.format_exception(*record.exc_info)
        log_record['logger'] = record.name
        log_record['level'] = record.levelname
        
        # Add request context if available
        if hasattr(g, 'request_id'):
            log_record['request_id'] = g.request_id
        if request:
            log_record['method'] = request.method
            log_record['path'] = request.path
            log_record['ip'] = request.remote_addr
        if hasattr(g, 'start_time'):
            log_record['response_time'] = (time.time() - g.start_time) * 1000
        if current_user and current_user.is_authenticated:
            log_record['user_id'] = current_user.id

def setup_logging(app):
    # Create logs directory if it doesn't exist
    if not os.path.exists('logs'):
        os.makedirs('logs')

    # Set up JSON formatter with enhanced context
    formatter = CustomJsonFormatter(
        '%(timestamp)s %(level)s %(name)s %(message)s'
    )

    # Set up file handler with daily rotation and compression
    file_handler = TimedRotatingFileHandler(
        'logs/app.log',
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    # Enable compression for rotated logs
    file_handler.rotator = lambda source, dest: os.system(f'gzip {source}')
    file_handler.namer = lambda name: name + ".gz"

    # Set up console handler with more detailed output
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.DEBUG)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # Remove any existing handlers
    root_logger.handlers = []
    
    # Add our handlers
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Configure Flask logger
    app.logger.setLevel(logging.INFO)
    # Remove default handlers
    app.logger.handlers = []
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)

    # Log application startup
    app.logger.info("Application logging initialized")

    # Add request context processor
    @app.before_request
    def before_request():
        g.request_id = str(uuid.uuid4())
        g.start_time = time.time()
        app.logger.info(f"Request started", extra={
            'request_id': g.request_id,
            'method': request.method,
            'path': request.path,
            'ip': request.remote_addr
        })

    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            response_time = (time.time() - g.start_time) * 1000
            app.logger.info(f"Request completed", extra={
                'request_id': getattr(g, 'request_id', 'unknown'),
                'method': request.method,
                'path': request.path,
                'status_code': response.status_code,
                'response_time': response_time
            })
        return response

def shuffle_filter(seq):
    try:
        result = list(seq)
        random.shuffle(result)
        return result
    except Exception as e:
        app.logger.error(f'Shuffle filter failed: {str(e)}', exc_info=True)
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
    try:
        user = User.query.get(int(id))
        app.logger.info(f"User loaded: {id}")
        return user
    except Exception as e:
        app.logger.error(f"Error loading user {id}: {str(e)}", exc_info=True)
        return None

# Register blueprints
app.register_blueprint(main_bp)

# Error handlers
@app.errorhandler(404)
def not_found_error(error):
    app.logger.warning(f'Page not found: {request.url}', exc_info=True)
    return render_template('errors/404.html'), 404

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f'Server Error: {str(error)}', exc_info=True)
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
        else:
            app.logger.info('Admin user verified/created successfully')
        
        # Create default categories if they don't exist
        default_categories = [
            {"name": "Legal & Judicial Terminology", "description": "Common legal terms, court procedures, and Latin phrases"},
            {"name": "Professional Standards & Ethics", "description": "Court reporter responsibilities and ethical guidelines"},
            {"name": "Grammar & Vocabulary", "description": "Legal writing, punctuation, and specialized terminology"},
            {"name": "Transcription Standards", "description": "Formatting rules and transcript preparation guidelines"}
        ]
        
        categories_added = 0
        for category_data in default_categories:
            if not Category.query.filter_by(name=category_data["name"]).first():
                category = Category()
                category.name = category_data["name"]
                category.description = category_data["description"]
                db.session.add(category)
                categories_added += 1
                app.logger.info(f'Added new category: {category_data["name"]}')
        
        if categories_added > 0:
            db.session.commit()
            app.logger.info(f'Added {categories_added} new categories')
        
        app.logger.info('Initial setup completed successfully')
        
    except Exception as e:
        app.logger.error(f'Error during initialization: {str(e)}', exc_info=True)
        db.session.rollback()
        raise

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
