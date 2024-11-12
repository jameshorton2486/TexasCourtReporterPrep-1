import os
import logging
import PyPDF2
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    """Extract text content from a PDF file."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            text = ''
            for page in reader.pages:
                text += page.extract_text() + '\n'
            logger.info(f"Successfully extracted text from {pdf_path}")
            return text
    except Exception as e:
        logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        return None

def parse_questions(text: str) -> List[Dict]:
    """Parse questions, correct answers, and wrong answers from text."""
    questions = []
    current_question = None
    
    # Split text into lines and process
    lines = text.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        # Question typically ends with a question mark
        if '?' in line:
            if current_question:
                questions.append(current_question)
            current_question = {
                'question_text': line.strip(),
                'correct_answer': None,
                'wrong_answers': []
            }
        elif current_question and not current_question['correct_answer']:
            # First answer after question is typically correct
            current_question['correct_answer'] = line.strip()
        elif current_question:
            # Subsequent answers are wrong options
            current_question['wrong_answers'].append(line.strip())
            
    # Add the last question if exists
    if current_question and current_question['correct_answer']:
        questions.append(current_question)
    
    logger.info(f"Extracted {len(questions)} questions from text")
    return questions

def categorize_question(question_text: str) -> str:
    """Determine the category for a question based on its content."""
    keywords = {
        'Legal & Judicial Terminology': ['legal', 'court', 'judicial', 'law', 'jurisdiction', 'stare decisis', 'amicus'],
        'Professional Standards & Ethics': ['ethics', 'professional', 'conduct', 'responsibility', 'confidential'],
        'Grammar & Vocabulary': ['grammar', 'spelling', 'punctuation', 'vocabulary', 'definition'],
        'Transcription Standards': ['format', 'transcript', 'margin', 'indentation', 'certification']
    }
    
    question_lower = question_text.lower()
    for category, terms in keywords.items():
        if any(term.lower() in question_lower for term in terms):
            return category
            
    return 'Legal & Judicial Terminology'  # Default category

def process_pdf_file(pdf_path: str) -> Tuple[List[Dict], List[str]]:
    """Process a PDF file and return extracted questions and errors."""
    errors = []
    questions = []
    
    try:
        text = extract_text_from_pdf(pdf_path)
        if not text:
            errors.append(f"Failed to extract text from {pdf_path}")
            return [], errors
            
        raw_questions = parse_questions(text)
        
        # Validate and categorize questions
        for q in raw_questions:
            if not q['question_text'] or not q['correct_answer'] or len(q['wrong_answers']) < 2:
                errors.append(f"Invalid question format: {q['question_text']}")
                continue
                
            q['category'] = categorize_question(q['question_text'])
            questions.append(q)
        
        logger.info(f"Successfully processed {len(questions)} valid questions from {pdf_path}")
        
    except Exception as e:
        error_msg = f"Error processing PDF {pdf_path}: {str(e)}"
        logger.error(error_msg)
        errors.append(error_msg)
    
    return questions, errors
