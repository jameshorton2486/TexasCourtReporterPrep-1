from flask import Flask
from app import app, db
from models import Question, Category
import logging
import os
from utils.text_to_pdf import convert_text_to_pdf
from utils.perplexity import generate_questions, COURT_REPORTER_TOPICS
import shutil
from datetime import datetime
import time

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_categories():
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
    
    with app.app_context():
        try:
            for name, description in categories:
                if not Category.get_by_name(name):
                    category = Category(name=name, description=description)
                    db.session.add(category)
            db.session.commit()
            logger.info("Categories verified and created if needed")
        except Exception as e:
            logger.error(f"Error ensuring categories: {str(e)}")
            db.session.rollback()
            raise

def backup_pdfs(pdf_directory: str):
    """Create a backup of processed PDF files."""
    try:
        backup_dir = os.path.join(pdf_directory, 'processed_backup', 
                                datetime.now().strftime('%Y%m%d_%H%M%S'))
        os.makedirs(backup_dir, exist_ok=True)
        
        for filename in os.listdir(pdf_directory):
            if filename.endswith('.pdf'):
                src_path = os.path.join(pdf_directory, filename)
                dst_path = os.path.join(backup_dir, filename)
                shutil.copy2(src_path, dst_path)
                
        logger.info(f"Created backup of PDF files in {backup_dir}")
        return True
    except Exception as e:
        logger.error(f"Error creating PDF backup: {str(e)}")
        return False

def maintain_question_pool(min_threshold=50):
    """Ensure each category has minimum required questions."""
    with app.app_context():
        try:
            question_counts = Question.get_question_count_by_category()
            total_generated = 0
            
            for category in COURT_REPORTER_TOPICS:
                current_count = question_counts.get(category, 0)
                if current_count < min_threshold:
                    needed_count = min_threshold - current_count
                    logger.info(f"Generating {needed_count} questions for {category}")
                    
                    for attempt in range(3):  # Try up to 3 times
                        batch_size = min(20, needed_count)  # Generate in smaller batches
                        questions = generate_questions(category, count=batch_size)
                        
                        if questions:
                            added = Question.generate_questions_for_category(category, len(questions))
                            total_generated += added
                            needed_count -= added
                            
                            if needed_count <= 0:
                                break
                        
                        time.sleep(2)  # Brief pause between attempts
                        
            logger.info(f"Generated {total_generated} new questions across all categories")
            return total_generated
            
        except Exception as e:
            logger.error(f"Error maintaining question pool: {str(e)}")
            return 0

def process_pdfs():
    """Process PDF files and ensure minimum question threshold."""
    with app.app_context():
        total_added = 0
        all_errors = []
        
        try:
            logger.info("Starting PDF processing...")
            
            # Ensure categories exist
            ensure_categories()
            
            # Create pdf_files directory if it doesn't exist
            os.makedirs('pdf_files', exist_ok=True)
            logger.info("Created pdf_files directory")
            
            # Process text files first
            txt_files = [f for f in os.listdir() if f.endswith('.txt') and 'study' in f.lower()]
            for txt_file in txt_files:
                try:
                    logger.info(f"Converting {txt_file} to PDF...")
                    pdf_file = convert_text_to_pdf(txt_file, 'pdf_files')
                    if pdf_file:
                        logger.info(f"Successfully converted {txt_file} to PDF: {pdf_file}")
                    else:
                        logger.error(f"Failed to convert {txt_file} to PDF")
                except Exception as e:
                    logger.error(f"Error processing text file {txt_file}: {str(e)}")
                    all_errors.append(f"Text file conversion error: {str(e)}")
            
            # Create backup before processing
            if not backup_pdfs('pdf_files'):
                logger.warning("Failed to create PDF backup")
            
            # Process all PDFs
            logger.info("Processing all PDFs in pdf_files directory...")
            questions_added, processing_errors = Question.seed_from_pdfs('pdf_files')
            total_added += questions_added
            all_errors.extend(processing_errors)
            
            # Check and maintain minimum question threshold
            logger.info("Checking question counts and generating additional questions if needed...")
            generated_count = maintain_question_pool(min_threshold=50)
            total_added += generated_count
            
            if total_added > 0:
                logger.info(f"Successfully added {total_added} questions ({questions_added} from PDFs, {generated_count} generated)")
            else:
                logger.warning("No questions were added during processing")
            
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

if __name__ == "__main__":
    process_pdfs()
