from datetime import datetime
from app import db
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import logging
import os
from utils.pdf_parser import process_pdf_file

logger = logging.getLogger(__name__)

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256))
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    tests = db.relationship('Test', backref='user', lazy=True, cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
        
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)
        
    def is_administrator(self):
        return self.is_admin

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    questions = db.relationship('Question', backref='category', lazy=True, cascade='all, delete-orphan')
    tests = db.relationship('Test', backref='category', lazy=True)
    
    @classmethod
    def get_by_name(cls, name):
        return cls.query.filter_by(name=name).first()

class Question(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='CASCADE'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    correct_answer = db.Column(db.Text, nullable=False)
    wrong_answers = db.Column(db.JSON)  # Store wrong answers as JSON array
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    @classmethod
    def seed_from_pdfs(cls, pdf_directory: str) -> tuple[int, list[str]]:
        """
        Seed questions from PDF files in the specified directory.
        Returns tuple of (number of questions added, list of errors).
        """
        total_questions_added = 0
        all_errors = []
        
        # Process each PDF file in the directory
        for filename in os.listdir(pdf_directory):
            if filename.endswith('.pdf'):
                pdf_path = os.path.join(pdf_directory, filename)
                logger.info(f"Processing PDF file: {filename}")
                
                questions, errors = process_pdf_file(pdf_path)
                all_errors.extend(errors)
                
                # Add questions to database
                for question_data in questions:
                    try:
                        category = Category.get_by_name(question_data['category'])
                        if not category:
                            logger.warning(f"Category not found: {question_data['category']}")
                            continue
                            
                        # Check if question already exists
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
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='CASCADE'), nullable=False)
    category_id = db.Column(db.Integer, db.ForeignKey('category.id', ondelete='SET NULL'))
    score = db.Column(db.Float)
    completed = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_practice = db.Column(db.Boolean, default=False)  # New field for practice mode
    questions = db.relationship('TestQuestion', backref='test', lazy=True, cascade='all, delete-orphan')

class TestQuestion(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    test_id = db.Column(db.Integer, db.ForeignKey('test.id', ondelete='CASCADE'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('question.id', ondelete='CASCADE'), nullable=False)
    user_answer = db.Column(db.Text)
    is_correct = db.Column(db.Boolean)
    question = db.relationship('Question', backref='test_questions', lazy=True)
