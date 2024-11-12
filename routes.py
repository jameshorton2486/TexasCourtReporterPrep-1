from flask import render_template, redirect, url_for, flash, request, jsonify
from flask_login import login_user, logout_user, current_user, login_required
from app import app, db
from models import User, Category, Question, Test, TestQuestion
import random

@app.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard'))
    return render_template('login.html')

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        if User.query.filter_by(username=username).first():
            flash('Username already exists')
            return redirect(url_for('register'))
            
        user = User(username=username, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        
        login_user(user)
        return redirect(url_for('dashboard'))
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = User.query.filter_by(username=request.form['username']).first()
        if user and user.check_password(request.form['password']):
            login_user(user)
            return redirect(url_for('dashboard'))
        flash('Invalid username or password')
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

@app.route('/dashboard')
@login_required
def dashboard():
    categories = Category.query.all()
    tests = Test.query.filter_by(user_id=current_user.id).all()
    return render_template('dashboard.html', categories=categories, tests=tests)

@app.route('/test/new/<int:category_id>')
@login_required
def new_test(category_id):
    questions = Question.query.filter_by(category_id=category_id).all()
    selected_questions = random.sample(questions, min(20, len(questions)))
    
    test = Test(user_id=current_user.id, category_id=category_id)
    db.session.add(test)
    
    for question in selected_questions:
        test_question = TestQuestion(test_id=test.id, question_id=question.id)
        db.session.add(test_question)
    
    db.session.commit()
    return redirect(url_for('take_test', test_id=test.id))

@app.route('/test/<int:test_id>')
@login_required
def take_test(test_id):
    test = Test.query.get_or_404(test_id)
    if test.user_id != current_user.id:
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))
    
    return render_template('test.html', test=test)

@app.route('/test/<int:test_id>/submit', methods=['POST'])
@login_required
def submit_test(test_id):
    test = Test.query.get_or_404(test_id)
    if test.user_id != current_user.id:
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
    
    return jsonify({'redirect': url_for('test_results', test_id=test.id)})

@app.route('/test/<int:test_id>/results')
@login_required
def test_results(test_id):
    test = Test.query.get_or_404(test_id)
    if test.user_id != current_user.id:
        flash('Unauthorized access')
        return redirect(url_for('dashboard'))
    
    return render_template('results.html', test=test)
