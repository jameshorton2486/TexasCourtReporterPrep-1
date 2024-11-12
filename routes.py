from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from werkzeug.exceptions import NotFound, Unauthorized
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
                
            user = User(username=username, email=email)
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
        categories = Category.query.all()
        tests = Test.query.filter_by(user_id=current_user.id).all()
        app.logger.info(f'Dashboard accessed by user: {current_user.username}')
        return render_template('dashboard.html', categories=categories, tests=tests)
    except Exception as e:
        app.logger.error(f'Error accessing dashboard: {str(e)}')
        return redirect(url_for('index'))

@app.route('/test/new/<int:category_id>')
@login_required
def new_test(category_id):
    try:
        questions = Question.query.filter_by(category_id=category_id).all()
        if not questions:
            app.logger.warning(f'No questions found for category_id: {category_id}')
            flash('No questions available for this category')
            return redirect(url_for('dashboard'))
            
        selected_questions = random.sample(questions, min(20, len(questions)))
        
        test = Test(user_id=current_user.id, category_id=category_id)
        db.session.add(test)
        
        for question in selected_questions:
            test_question = TestQuestion(test_id=test.id, question_id=question.id)
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
        test = Test.query.get_or_404(test_id)
        if test.user_id != current_user.id:
            app.logger.warning(f'Unauthorized test access attempt by user {current_user.username} for test {test_id}')
            raise Unauthorized()
        
        app.logger.info(f'User {current_user.username} accessed test {test_id}')
        return render_template('test.html', test=test)
        
    except NotFound:
        app.logger.warning(f'Test not found: {test_id}')
        flash('Test not found')
        return redirect(url_for('dashboard'))
    except Unauthorized:
        flash('Unauthorized access')
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
        
        for test_question in test.questions:
            answer = answers.get(str(test_question.id))
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
        test = Test.query.get_or_404(test_id)
        if test.user_id != current_user.id:
            app.logger.warning(f'Unauthorized results access attempt by user {current_user.username} for test {test_id}')
            flash('Unauthorized access')
            return redirect(url_for('dashboard'))
        
        app.logger.info(f'User {current_user.username} accessed results for test {test_id}')
        return render_template('results.html', test=test)
        
    except Exception as e:
        app.logger.error(f'Error accessing test results: {str(e)}')
        flash('An error occurred while accessing the test results')
        return redirect(url_for('dashboard'))
