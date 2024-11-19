from flask import Flask
from app import app, db
from models import Question, Category
import logging
import os
from utils.text_to_pdf import convert_text_to_pdf
from utils.perplexity import generate_questions, COURT_REPORTER_TOPICS
from utils.pdf_parser import QuestionProcessor, ProcessingError
import shutil
from datetime import datetime
import time
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class QuestionPoolManager:
    """Manages the question pool and ensures minimum question thresholds."""
    
    def __init__(self, app_context, min_threshold: int = 50):
        self.app_context = app_context
        self.min_threshold = min_threshold
        self.pdf_processor = QuestionProcessor('pdf_files', 'processed_questions')
    
    def ensure_categories(self):
        """Ensure all required categories exist in the database."""
        categories = [
            ('Legal & Judicial Terminology', 'Common legal terms, court procedures, and judicial concepts'),
            ('Professional Standards & Ethics', 'Professional conduct, responsibilities, and ethical guidelines'),
            ('Transcription Standards', 'Formatting rules, technical requirements, and industry standards'),
            ('Grammar & Vocabulary', 'Legal writing, punctuation, and specialized terminology'),
            ('Court Procedures', 'Court protocols and procedural guidelines'),
            ('Deposition Protocol', 'Deposition procedures and best practices'),
            ('Reporting Equipment', 'Court reporting technology and equipment usage'),
            ('Certification Requirements', 'Licensing and certification standards')
        ]
        
        try:
            for name, description in categories:
                if not Category.query.filter_by(name=name).first():
                    category = Category(name=name, description=description)
                    db.session.add(category)
            db.session.commit()
            logger.info("Categories verified and created if needed")
        except Exception as e:
            logger.error(f"Error ensuring categories: {str(e)}")
            db.session.rollback()
            raise

    def backup_pdfs(self) -> bool:
        """Create a backup of processed PDF files."""
        try:
            backup_dir = Path('pdf_files') / 'processed_backup' / datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_dir.mkdir(parents=True, exist_ok=True)
            
            pdf_dir = Path('pdf_files')
            for pdf_file in pdf_dir.glob('*.pdf'):
                shutil.copy2(pdf_file, backup_dir / pdf_file.name)
                
            logger.info(f"Created backup of PDF files in {backup_dir}")
            return True
        except Exception as e:
            logger.error(f"Error creating PDF backup: {str(e)}")
            return False

    def process_text_files(self) -> Tuple[int, List[str]]:
        """Process and convert text files to PDFs."""
        total_converted = 0
        errors = []
        
        try:
            txt_files = [f for f in os.listdir() if f.endswith('.txt') and 'study' in f.lower()]
            for txt_file in txt_files:
                try:
                    logger.info(f"Converting {txt_file} to PDF...")
                    pdf_file = convert_text_to_pdf(txt_file, 'pdf_files')
                    if pdf_file:
                        logger.info(f"Successfully converted {txt_file} to PDF: {pdf_file}")
                        total_converted += 1
                    else:
                        error_msg = f"Failed to convert {txt_file} to PDF"
                        logger.error(error_msg)
                        errors.append(error_msg)
                except Exception as e:
                    error_msg = f"Error processing text file {txt_file}: {str(e)}"
                    logger.error(error_msg)
                    errors.append(error_msg)
                    
            return total_converted, errors
            
        except Exception as e:
            error_msg = f"Error processing text files: {str(e)}"
            logger.error(error_msg)
            return 0, [error_msg]

    def maintain_question_pool(self) -> Tuple[int, List[str]]:
        """Ensure each category has the minimum required questions."""
        total_generated = 0
        errors = []
        
        try:
            for category in COURT_REPORTER_TOPICS:
                current_count = Question.query.join(Category).filter(
                    Category.name == category
                ).count()
                
                if current_count < self.min_threshold:
                    needed_count = self.min_threshold - current_count
                    logger.info(f"Generating {needed_count} questions for {category}")
                    
                    for attempt in range(3):
                        batch_size = min(20, needed_count)
                        questions = generate_questions(category, count=batch_size)
                        
                        if questions:
                            category_obj = Category.query.filter_by(name=category).first()
                            if not category_obj:
                                errors.append(f"Category not found: {category}")
                                break
                                
                            added_count = 0
                            for question_data in questions:
                                try:
                                    existing = Question.query.filter_by(
                                        question_text=question_data['question_text'],
                                        category_id=category_obj.id
                                    ).first()
                                    
                                    if not existing:
                                        question = Question(
                                            category_id=category_obj.id,
                                            question_text=question_data['question_text'],
                                            correct_answer=question_data['correct_answer'],
                                            wrong_answers=question_data['wrong_answers']
                                        )
                                        db.session.add(question)
                                        added_count += 1
                                        
                                except Exception as e:
                                    errors.append(f"Error adding question: {str(e)}")
                                    continue
                                    
                            if added_count > 0:
                                db.session.commit()
                                total_generated += added_count
                                needed_count -= added_count
                                logger.info(f"Added {added_count} questions to {category}")
                                
                            if needed_count <= 0:
                                break
                                
                        time.sleep(2)  # Brief pause between attempts
                        
            return total_generated, errors
            
        except Exception as e:
            error_msg = f"Error maintaining question pool: {str(e)}"
            logger.error(error_msg)
            return 0, [error_msg]

    def process_pdfs(self) -> Tuple[int, List[str]]:
        """Process PDF files and extract questions."""
        total_added = 0
        all_errors = []
        
        try:
            logger.info("Starting PDF processing...")
            
            # Ensure categories exist
            self.ensure_categories()
            
            # Create directories
            os.makedirs('pdf_files', exist_ok=True)
            os.makedirs('processed_questions', exist_ok=True)
            
            # Process text files
            converted_count, text_errors = self.process_text_files()
            all_errors.extend(text_errors)
            
            # Backup existing PDFs
            if not self.backup_pdfs():
                logger.warning("Failed to create PDF backup")
            
            # Process all PDFs
            pdf_dir = Path('pdf_files')
            for pdf_file in pdf_dir.glob('*.pdf'):
                logger.info(f"Processing PDF file: {pdf_file.name}")
                questions, errors = self.pdf_processor.process_pdf(pdf_file.name)
                
                if questions:
                    output_path = self.pdf_processor.save_questions(
                        questions,
                        f"processed_{pdf_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                    )
                    
                    if output_path:
                        # Add questions to database
                        added_count = 0
                        for question in questions:
                            try:
                                category = Category.query.filter_by(name=question.category).first()
                                if not category:
                                    logger.warning(f"Category not found: {question.category}")
                                    continue
                                    
                                db_question = Question(
                                    category_id=category.id,
                                    question_text=question.question_text,
                                    correct_answer=question.correct_answer,
                                    wrong_answers=question.wrong_answers
                                )
                                db.session.add(db_question)
                                added_count += 1
                                
                            except Exception as e:
                                error_msg = f"Error adding question to database: {str(e)}"
                                logger.error(error_msg)
                                all_errors.append(error_msg)
                                continue
                                
                        if added_count > 0:
                            db.session.commit()
                            total_added += added_count
                            logger.info(f"Added {added_count} questions from {pdf_file.name}")
                
                all_errors.extend([e.message for e in errors])
            
            # Generate additional questions if needed
            generated_count, generation_errors = self.maintain_question_pool()
            total_added += generated_count
            all_errors.extend(generation_errors)
            
            logger.info(f"Total questions added: {total_added}")
            if all_errors:
                logger.warning("Errors encountered during processing:")
                for error in all_errors:
                    logger.warning(f"- {error}")
            
            return total_added, all_errors
            
        except Exception as e:
            error_msg = f"Critical error during PDF processing: {str(e)}"
            logger.error(error_msg)
            db.session.rollback()
            return 0, [error_msg]

def process_pdfs():
    """Main entry point for PDF processing."""
    with app.app_context():
        pool_manager = QuestionPoolManager(app.app_context)
        return pool_manager.process_pdfs()

if __name__ == "__main__":
    process_pdfs()
