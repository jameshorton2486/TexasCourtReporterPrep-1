from flask import Flask
from app import app, db
from models import Question, Category
import logging
import os
from utils.text_to_pdf import convert_text_to_pdf
from utils.perplexity import generate_questions

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def ensure_categories():
    """Ensure all required categories exist in the database."""
    categories = [
        ('Legal & Judicial Terminology', 'Common legal terms, court procedures, and judicial concepts'),
        ('Professional Standards & Ethics', 'Professional conduct, responsibilities, and ethical guidelines'),
        ('Transcription Standards', 'Formatting rules, technical requirements, and industry standards')
    ]
    
    with app.app_context():
        for name, description in categories:
            if not Category.get_by_name(name):
                category = Category(name=name, description=description)
                db.session.add(category)
        db.session.commit()
        logger.info("Categories verified and created if needed")

def process_pdfs():
    with app.app_context():
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
                logger.info(f"Converting {txt_file} to PDF...")
                pdf_file = convert_text_to_pdf(txt_file, 'pdf_files')
                if pdf_file:
                    logger.info(f"Successfully converted {txt_file} to PDF: {pdf_file}")
            
            # Generate additional questions using Perplexity AI
            topics = ["court reporting legal terminology", "court reporter ethics", "transcription standards"]
            for topic in topics:
                logger.info(f"Generating questions about {topic} using Perplexity AI...")
                questions = generate_questions(topic)
                if questions:
                    # Save generated questions as a new PDF
                    content = "\n\n".join([
                        f"{q['question_text']} - {q['correct_answer']}"
                        for q in questions
                    ])
                    with open(f"generated_{topic.replace(' ', '_')}.txt", 'w') as f:
                        f.write(content)
                    pdf_file = convert_text_to_pdf(f"generated_{topic.replace(' ', '_')}.txt", 'pdf_files')
                    if pdf_file:
                        logger.info(f"Saved generated questions to {pdf_file}")
            
            # Now process all PDFs
            logger.info("Processing all PDFs in pdf_files directory...")
            total_added, errors = Question.seed_from_pdfs('pdf_files')
            logger.info(f"Total questions added: {total_added}")
            
            if errors:
                logger.warning("Errors encountered during processing:")
                for error in errors:
                    logger.warning(f"- {error}")
            
            return total_added, errors
            
        except Exception as e:
            logger.error(f"Error during PDF processing: {str(e)}")
            return 0, [str(e)]

if __name__ == "__main__":
    process_pdfs()
