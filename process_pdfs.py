import logging
import os
from pathlib import Path
import json
import time
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from flask import Flask
from models import Question, Category, db
from utils.text_to_pdf import convert_text_to_pdf
from utils.perplexity import generate_questions, COURT_REPORTER_TOPICS
from utils.pdf_parser import QuestionProcessor, ProcessingError
from move_pdf import PDFMover

# Configure basic logging without Flask dependencies
logging.basicConfig(
    level=logging.INFO,
    format='{"timestamp": "%(asctime)s", "level": "%(levelname)s", "name": "%(name)s", "message": "%(message)s"}',
    datefmt='%Y-%m-%d %H:%M:%S,%03d'
)
logger = logging.getLogger(__name__)

class QuestionPoolManager:
    """Manages the question pool and ensures minimum question thresholds."""
    
    def __init__(self, min_threshold: int = 50):
        """Initialize with minimum threshold."""
        self.min_threshold = min_threshold
        self.pdf_processor = QuestionProcessor('pdf_files', 'processed_questions')
        self.pdf_mover = PDFMover('pdf_files')
    
    def ensure_categories(self):
        """Ensure all required categories exist in the database."""
        categories = [
            ('Legal & Judicial Terminology', 'Common legal terms, court procedures, and judicial concepts'),
            ('Professional Standards & Ethics', 'Professional conduct, responsibilities, and ethical guidelines'),
            ('Grammar & Vocabulary', 'Legal writing, punctuation, and specialized terminology'),
            ('Transcription Standards', 'Formatting rules and industry standards'),
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
            pdf_files = list(pdf_dir.glob('*.pdf'))
            if not pdf_files:
                logger.info("No PDF files to backup")
                return True

            for pdf_file in pdf_dir.glob('*.pdf'):
                shutil.copy2(pdf_file, backup_dir / pdf_file.name)
                
            logger.info(f"Created backup of {len(pdf_files)} PDF files in {backup_dir}")
            return True
        except Exception as e:
            logger.error(f"Error creating PDF backup: {str(e)}")
            return False

    def process_text_files(self) -> Tuple[int, List[str]]:
        """Process and convert text files to PDFs."""
        total_converted = 0
        errors = []
        
        try:
            # Only process study materials text file
            study_files = [f for f in os.listdir() if f.startswith('study_materials') and f.endswith('.txt')]
            if not study_files:
                logger.info("No study materials text files found")
                return 0, []

            for txt_file in study_files:
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
                    
                    retries = 3
                    for attempt in range(retries):
                        try:
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
                                    
                        except Exception as e:
                            logger.error(f"Attempt {attempt + 1}/{retries} failed: {str(e)}")
                            if attempt == retries - 1:
                                errors.append(f"Failed to generate questions for {category} after {retries} attempts")
                        
                        time.sleep(2)  # Brief pause between attempts
                        
            return total_generated, errors
            
        except Exception as e:
            error_msg = f"Error maintaining question pool: {str(e)}"
            logger.error(error_msg)
            return 0, [error_msg]

    def process_pdfs(self) -> Tuple[int, List[str]]:
        """Process PDF files and extract questions with enhanced error handling."""
        total_added = 0
        all_errors = []
        start_time = time.time()
        
        try:
            logger.info("Starting PDF processing...")
            
            # Create directories
            os.makedirs('pdf_files', exist_ok=True)
            os.makedirs('processed_questions', exist_ok=True)
            
            # Process text files
            converted_count, text_errors = self.process_text_files()
            all_errors.extend(text_errors)
            
            # Backup existing PDFs
            if not self.backup_pdfs():
                logger.warning("Failed to create PDF backup, proceeding with caution")
            
            # Process all PDFs
            pdf_dir = Path('pdf_files')
            pdf_files = list(pdf_dir.glob('*.pdf'))
            logger.info(f"Found {len(pdf_files)} PDF files to process")
            
            for pdf_file in pdf_files:
                try:
                    logger.info(f"Processing PDF file: {pdf_file.name}")
                    questions, errors = self.pdf_processor.process_pdf(pdf_file.name)
                    all_errors.extend([e.message for e in errors])
                    
                    if questions:
                        # Save processed questions
                        output_name = f"processed_{pdf_file.stem}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
                        output_path = self.pdf_processor.save_questions(questions, output_name)
                        
                        if output_path:
                            # Add questions to database with enhanced validation
                            added_count = 0
                            for question in questions:
                                try:
                                    # Validate category
                                    category = Category.query.filter_by(name=question.category).first()
                                    if not category:
                                        logger.warning(f"Category not found: {question.category}")
                                        continue
                                    
                                    # Check for duplicates
                                    existing = Question.query.filter_by(
                                        question_text=question.question_text,
                                        category_id=category.id
                                    ).first()
                                    
                                    if not existing:
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
                    else:
                        logger.warning(f"No valid questions extracted from {pdf_file.name}")
                    
                except Exception as e:
                    error_msg = f"Error processing PDF {pdf_file.name}: {str(e)}"
                    logger.error(error_msg)
                    all_errors.append(error_msg)
                    continue
            
            # Generate additional questions if needed
            generated_count, generation_errors = self.maintain_question_pool()
            total_added += generated_count
            all_errors.extend(generation_errors)
            
            processing_time = time.time() - start_time
            logger.info(f"PDF processing completed in {processing_time:.2f} seconds")
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

def create_app():
    """Create a minimal Flask app for database operations."""
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL')
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    db.init_app(app)
    return app

def process_pdfs():
    """Main entry point for PDF processing with enhanced error handling."""
    app = create_app()
    with app.app_context():
        try:
            pool_manager = QuestionPoolManager()
            pool_manager.ensure_categories()
            return pool_manager.process_pdfs()
        except Exception as e:
            logger.error(f"Fatal error in process_pdfs: {str(e)}")
            return 0, [str(e)]

if __name__ == "__main__":
    total_questions, errors = process_pdfs()
    if errors:
        print("\nErrors encountered:")
        for error in errors:
            print(f"- {error}")
    print(f"\nTotal questions processed: {total_questions}")
