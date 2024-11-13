import os
import logging
import PyPDF2
import random
from typing import Dict, List, Tuple, Optional
import re

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

def clean_text(text: str) -> str:
    """Clean and normalize text content with enhanced formatting."""
    # Remove unwanted headers/footers
    text = re.sub(r'Question\s+\d+\s+of\s+\d+', '', text)
    text = re.sub(r'Stuvia\.com.*?Study Material\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    
    # Ensure proper question format
    text = text.strip()
    if not text.endswith('?'):
        text = text.rstrip('.') + '?'
    
    # Ensure complete sentences
    if text and not text[0].isupper():
        text = text[0].upper() + text[1:]
        
    # Add context if needed
    if len(text.split()) < 8:  # Very short questions likely lack context
        logger.warning(f"Question may lack context: {text}")
        return None
        
    return text

def check_answer_relevance(question_text: str, answer: str) -> bool:
    """Check if an answer is relevant to the question."""
    # Convert to lowercase for comparison
    q_words = set(word.lower() for word in question_text.split() if len(word) > 3)
    a_words = set(word.lower() for word in answer.split() if len(word) > 3)
    
    # Check word overlap
    common_words = q_words.intersection(a_words)
    if len(common_words) < 2:  # Require at least 2 significant words in common
        return False
        
    # Check answer completeness
    if len(answer.split()) < 5:  # Require minimum length for meaningful answers
        return False
        
    return True

def split_into_qa_pairs(text: str) -> List[Dict]:
    """Split text into question-answer pairs with enhanced format and validation."""
    questions = []
    
    # Enhanced pattern for question blocks
    question_pattern = r'(?:Question:|Q:|\d+[\.:])?\s*([^?]+\??)\s*(?:A[\.:])?\s*(.*?)(?=(?:Question:|Q:|\d+[\.:])|\Z)'
    matches = list(re.finditer(question_pattern, text, re.DOTALL | re.IGNORECASE))
    
    for match in matches:
        try:
            question_text = clean_text(match.group(1))
            if not question_text:
                continue
                
            answers_text = match.group(2)
            
            # Enhanced answer extraction pattern
            answer_pattern = r'(?:^|\n)\s*([A-D])[\.:]\s*(.*?)(?=(?:\n\s*[A-D][\.:]\s*|\Z))'
            answer_matches = list(re.finditer(answer_pattern, answers_text, re.MULTILINE | re.DOTALL))
            
            if len(answer_matches) != 4:
                logger.warning(f"Incorrect number of answers: {question_text}")
                continue
                
            answers = []
            for ans_match in answer_matches:
                letter = ans_match.group(1)
                answer_text = clean_text(ans_match.group(2))
                if not answer_text or not check_answer_relevance(question_text, answer_text):
                    continue
                answers.append((letter, answer_text))
            
            # Find correct answer with improved pattern
            correct_marker = re.search(
                r'(?:correct(?:\s+answer)?[:.-]\s*|answer[:.-]\s*|[Cc]orrect:\s*)([A-D])',
                answers_text,
                re.IGNORECASE
            )
            
            if not correct_marker:
                logger.warning(f"No clear correct answer marker: {question_text}")
                continue
                
            correct_letter = correct_marker.group(1).upper()
            correct_index = ord(correct_letter) - ord('A')
            
            if 0 <= correct_index < len(answers):
                # Create question entry with enhanced validation
                question_entry = {
                    'question_text': f"Question: {question_text}",
                    'correct_answer': answers[correct_index][1],
                    'wrong_answers': [ans[1] for i, ans in enumerate(answers) if i != correct_index]
                }
                
                # Additional validation
                if validate_question(question_entry):
                    questions.append(question_entry)
                    logger.info(f"Successfully parsed question: {question_text[:50]}...")
                    
        except Exception as e:
            logger.error(f"Error processing question block: {str(e)}")
            continue
            
    return questions

def validate_question(question: Dict) -> bool:
    """Validate a question entry with enhanced checks."""
    try:
        # Check required fields
        required_fields = ['question_text', 'correct_answer', 'wrong_answers']
        if not all(key in question for key in required_fields):
            logger.warning("Missing required fields in question")
            return False
        
        # Question structure validation
        question_text = question['question_text']
        
        # Enhanced format validation
        if not (
            question_text.startswith('Question:') and
            len(question_text.split()) >= 8 and  # Require more context
            question_text.endswith('?') and  # Must be a proper question
            re.search(r'\b(?:what|who|when|where|why|how|should|can|is|are|does|do|will|which)\b', 
                     question_text, re.IGNORECASE)  # Must contain question word
        ):
            logger.warning(f"Invalid question structure: {question_text}")
            return False
        
        # Answer validation
        all_answers = [question['correct_answer']] + question['wrong_answers']
        
        if len(all_answers) != 4:
            logger.warning("Question must have exactly 4 answers")
            return False
        
        # Enhanced answer validation
        for i, answer in enumerate(all_answers):
            if not (
                len(answer.split()) >= 5 and  # Require more context in answers
                answer[0].isupper() and  # Proper capitalization
                answer[-1] in '.!?' and  # Proper ending punctuation
                len(answer) >= 20 and  # Minimum length for meaningful answer
                check_answer_relevance(question_text, answer)  # Check relevance
            ):
                logger.warning(f"Invalid answer format or relevance: {answer}")
                return False
        
        # Check answer distinctness (case-insensitive)
        if len(set(map(str.lower, all_answers))) != len(all_answers):
            logger.warning("Duplicate answers found")
            return False
        
        # Validate answer similarity (length should not vary too much)
        lengths = [len(ans) for ans in all_answers]
        avg_length = sum(lengths) / len(lengths)
        if any(abs(len(ans) - avg_length) > avg_length * 0.5 for ans in all_answers):
            logger.warning("Answer lengths vary too much")
            return False
        
        return True
        
    except Exception as e:
        logger.error(f"Error validating question: {str(e)}")
        return False

def process_pdf_file(pdf_path: str) -> Tuple[List[Dict], List[str]]:
    """Process a PDF file and return extracted questions and errors."""
    errors = []
    questions = []
    
    try:
        text = extract_text_from_pdf(pdf_path)
        if not text:
            errors.append(f"Failed to extract text from {pdf_path}")
            return [], errors
            
        extracted_questions = split_into_qa_pairs(text)
        
        # Validate and process questions
        for q in extracted_questions:
            if validate_question(q):
                q['category'] = categorize_question(q['question_text'])
                questions.append(q)
            else:
                errors.append(f"Invalid question format: {q.get('question_text', 'No question text')}")
        
        logger.info(f"Successfully processed {len(questions)} valid questions from {pdf_path}")
        
    except Exception as e:
        error_msg = f"Error processing PDF {pdf_path}: {str(e)}"
        logger.error(error_msg)
        errors.append(error_msg)
    
    return questions, errors

def categorize_question(question_text: str) -> str:
    """Categorize the question based on its content."""
    keywords = {
        'Legal & Judicial Terminology': [
            'legal', 'court', 'judicial', 'law', 'jurisdiction', 'stare decisis', 'amicus',
            'motion', 'pleading', 'criminal', 'civil', 'judge', 'attorney', 'counsel'
        ],
        'Professional Standards & Ethics': [
            'ethics', 'professional', 'conduct', 'responsibility', 'confidential',
            'csr', 'court reporter', 'certification', 'license', 'board', 'oath',
            'appointed', 'salary', 'fees', 'conflict', 'interest', 'disclosure'
        ],
        'Grammar & Vocabulary': [
            'grammar', 'spelling', 'punctuation', 'vocabulary', 'definition',
            'word', 'sentence', 'paragraph', 'usage', 'style'
        ],
        'Transcription Standards': [
            'format', 'transcript', 'margin', 'indentation', 'certification',
            'wpm', 'dictation', 'speed', 'accuracy', 'notes', 'deposition',
            'q & a', 'jury charge', 'literary'
        ]
    }
    
    question_lower = question_text.lower()
    max_matches = 0
    best_category = 'Legal & Judicial Terminology'  # Default category
    
    for category, terms in keywords.items():
        matches = sum(1 for term in terms if term.lower() in question_lower)
        if matches > max_matches:
            max_matches = matches
            best_category = category
            
    return best_category