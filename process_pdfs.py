from flask import Flask
from app import app, db
from models import Question, Category
import logging
import os
from utils.text_to_pdf import convert_text_to_pdf
from utils.perplexity import generate_questions
import shutil
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_categories():
    """Ensure all required categories exist in the database."""
    categories = [
        ('Legal & Judicial Terminology', 'Common legal terms, court procedures, and judicial concepts'),
        ('Professional Standards & Ethics', 'Professional conduct, responsibilities, and ethical guidelines'),
        ('Transcription Standards', 'Formatting rules, technical requirements, and industry standards'),
        ('Grammar & Vocabulary', 'Legal writing, punctuation, and specialized terminology')
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

def process_pdfs():
    """Process PDF files with enhanced error handling and validation."""
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
            
            # Generate additional questions using Perplexity AI
            topics = [
                "court reporting legal terminology",
                "court reporter ethics",
                "transcription standards",
                "legal writing and grammar"
            ]
            
            for topic in topics:
                try:
                    logger.info(f"Generating questions about {topic} using Perplexity AI...")
                    questions = generate_questions(topic)
                    if questions:
                        content = "\n\n".join([
                            f"Question: {q['question_text']}\n"
                            f"A. {q['correct_answer']}\n"
                            f"B. {q['wrong_answers'][0]}\n"
                            f"C. {q['wrong_answers'][1]}\n"
                            f"D. {q['wrong_answers'][2]}\n"
                            f"Correct: A"
                            for q in questions
                        ])
                        
                        filename = f"generated_{topic.replace(' ', '_')}.txt"
                        with open(filename, 'w') as f:
                            f.write(content)
                            
                        pdf_file = convert_text_to_pdf(filename, 'pdf_files')
                        if pdf_file:
                            logger.info(f"Saved generated questions to {pdf_file}")
                        else:
                            logger.error(f"Failed to convert {filename} to PDF")
                except Exception as e:
                    logger.error(f"Error generating questions for {topic}: {str(e)}")
                    all_errors.append(f"Question generation error: {str(e)}")
            
            # Create backup before processing
            if not backup_pdfs('pdf_files'):
                logger.warning("Failed to create PDF backup")
            
            # Now process all PDFs
            logger.info("Processing all PDFs in pdf_files directory...")
            total_added, processing_errors = Question.seed_from_pdfs('pdf_files')
            all_errors.extend(processing_errors)
            
            if total_added > 0:
                logger.info(f"Successfully added {total_added} questions")
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
