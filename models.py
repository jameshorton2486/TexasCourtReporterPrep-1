from datetime import datetime, timedelta
from extensions import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
from utils.pdf_parser import process_pdf_file

logger = logging.getLogger(__name__)

class User(UserMixin, db.Model):
    __tablename__ = 'users'  # Explicitly set table name to avoid conflicts
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tests = db.relationship('Test', backref='user', lazy=True, cascade='all, delete-orphan')
    question_performance = db.relationship('UserQuestionPerformance', backref='user', lazy=True)
    study_sessions = db.relationship('StudySession', backref='user', lazy=True, cascade='all, delete-orphan')
    study_timers = db.relationship('StudyTimer', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def is_administrator(self):
        return self.is_admin

    def get_weak_areas(self, category_id=None, limit=10):
        """Get questions the user needs to review based on performance"""
        query = UserQuestionPerformance.query.filter_by(user_id=self.id)
        if category_id:
            query = query.join(Question).filter(Question.category_id == category_id)
        return query.filter(
            UserQuestionPerformance.next_review_date <= datetime.utcnow()
        ).order_by(
            UserQuestionPerformance.ease_factor.asc()
        ).limit(limit).all()

    def get_upcoming_sessions(self):
        """Get upcoming study sessions"""
        return StudySession.query.filter_by(
            user_id=self.id
        ).filter(
            StudySession.start_time > datetime.utcnow()
        ).order_by(StudySession.start_time).all()

class StudyTimer(db.Model):
    __tablename__ = 'study_timers'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey('study_sessions.id', ondelete='CASCADE'))
    start_time = db.Column(db.DateTime, default=datetime.utcnow)
    duration_seconds = db.Column(db.Integer, default=0)
    is_active = db.Column(db.Boolean, default=True)
    
    def __init__(self, user_id, session_id=None):
        self.user_id = user_id
        self.session_id = session_id
        self.start_time = datetime.utcnow()
        self.is_active = True
        self.duration_seconds = 0
    
    def stop(self):
        if self.is_active:
            self.is_active = False
            self.duration_seconds = int((datetime.utcnow() - self.start_time).total_seconds())
            db.session.commit()

class StudySession(db.Model):
    __tablename__ = 'study_sessions'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'))
    start_time = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, nullable=False)
    description = db.Column(db.String(200))
    is_completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    actual_duration = db.Column(db.Integer)  # Added for tracking actual study time
    questions_reviewed = db.Column(db.Integer, default=0)  # Track number of questions reviewed
    correct_answers = db.Column(db.Integer, default=0)  # Track correct answers
    timers = db.relationship('StudyTimer', backref='session', lazy=True, cascade='all, delete-orphan')

    def __init__(self, user_id, category_id, start_time, duration_minutes, description=None):
        self.user_id = user_id
        self.category_id = category_id
        self.start_time = start_time
        self.duration_minutes = duration_minutes
        self.description = description
        self.is_completed = False

    @property
    def end_time(self):
        return self.start_time + timedelta(minutes=self.duration_minutes)

class Category(db.Model):
    __tablename__ = 'categories'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    questions = db.relationship('Question', backref='category', lazy=True, cascade='all, delete-orphan')
    tests = db.relationship('Test', backref='category', lazy=True)
    study_sessions = db.relationship('StudySession', backref='category', lazy=True)
    
    @classmethod
    def get_by_name(cls, name):
        return cls.query.filter_by(name=name).first()

class Question(db.Model):
    __tablename__ = 'questions'
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='CASCADE'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    wrong_answers = db.Column(db.JSON)
    difficulty_level = db.Column(db.Float, default=2.5)  # Added for dynamic difficulty tracking
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used = db.Column(db.DateTime)  # Track when the question was last used
    times_used = db.Column(db.Integer, default=0)  # Track how many times the question has been used
    success_rate = db.Column(db.Float, default=0.0)  # Track overall success rate
    user_performance = db.relationship('UserQuestionPerformance', backref='question', lazy=True)
    
    @classmethod
    def seed_from_pdfs(cls, pdf_directory: str) -> tuple[int, list[str]]:
        """
        Seed questions from PDF files in the specified directory.
        Returns tuple of (number of questions added, list of errors).
        """
        total_questions_added = 0
        all_errors = []
        
        for filename in os.listdir(pdf_directory):
            if filename.endswith('.pdf'):
                pdf_path = os.path.join(pdf_directory, filename)
                logger.info(f"Processing PDF file: {filename}")
                
                questions, errors = process_pdf_file(pdf_path)
                all_errors.extend(errors)
                
                for question_data in questions:
                    try:
                        category = Category.get_by_name(question_data['category'])
                        if not category:
                            logger.warning(f"Category not found: {question_data['category']}")
                            continue
                            
                        existing = cls.query.filter_by(
                            question_text=question_data['question_text'],
                            category_id=category.id
                        ).first()
                        
                        if not existing:
                            question = cls(
                                category_id=category.id,
                                question_text=question_data['question_text'],
                                correct_answer=question_data['correct_answer'],
                                wrong_answers=question_data['wrong_answers']
                            )
                            db.session.add(question)
                            total_questions_added += 1
                            
                    except Exception as e:
                        error_msg = f"Error adding question: {str(e)}"
                        logger.error(error_msg)
                        all_errors.append(error_msg)
                
                try:
                    db.session.commit()
                    logger.info(f"Added {total_questions_added} questions from {filename}")
                except Exception as e:
                    db.session.rollback()
                    error_msg = f"Error committing questions from {filename}: {str(e)}"
                    logger.error(error_msg)
                    all_errors.append(error_msg)
        
        return total_questions_added, all_errors

class Test(db.Model):
    __tablename__ = 'tests'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('categories.id', ondelete='SET NULL'))
    score = db.Column(db.Float)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_practice = db.Column(db.Boolean, default=False)
    completion_time = db.Column(db.Integer)  # Time taken to complete the test
    total_time_spent = db.Column(db.Integer)  # Total time including pauses
    questions = db.relationship('TestQuestion', backref='test', lazy=True, cascade='all, delete-orphan')

class TestQuestion(db.Model):
    __tablename__ = 'test_questions'
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('tests.id', ondelete='CASCADE'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    user_answer = db.Column(db.Text)
    is_correct = db.Column(db.Boolean)
    response_time = db.Column(db.Integer)  # Time taken to answer in seconds
    attempt_count = db.Column(db.Integer, default=1)  # Number of attempts for practice mode
    question = db.relationship('Question', backref='test_questions', lazy=True)

    def update_performance(self):
        """Update the user's performance record for this question"""
        user_id = Test.query.get(self.test_id).user_id
        perf = UserQuestionPerformance.query.filter_by(
            user_id=user_id,
            question_id=self.question_id
        ).first()

        if not perf:
            perf = UserQuestionPerformance(
                user_id=user_id,
                question_id=self.question_id
            )
            db.session.add(perf)

        perf.total_attempts += 1
        if self.is_correct:
            perf.correct_attempts += 1
            perf.consecutive_correct += 1
            perf.ease_factor = max(1.3, perf.ease_factor + 0.1)
        else:
            perf.consecutive_correct = 0
            perf.ease_factor = max(1.3, perf.ease_factor - 0.2)

        if self.is_correct:
            if perf.consecutive_correct == 1:
                perf.interval_days = 1
            elif perf.consecutive_correct == 2:
                perf.interval_days = 6
            else:
                perf.interval_days = int(perf.interval_days * perf.ease_factor)
        else:
            perf.interval_days = 1

        # Update question statistics
        self.question.times_used += 1
        self.question.last_used = datetime.utcnow()
        self.question.success_rate = (
            (self.question.success_rate * (self.question.times_used - 1) + (1 if self.is_correct else 0))
            / self.question.times_used
        )

        perf.last_attempt_date = datetime.utcnow()
        perf.next_review_date = datetime.utcnow() + timedelta(days=perf.interval_days)
        
        # Update response time analytics
        if self.response_time:
            perf.average_response_time = (
                (perf.average_response_time or 0) * perf.total_attempts + self.response_time
            ) / (perf.total_attempts + 1)
            
        db.session.commit()

class UserQuestionPerformance(db.Model):
    __tablename__ = 'user_question_performance'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id', ondelete='CASCADE'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id', ondelete='CASCADE'), nullable=False)
    last_attempt_date = db.Column(db.DateTime, default=datetime.utcnow)
    next_review_date = db.Column(db.DateTime, default=datetime.utcnow)
    ease_factor = db.Column(db.Float, default=2.5)
    interval_days = db.Column(db.Integer, default=1)
    consecutive_correct = db.Column(db.Integer, default=0)
    total_attempts = db.Column(db.Integer, default=0)
    correct_attempts = db.Column(db.Integer, default=0)
    average_response_time = db.Column(db.Float)  # Average time to answer in seconds

    def __init__(self, user_id, question_id):
        self.user_id = user_id
        self.question_id = question_id
        self.last_attempt_date = datetime.utcnow()
        self.next_review_date = datetime.utcnow()
        self.ease_factor = 2.5
        self.interval_days = 1
        self.consecutive_correct = 0
        self.total_attempts = 0
        self.correct_attempts = 0

    @property
    def accuracy(self):
        """Calculate the accuracy percentage for this question"""
        if self.total_attempts == 0:
            return 0
        return (self.correct_attempts / self.total_attempts) * 100
