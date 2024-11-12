from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.exceptions import NotFound, Unauthorized
from sqlalchemy.orm.exc import DetachedInstanceError
from jinja2.exceptions import TemplateError
from app import app, db
from models import User, Category, Question, Test, TestQuestion
import random

@app.route('/')
def index():
    app.logger.info('Accessing index page')
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        try:
            username = request.form['username']
            email = request.form['email']
            password = request.form['password']
            
            if User.query.filter_by(username=username).first():
                app.logger.warning(f'Registration attempt with existing username: {username}')
                flash('Username already exists')
                return redirect(url_for('register'))
            
            if User.query.filter_by(email=email).first():
                app.logger.warning(f'Registration attempt with existing email: {email}')
                flash('Email already exists')
                return redirect(url_for('register'))
                
            user = User()
            user.username = username
            user.email = email
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            
            app.logger.info(f'New user registered: {username}')
            login_user(user)
            return redirect(url_for('dashboard'))
            
        except Exception as e:
            app.logger.error(f'Error during registration: {str(e)}')
            db.session.rollback()
            flash('An error occurred during registration')
            return redirect(url_for('register'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        try:
            username = request.form['username']
            user = User.query.filter_by(username=username).first()
            
            if user and user.check_password(request.form['password']):
                login_user(user)
                app.logger.info(f'User logged in: {username}')
                return redirect(url_for('dashboard'))
                
            app.logger.warning(f'Failed login attempt for username: {username}')
            flash('Invalid username or password')
            
        except Exception as e:
            app.logger.error(f'Error during login: {str(e)}')
            flash('An error occurred during login')
            
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    username = current_user.username
    logout_user()
    app.logger.info(f'User logged out: {username}')
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    try:
        app.logger.debug('Fetching categories from database')
        categories = Category.query.all()
        
        app.logger.debug(f'Fetching tests for user {current_user.username}')
        tests = Test.query.filter_by(user_id=current_user.id).order_by(Test.created_at.desc()).all()
        
        # Eagerly load category relationships to avoid detached instance errors
        for test in tests:
            app.logger.debug(f'Loading category for test {test.id}')
            db.session.refresh(test)
            if test.category_id and not test.category:
                app.logger.warning(f'Category {test.category_id} not found for test {test.id}')
                test.category_id = None
                db.session.commit()
        
        return render_template('dashboard.html', categories=categories, tests=tests)
        
    except DetachedInstanceError as e:
        app.logger.error(f'Detached instance error in dashboard: {str(e)}')
        db.session.rollback()
        flash('Error loading dashboard data. Please try again.')
        return redirect(url_for('index'))
    except Exception as e:
        app.logger.error(f'Error accessing dashboard: {str(e)}')
        db.session.rollback()
        flash('An unexpected error occurred while loading the dashboard')
        return redirect(url_for('index'))

@app.route('/test/new/<int:category_id>')
@login_required
def new_test(category_id):
    try:
        question_count = int(request.args.get('question_count', 20))
        if question_count not in [10, 20]:
            question_count = 20  # Default to 20 if invalid value provided
            
        app.logger.debug(f'Creating new test for category {category_id} with {question_count} questions')
        questions = Question.query.filter_by(category_id=category_id).all()
        if not questions:
            app.logger.warning(f'No questions found for category_id: {category_id}')
            flash('No questions available for this category')
            return redirect(url_for('dashboard'))
            
        selected_questions = random.sample(questions, min(question_count, len(questions)))
        
        test = Test()
        test.user_id = current_user.id
        test.category_id = category_id
        db.session.add(test)
        db.session.flush()  # Get the test ID without committing
        
        for question in selected_questions:
            test_question = TestQuestion()
            test_question.test_id = test.id
            test_question.question_id = question.id
            db.session.add(test_question)
        
        db.session.commit()
        app.logger.info(f'New test created for user {current_user.username} in category {category_id}')
        return redirect(url_for('take_test', test_id=test.id))
        
    except Exception as e:
        app.logger.error(f'Error creating new test: {str(e)}')
        db.session.rollback()
        flash('An error occurred while creating the test')
        return redirect(url_for('dashboard'))

@app.route('/test/<int:test_id>')
@login_required
def take_test(test_id):
    try:
        app.logger.debug(f'Attempting to load test {test_id}')
        test = Test.query.get_or_404(test_id)
        
        if test.user_id != current_user.id:
            app.logger.warning(f'Unauthorized test access attempt by user {current_user.username} for test {test_id}')
            raise Unauthorized()
        
        app.logger.debug(f'Loading test data and relationships for test {test_id}')
        db.session.refresh(test)
        
        # Verify all required relationships are loaded
        app.logger.debug('Verifying test question relationships')
        for test_question in test.questions:
            if not test_question.question:
                app.logger.error(f'Question relationship missing for test_question {test_question.id}')
                raise ValueError('Invalid test question data')
        
        try:
            app.logger.debug('Rendering test template')
            return render_template('test.html', test=test)
        except TemplateError as te:
            app.logger.error(f'Template rendering error: {str(te)}')
            flash('An error occurred while preparing the test display')
            return redirect(url_for('dashboard'))
            
    except NotFound:
        app.logger.warning(f'Test not found: {test_id}')
        flash('Test not found')
        return redirect(url_for('dashboard'))
    except Unauthorized:
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))
    except ValueError as ve:
        app.logger.error(f'Data validation error: {str(ve)}')
        flash('Invalid test data')
        return redirect(url_for('dashboard'))
    except Exception as e:
        app.logger.error(f'Error accessing test: {str(e)}')
        flash('An error occurred while accessing the test')
        return redirect(url_for('dashboard'))

@app.route('/test/<int:test_id>/submit', methods=['POST'])
@login_required
def submit_test(test_id):
    try:
        test = Test.query.get_or_404(test_id)
        if test.user_id != current_user.id:
            app.logger.warning(f'Unauthorized test submission attempt by user {current_user.username} for test {test_id}')
            return jsonify({'error': 'Unauthorized'}), 403
        
        answers = request.get_json()
        correct_count = 0
        
        app.logger.debug(f'Processing {len(answers)} answers for test {test_id}')
        for test_question in test.questions:
            answer = answers.get(str(test_question.id))
            if not answer:
                return jsonify({'error': 'All questions must be answered'}), 400
                
            test_question.user_answer = answer
            test_question.is_correct = (answer == test_question.question.correct_answer)
            if test_question.is_correct:
                correct_count += 1
        
        test.score = (correct_count / len(test.questions)) * 100
        test.completed = True
        db.session.commit()
        
        app.logger.info(f'Test {test_id} submitted by user {current_user.username} with score {test.score}')
        return jsonify({'redirect': url_for('test_results', test_id=test.id)})
        
    except Exception as e:
        app.logger.error(f'Error submitting test: {str(e)}')
        db.session.rollback()
        return jsonify({'error': 'An error occurred while submitting the test'}), 500

@app.route('/test/<int:test_id>/results')
@login_required
def test_results(test_id):
    try:
        app.logger.debug(f'Loading test results for test {test_id}')
        test = Test.query.get_or_404(test_id)
        
        if test.user_id != current_user.id:
            app.logger.warning(f'Unauthorized results access attempt by user {current_user.username} for test {test_id}')
            flash('Unauthorized access')
            return redirect(url_for('dashboard'))
        
        db.session.refresh(test)
        
        try:
            app.logger.debug('Rendering results template')
            return render_template('results.html', test=test)
        except TemplateError as te:
            app.logger.error(f'Template rendering error in results: {str(te)}')
            flash('An error occurred while displaying the results')
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        app.logger.error(f'Error accessing test results: {str(e)}')
        flash('An error occurred while accessing the test results')
        return redirect(url_for('dashboard'))
