from flask import Flask, render_template, redirect, url_for, request, g, current_app, jsonify, make_response
from flask_login import current_user, login_required
from flask_cors import CORS
from extensions import db, login_manager
from models import User
from flask_mail import Mail
import random
import os
import logging
from logging.handlers import TimedRotatingFileHandler, RotatingFileHandler
from pythonjsonlogger import jsonlogger
import traceback
import time
import uuid
from functools import wraps
from datetime import timedelta
from routes.dashboard import dashboard as dashboard_blueprint
from routes.auth import auth as auth_blueprint
import socket

def is_port_in_use(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('0.0.0.0', port))
            return False
        except socket.error:
            return True

class CustomJsonFormatter(jsonlogger.JsonFormatter):
    def add_fields(self, log_record, record, message_dict):
        super(CustomJsonFormatter, self).add_fields(log_record, record, message_dict)
        if not log_record.get('timestamp'):
            log_record['timestamp'] = self.formatTime(record)
        if record.exc_info:
            log_record['stack_trace'] = traceback.format_exception(*record.exc_info)
        log_record['logger'] = record.name
        log_record['level'] = record.levelname
        
        try:
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
                
        except Exception as e:
            log_record['context_error'] = str(e)

def setup_logging(app):
    if not os.path.exists('logs'):
        os.makedirs('logs')

    formatter = CustomJsonFormatter('%(timestamp)s %(level)s %(name)s %(message)s')
    
    # Add rotating file handler for app.log
    file_handler = RotatingFileHandler(
        'flask_app.log', 
        maxBytes=10000000,  # 10MB
        backupCount=5
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    
    file_handler = TimedRotatingFileHandler(
        'logs/app.log',
        when='midnight',
        interval=1,
        backupCount=30,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    app.logger.setLevel(logging.INFO)
    app.logger.handlers = []
    app.logger.addHandler(file_handler)
    app.logger.addHandler(console_handler)

    return app.logger

def create_app():
    app = Flask(__name__)
    
    # Enable CORS
    CORS(app)
    
    # Basic configuration
    app.config.update(
        SECRET_KEY=os.environ.get('FLASK_SECRET_KEY', 'default_secret_key'),
        SQLALCHEMY_DATABASE_URI=os.environ.get('DATABASE_URL'),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SESSION_COOKIE_SECURE=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(minutes=60)
    )

    # Set up logging first
    logger = setup_logging(app)

    # Initialize extensions
    db.init_app(app)
    
    # Configure login manager
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access this page.'

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    @app.before_request
    def before_request():
        g.start_time = time.time()
        g.request_id = str(uuid.uuid4())

    @app.after_request
    def after_request(response):
        if hasattr(g, 'start_time'):
            total_time = (time.time() - g.start_time) * 1000
            logger.info(f"Request completed in {total_time:.2f}ms")
        
        # Add security headers
        response.headers.update({
            'X-Content-Type-Options': 'nosniff',
            'X-Frame-Options': 'SAMEORIGIN',
            'X-XSS-Protection': '1; mode=block',
            'Access-Control-Allow-Origin': '*'
        })
        return response

    # Register blueprints
    app.register_blueprint(auth_blueprint, url_prefix='/auth')
    app.register_blueprint(dashboard_blueprint)

    # Initialize database
    with app.app_context():
        db.create_all()
        logger.info('Database tables created successfully')

        # Create admin user and default categories
        from routes import create_admin_user
        if create_admin_user():
            logger.info('Admin user verified/created successfully')
        
        # Create default categories
        from models import Category
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
        
        db.session.commit()

    @app.route('/')
    def index():
        if current_user.is_authenticated:
            return redirect(url_for('dashboard.show_dashboard'))
        return redirect(url_for('auth.login'))

    @app.errorhandler(404)
    def not_found_error(error):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def internal_error(error):
        db.session.rollback()
        return render_template('errors/500.html'), 500

    return app

def shuffle_filter(seq):
    try:
        result = list(seq)
        random.shuffle(result)
        return result
    except Exception as e:
        current_app.logger.error(f'Shuffle filter failed: {str(e)}')
        return seq

app = create_app()
app.jinja_env.filters['shuffle'] = shuffle_filter

if __name__ == '__main__':
    port = 5000
    if is_port_in_use(port):
        logger.warning(f'Port {port} is in use, trying alternate port')
        port = 8080
    app.run(host='0.0.0.0', port=port)
