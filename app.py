from flask import Flask, render_template, redirect, url_for, request, g, current_app, jsonify
from flask_login import current_user
from extensions import db, login_manager
from models import User
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

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        
        # Add basic fields
        if not log_record.get('timestamp'):
            log_record['timestamp'] = self.formatTime(record)
        if record.exc_info:
            log_record['stack_trace'] = traceback.format_exception(*record.exc_info)
        log_record['logger'] = record.name
        log_record['level'] = record.levelname
        
        try:
            # Only add request info if we're in request context
            if hasattr(g, 'request_id'):
                log_record['request_id'] = g.request_id
            
            if request and request.environ:
                log_record['method'] = request.method
                log_record['path'] = request.path
                log_record['ip'] = request.remote_addr
                
            # Add response time if available
            if hasattr(g, 'start_time'):
                log_record['response_time'] = (time.time() - g.start_time) * 1000
                
            # Add user context if available
            if current_user and current_user.is_authenticated:
                log_record['user_id'] = current_user.id
                
        except Exception as e:
            # If anything goes wrong adding context, log it but don't fail
            log_record['context_error'] = str(e)

def setup_logging(app):
    """Configure application logging with enhanced error handling and rotation."""
    try:
        # Ensure logs directory exists
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

        app.logger.info("Application logging initialized")

    except Exception as e:
        # If logging setup fails, ensure basic console logging works
        print(f"Error setting up logging: {str(e)}")
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(console_handler)
        app.logger.error(f"Failed to initialize logging: {str(e)}")

def create_app():
    """Application factory function with enhanced error handling."""
    app = Flask(__name__)

    # Configure app with improved error handling
    try:
        app.config.update(
            SECRET_KEY=os.environ.get("FLASK_SECRET_KEY", "default_secret_key"),
            SQLALCHEMY_DATABASE_URI=os.environ.get("DATABASE_URL"),
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
            # Mail settings with defaults
            MAIL_SERVER=os.environ.get('MAIL_SERVER', 'smtp.gmail.com'),
            MAIL_PORT=int(os.environ.get('MAIL_PORT', 587)),
            MAIL_USE_TLS=True,
            MAIL_USERNAME=os.environ.get('MAIL_USERNAME'),
            MAIL_PASSWORD=os.environ.get('MAIL_PASSWORD'),
            MAIL_DEFAULT_SENDER=os.environ.get('MAIL_USERNAME'),
            # Security settings
            SESSION_COOKIE_SECURE=True,
            REMEMBER_COOKIE_SECURE=True,
            SESSION_COOKIE_HTTPONLY=True,
            REMEMBER_COOKIE_HTTPONLY=True,
            # Development settings
            DEBUG=True
        )

        # Initialize extensions with error handling
        db.init_app(app)
        login_manager.init_app(app)
        login_manager.login_view = 'auth.login'

        # Add user loader
        @login_manager.user_loader
        def load_user(user_id):
            try:
                return db.session.get(User, int(user_id))
            except Exception as e:
                app.logger.error(f"Error loading user: {str(e)}")
                return None

        # Initialize mail
        mail = Mail(app)

        # Set up logging
        setup_logging(app)

        # Register error handlers
        @app.errorhandler(400)
        def bad_request_error(error):
            app.logger.error(f"400 error: {str(error)}")
            return jsonify(error="Bad Request", message=str(error)), 400

        @app.errorhandler(401)
        def unauthorized_error(error):
            app.logger.error(f"401 error: {str(error)}")
            return jsonify(error="Unauthorized", message="Please log in to access this resource"), 401

        @app.errorhandler(403)
        def forbidden_error(error):
            app.logger.error(f"403 error: {str(error)}")
            return jsonify(error="Forbidden", message="You don't have permission to access this resource"), 403

        @app.errorhandler(404)
        def not_found_error(error):
            app.logger.error(f"404 error: {str(error)}")
            return jsonify(error="Not Found", message="The requested resource was not found"), 404

        @app.errorhandler(500)
        def internal_error(error):
            app.logger.error(f"500 error: {str(error)}")
            db.session.rollback()
            return jsonify(error="Internal Server Error", message="An internal server error occurred"), 500

        # Register blueprints
        from routes import bp as main_bp
        app.register_blueprint(main_bp)

        # Request handlers for logging
        @app.before_request
        def before_request():
            g.start_time = time.time()
            g.request_id = str(uuid.uuid4())

        @app.after_request
        def after_request(response):
            try:
                if hasattr(g, 'start_time'):
                    total_time = (time.time() - g.start_time) * 1000
                    app.logger.info(f"Request completed in {total_time:.2f}ms")
                
                # Add security headers
                response.headers['X-Content-Type-Options'] = 'nosniff'
                response.headers['X-Frame-Options'] = 'SAMEORIGIN'
                response.headers['X-XSS-Protection'] = '1; mode=block'
                
                return response
            except Exception as e:
                app.logger.error(f"Error in after_request: {str(e)}")
                return response

        # Initialize database and create tables
        with app.app_context():
            db.create_all()
            app.logger.info('Database tables created successfully')

            # Create admin user and default categories
            from routes import create_admin_user
            admin_user = create_admin_user()
            if not admin_user:
                app.logger.error('Failed to create admin user')
            else:
                app.logger.info('Admin user verified/created successfully')
            
            # Create default categories if they don't exist
            from models import Category
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

        return app

    except Exception as e:
        print(f"Error creating application: {str(e)}")
        raise

def shuffle_filter(seq):
    try:
        result = list(seq)
        random.shuffle(result)
        return result
    except Exception as e:
        current_app.logger.error(f'Shuffle filter failed: {str(e)}', exc_info=True)
        return seq

if __name__ == '__main__':
    try:
        app = create_app()
        port = int(os.environ.get('PORT', 3000))
        app.run(host='0.0.0.0', port=port, debug=True)
    except Exception as e:
        print(f"Failed to start application: {str(e)}")
        raise