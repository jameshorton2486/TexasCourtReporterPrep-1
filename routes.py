from flask import Blueprint, render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.exceptions import NotFound, Unauthorized
from sqlalchemy.orm.exc import DetachedInstanceError
from jinja2.exceptions import TemplateError
from functools import wraps
from datetime import datetime, timedelta
import random
import logging
import os
from extensions import db
from models import User, Category, Question, Test, TestQuestion, StudySession, StudyTimer
from flask_mail import Mail, Message
from threading import Thread

mail = Mail()

def send_async_email(app, msg):
    with app.app_context():
        mail.send(msg)

def send_email(subject, sender, recipients, text_body, html_body):
    msg = Message(subject, sender=sender, recipients=recipients)
    msg.body = text_body
    msg.html = html_body
    Thread(target=send_async_email, args=(app._get_current_object(), msg)).start()

def send_password_reset_email(user):
    token = user.get_reset_password_token()
    send_email(
        'Reset Your Password',
        sender=app.config['MAIL_DEFAULT_SENDER'],
        recipients=[user.email],
        text_body=render_template('email/reset_password.txt', user=user, token=token),
        html_body=render_template('email/reset_password.html', user=user, token=token)
    )

logger = logging.getLogger(__name__)

bp = Blueprint('main', __name__)

def admin_required(f):
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_administrator():
            flash('Admin access required')
            return redirect(url_for('main.login'))
        return f(*args, **kwargs)
    return decorated_function

def create_admin_user():
    """Create admin user if it doesn't exist using environment variables."""
    try:
        # Get admin credentials from environment variables
        admin_username = os.environ.get('ADMIN_USERNAME')
        admin_email = os.environ.get('ADMIN_EMAIL')
        admin_password = os.environ.get('ADMIN_PASSWORD')

        # Validate environment variables
        if not all([admin_username, admin_email, admin_password]):
            logger.error("Admin credentials not properly configured in environment variables")
            return None

        # Check if admin user already exists
        admin = User.query.filter_by(username=admin_username).first()
        if not admin:
            # Create new admin user
            admin = User()
            admin.username = admin_username
            admin.email = admin_email
            admin.set_password(admin_password)
            admin.is_admin = True
            
            db.session.add(admin)
            db.session.commit()
            logger.info('Admin user created successfully')
        return admin
        
    except Exception as e:
        logger.error(f'Error creating admin user: {str(e)}')
        db.session.rollback()
        return None

@bp.route('/')
def index():
    """Home page route that handles both authenticated and non-authenticated users."""
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('main.login'))

@bp.route('/dashboard')
@login_required
def dashboard():
    """Dashboard page showing categories and tests."""
    try:
        categories = Category.query.all()
        tests = Test.query.filter_by(user_id=current_user.id).order_by(Test.created_at.desc()).all()
        return render_template('dashboard.html', categories=categories, tests=tests)
    except Exception as e:
        logger.error(f'Error accessing dashboard: {str(e)}')
        db.session.rollback()
        flash('An error occurred while loading the dashboard')
        return redirect(url_for('main.login'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            email = request.form.get('email')
            password = request.form.get('password')
            
            if not all([username, email, password]):
                flash('All fields are required')
                return redirect(url_for('main.register'))
            
            if User.query.filter_by(username=username).first():
                flash('Username already exists')
                return redirect(url_for('main.register'))
            
            if User.query.filter_by(email=email).first():
                flash('Email already exists')
                return redirect(url_for('main.register'))
            
            user = User()
            user.username = username
            user.email = email
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            login_user(user)
            return redirect(url_for('main.dashboard'))
            
        except Exception as e:
            logger.error(f'Error during registration: {str(e)}')
            db.session.rollback()
            flash('An error occurred during registration')
            return redirect(url_for('main.register'))
    
    return render_template('register.html')

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    
    if request.method == 'POST':
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            
            if not all([username, password]):
                flash('Username and password are required')
                return redirect(url_for('main.login'))
            
            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for('main.dashboard'))
            
            flash('Invalid login credentials')
            
        except Exception as e:
            logger.error(f'Error during login: {str(e)}')
            flash('An error occurred during login')
    
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.login'))

@bp.route('/study/timer/start', methods=['POST'])
@login_required
def start_timer():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        session_id = data.get('session_id')
        if not session_id:
            return jsonify({'error': 'Session ID required'}), 400
        
        study_session = StudySession.query.get_or_404(session_id)
        if study_session.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        timer = StudyTimer(user_id=current_user.id, session_id=session_id)
        db.session.add(timer)
        db.session.commit()
        
        return jsonify({'timer_id': timer.id, 'success': True})
        
    except Exception as e:
        logger.error(f'Error starting timer: {str(e)}')
        return jsonify({'error': 'Failed to start timer'}), 500

@bp.route('/study/timer/stop', methods=['POST'])
@login_required
def stop_timer():
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No data provided'}), 400
            
        timer_id = data.get('timer_id')
        if not timer_id:
            return jsonify({'error': 'Timer ID required'}), 400
        
        timer = StudyTimer.query.get_or_404(timer_id)
        if timer.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
        
        timer.stop()
        return jsonify({'success': True})
        
    except Exception as e:
        logger.error(f'Error stopping timer: {str(e)}')
        return jsonify({'error': 'Failed to stop timer'}), 500

@bp.route('/schedule_study', methods=['GET', 'POST'])
@login_required
def schedule_study():
    try:
        if request.method == 'POST':
            start_time_str = request.form.get('start_time')
            duration_str = request.form.get('duration_minutes')
            description = request.form.get('description', '')
            category_id = request.form.get('category_id')

            if not all([category_id, start_time_str, duration_str]):
                flash('Please fill in all required fields')
                return redirect(url_for('main.schedule_study'))

            try:
                start_time = datetime.strptime(start_time_str, '%Y-%m-%dT%H:%M')
                duration_minutes = int(duration_str)
            except (ValueError, TypeError):
                flash('Invalid date/time or duration format')
                return redirect(url_for('main.schedule_study'))

            if start_time < datetime.utcnow():
                flash('Start time must be in the future')
                return redirect(url_for('main.schedule_study'))

            session = StudySession(
                user_id=current_user.id,
                category_id=int(category_id),
                start_time=start_time,
                duration_minutes=duration_minutes,
                description=description
            )
            db.session.add(session)
            db.session.commit()

            flash('Study session scheduled successfully')
            return redirect(url_for('main.dashboard'))

        categories = Category.query.all()
        return render_template('schedule_study.html', categories=categories)

    except Exception as e:
        logger.error(f'Error scheduling study session: {str(e)}')
        db.session.rollback()
        flash('An error occurred while scheduling the study session')
        return redirect(url_for('main.dashboard'))

@bp.route('/test/new/<int:category_id>')
@login_required
def new_test(category_id):
    try:
        question_count = int(request.args.get('question_count', 20))
        is_practice = request.args.get('practice', 'false').lower() == 'true'
        
        if question_count not in [10, 20]:
            question_count = 20
            
        weak_questions = current_user.get_weak_areas(category_id=category_id)
        weak_question_ids = [q.question_id for q in weak_questions]
        
        remaining_questions = Question.query.filter_by(category_id=category_id)
        if weak_question_ids:
            remaining_questions = remaining_questions.filter(~Question.id.in_(weak_question_ids))
        remaining_questions = remaining_questions.all()
        
        total_available = len(remaining_questions) + len(weak_questions)
        
        if total_available < 10:
            flash('Not enough questions available for testing in this category. Please try again later.')
            return redirect(url_for('main.dashboard'))
            
        if total_available < question_count:
            flash(f'Only {total_available} questions available. Creating test with all available questions.')
            question_count = total_available
            
        weak_count = len(weak_questions)
        new_count = min(question_count - weak_count, len(remaining_questions))
        
        selected_questions = []
        selected_questions.extend(weak_questions)
        if new_count > 0:
            selected_questions.extend(random.sample(remaining_questions, new_count))
        
        if len(selected_questions) < question_count:
            additional_needed = question_count - len(selected_questions)
            available_pool = [q for q in remaining_questions if q not in selected_questions]
            if available_pool:
                selected_questions.extend(random.sample(available_pool, min(additional_needed, len(available_pool))))
        
        test = Test()
        test.user_id = current_user.id
        test.category_id = category_id
        test.is_practice = is_practice
        db.session.add(test)
        db.session.flush()
        
        for question in selected_questions:
            test_question = TestQuestion()
            test_question.test_id = test.id
            test_question.question_id = question.id if isinstance(question, Question) else question.question_id
            db.session.add(test_question)
        
        db.session.commit()
        return redirect(url_for('main.take_test', test_id=test.id))
        
    except ValueError as ve:
        logger.error(f'Value error in new_test: {str(ve)}')
        flash('Invalid test parameters provided')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        logger.error(f'Error creating new test: {str(e)}')
        db.session.rollback()
        flash('An error occurred while creating the test')
        return redirect(url_for('main.dashboard'))

@bp.route('/test/<int:test_id>')
@login_required
def take_test(test_id):
    try:
        test = Test.query.get_or_404(test_id)
        
        if test.user_id != current_user.id:
            logger.warning(f'Unauthorized test access attempt by user {current_user.username} for test {test_id}')
            raise Unauthorized()
        
        if not test.questions:
            logger.error(f'No questions found for test {test_id}')
            flash('Test has no questions')
            return redirect(url_for('main.dashboard'))
            
        return render_template('test.html', test=test)
        
    except NotFound:
        logger.warning(f'Test not found: {test_id}')
        flash('Test not found')
        return redirect(url_for('main.dashboard'))
    except Unauthorized:
        flash('Unauthorized access')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        logger.error(f'Error accessing test: {str(e)}')
        flash('An error occurred while accessing the test')
        return redirect(url_for('main.dashboard'))

@bp.route('/test/<int:test_id>/submit', methods=['POST'])
@login_required
def submit_test(test_id):
    try:
        test = Test.query.get_or_404(test_id)
        if test.user_id != current_user.id:
            return jsonify({'error': 'Unauthorized'}), 403
            
        data = request.get_json()
        if not data:
            return jsonify({'error': 'No answer data provided'}), 400
            
        correct_count = 0
        total_questions = len(test.questions)
        
        for question in test.questions:
            answer = data.get(str(question.id))
            if not answer:
                return jsonify({'error': 'All questions must be answered'}), 400
                
            question.user_answer = answer
            question.is_correct = (answer == question.question.correct_answer)
            if question.is_correct:
                correct_count += 1
                
            question.update_performance()
        
        test.score = (correct_count / total_questions) * 100
        test.completed = True
        db.session.commit()
        
        if test.is_practice:
            return jsonify({
                'score': test.score,
                'correct_count': correct_count,
                'total_questions': total_questions
            })
        
        return jsonify({'redirect': url_for('main.test_results', test_id=test_id)})
        
    except Exception as e:
        logger.error(f'Error submitting test: {str(e)}')
        db.session.rollback()
        return jsonify({'error': 'An error occurred while submitting the test'}), 500

@bp.route('/test/<int:test_id>/results')
@login_required
def test_results(test_id):
    try:
        test = Test.query.get_or_404(test_id)
        if test.user_id != current_user.id:
            raise Unauthorized()
            
        if not test.completed:
            flash('Test has not been completed')
            return redirect(url_for('main.dashboard'))
            
        return render_template('results.html', test=test)
        
    except NotFound:
        flash('Test not found')
        return redirect(url_for('main.dashboard'))
    except Unauthorized:
        flash('Unauthorized access')
        return redirect(url_for('main.dashboard'))
    except Exception as e:
        logger.error(f'Error accessing test results: {str(e)}')
        flash('An error occurred while accessing the test results')
        return redirect(url_for('main.dashboard'))

# Admin routes
@bp.route('/admin/questions')
@admin_required
def admin_questions():
    try:
        questions = Question.query.order_by(Question.created_at.desc()).all()
        return render_template('admin/questions.html', questions=questions)
    except Exception as e:
        logger.error(f'Error accessing admin questions: {str(e)}')
        flash('An error occurred while loading questions')
        return redirect(url_for('main.dashboard'))

@bp.route('/admin/questions/add', methods=['GET', 'POST'])
@admin_required
def admin_add_question():
    try:
        if request.method == 'POST':
            category_id = request.form.get('category_id')
            question_text = request.form.get('question_text')
            correct_answer = request.form.get('correct_answer')
            wrong_answers = request.form.getlist('wrong_answers[]')
            
            if not all([category_id, question_text, correct_answer]) or len(wrong_answers) < 3:
                flash('Please fill in all required fields')
                return redirect(url_for('main.admin_add_question'))

            question = Question()
            question.category_id = category_id
            question.question_text = question_text
            question.correct_answer = correct_answer
            question.wrong_answers = wrong_answers
            
            db.session.add(question)
            db.session.commit()
            
            flash('Question added successfully')
            return redirect(url_for('main.admin_questions'))
            
        categories = Category.query.all()
        return render_template('admin/add_question.html', categories=categories)
    except Exception as e:
        logger.error(f'Error adding question: {str(e)}')
        db.session.rollback()
        flash('An error occurred while adding the question')
        return redirect(url_for('main.admin_questions'))

@bp.route('/admin/questions/<int:id>/edit', methods=['GET', 'POST'])
@admin_required
def admin_edit_question(id):
    try:
        question = Question.query.get_or_404(id)
        
        if request.method == 'POST':
            category_id = request.form.get('category_id')
            question_text = request.form.get('question_text')
            correct_answer = request.form.get('correct_answer')
            wrong_answers = request.form.getlist('wrong_answers[]')
            
            if not all([category_id, question_text, correct_answer]) or len(wrong_answers) < 3:
                flash('Please fill in all required fields')
                return redirect(url_for('main.admin_edit_question', id=id))
            
            question.category_id = category_id
            question.question_text = question_text
            question.correct_answer = correct_answer
            question.wrong_answers = wrong_answers
            db.session.commit()
            
            flash('Question updated successfully')
            return redirect(url_for('main.admin_questions'))
        
        categories = Category.query.all()
        return render_template('admin/add_question.html', question=question, categories=categories)
        
    except Exception as e:
        logger.error(f'Error editing question: {str(e)}')
        db.session.rollback()
        flash('An error occurred while editing the question')
        return redirect(url_for('main.admin_questions'))

@bp.route('/admin/questions/<int:id>/delete', methods=['POST'])
@admin_required
def admin_delete_question(id):
    try:
        question = Question.query.get_or_404(id)
        db.session.delete(question)
        db.session.commit()
        
        flash('Question deleted successfully')
        
    except Exception as e:
        logger.error(f'Error deleting question: {str(e)}')
        db.session.rollback()
        flash('An error occurred while deleting the question')
        
    return redirect(url_for('main.admin_questions'))

@bp.route('/admin/categories', methods=['GET', 'POST'])
@admin_required
def admin_categories():
    try:
        categories = Category.query.all()
        
        if request.method == 'POST':
            category_name = request.form.get('category_name')
            if not category_name:
                flash('Category name is required')
                return render_template('admin/categories.html', categories=categories)
            
            category = Category(category_name=category_name)
            db.session.add(category)
            db.session.commit()
            
            logger.info(f'Admin {current_user.username} added new category: {category.id}')
            flash('Category added successfully')
            return redirect(url_for('main.admin_categories'))
            
        return render_template('admin/categories.html', categories=categories)
        
    except Exception as e:
        logger.error(f'Error accessing admin categories: {str(e)}')
        flash('An error occurred while loading categories')
        return redirect(url_for('main.dashboard'))

@bp.route('/admin/categories/edit/<int:id>', methods=['GET', 'POST'])
@admin_required
def admin_edit_category(id):
    try:
        category = Category.query.get_or_404(id)
        
        if request.method == 'POST':
            category_name = request.form.get('category_name')
            if not category_name:
                flash('Category name is required')
                return render_template('admin/edit_category.html', category=category)
            
            category.category_name = category_name
            db.session.commit()
            
            logger.info(f'Admin {current_user.username} updated category: {category.id}')
            flash('Category updated successfully')
            return redirect(url_for('main.admin_categories'))
            
        return render_template('admin/edit_category.html', category=category)
        
    except Exception as e:
        logger.error(f'Error editing category: {str(e)}')
        db.session.rollback()
        flash('An error occurred while editing the category')
        return redirect(url_for('main.admin_categories'))

@bp.route('/admin/categories/delete/<int:id>', methods=['POST'])
@admin_required
def admin_delete_category(id):
    try:
        category = Category.query.get_or_404(id)
        db.session.delete(category)
        db.session.commit()
        
        logger.info(f'Admin {current_user.username} deleted category: {id}')
        flash('Category deleted successfully')
        
    except Exception as e:
        logger.error(f'Error deleting category: {str(e)}')
        db.session.rollback()
        flash('An error occurred while deleting the category')
        
    return redirect(url_for('main.admin_categories'))

@bp.route('/reset_password_request', methods=['GET', 'POST'])
def reset_password_request():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    if request.method == 'POST':
        email = request.form.get('email')
        if not email:
            flash('Email address is required')
            return redirect(url_for('main.reset_password_request'))
            
        user = User.query.filter_by(email=email).first()
        if user:
            send_password_reset_email(user)
            flash('Check your email for instructions to reset your password')
            return redirect(url_for('main.login'))
        else:
            flash('Email address not found')
            return redirect(url_for('main.reset_password_request'))
            
    return render_template('reset_password_request.html')

@bp.route('/reset_password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
        
    user = User.verify_reset_password_token(token)
    if not user:
        flash('Invalid or expired reset token')
        return redirect(url_for('main.login'))
        
    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')
        
        if not password or not confirm_password:
            flash('Please fill in all fields')
            return redirect(url_for('main.reset_password', token=token))
            
        if password != confirm_password:
            flash('Passwords do not match')
            return redirect(url_for('main.reset_password', token=token))
            
        if len(password) < 8:
            flash('Password must be at least 8 characters long')
            return redirect(url_for('main.reset_password', token=token))
            
        user.set_password(password)
        db.session.commit()
        flash('Your password has been reset')
        return redirect(url_for('main.login'))
        
    return render_template('reset_password.html')