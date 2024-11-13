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
    """Clean and normalize text content."""
    # Remove unwanted headers/footers and normalize whitespace
    text = re.sub(r'Question\s+\d+\s+of\s+\d+', '', text)
    text = re.sub(r'Stuvia\.com.*?Study Material\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s+', ' ', text)
    
    # Handle question numbers and formatting
    text = re.sub(r'(\d+\.)\s*([A-Z])', r'\1 \2', text)  # Ensure space after question numbers
    text = re.sub(r'\n+(?=[A-D]\.|\([A-D]\))', ' ', text)  # Join lines before answer choices
    text = re.sub(r'\s*\([^)]*\)\s*$', '', text)  # Remove trailing parentheticals
    text = re.sub(r'\s*-\s*correct answer\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[.*?\]\s*', ' ', text)  # Remove bracketed content
    
    return text.strip()

def split_into_qa_pairs(text: str) -> List[Dict]:
    """Split text into question-answer pairs with enhanced boundary detection."""
    questions = []
    
    # Split into question blocks with stronger boundary detection
    # Look for numbered questions, question prefixes, or clear question starts
    blocks = re.split(r'(?:\n{2,}|\r\n{2,}|\f)(?=(?:\d+\.|\(?[A-D]\)|\b(?:What|Who|When|Where|Why|How|Should|Can|Is|Are|Does|Do|Will|Which)\b))', text)
    
    for block in blocks:
        # Extract question number and text using improved pattern
        question_match = re.match(
            r'^(?:(\d+)\.?\s*)?(?:Q[:.]\s*)?([^?]+\??)',
            block,
            re.IGNORECASE | re.DOTALL
        )
        
        if not question_match:
            continue
            
        question_number = question_match.group(1)
        question_text = clean_text(question_match.group(2))
        
        # Ensure question ends with question mark
        if not question_text.endswith('?'):
            question_text += '?'
        
        # Find answer choices with improved pattern matching
        answer_pattern = r'(?:^|\n)\s*([A-D])[\)\.]\s*(.*?)(?=(?:\n\s*[A-D][\)\.]\s*|\Z))'
        answer_matches = list(re.finditer(answer_pattern, block[question_match.end():], re.MULTILINE | re.DOTALL))
        
        # Verify answers are in correct order and properly formatted
        answers = []
        expected_letters = ['A', 'B', 'C', 'D']
        
        for i, match in enumerate(answer_matches):
            if i >= len(expected_letters) or match.group(1) != expected_letters[i]:
                logger.warning(f"Answer choices out of order in question: {question_text}")
                continue
                
            answer_text = clean_text(match.group(2))
            if answer_text:
                if not answer_text.endswith(('.', '!', '?')):
                    answer_text += '.'
                if not answer_text[0].isupper():
                    answer_text = answer_text[0].upper() + answer_text[1:]
                answers.append((match.group(1), answer_text))
        
        # Find correct answer with improved pattern
        correct_marker = re.search(
            r'(?:correct(?:\s+answer)?[:.-]\s*|answer[:.-]\s*|[Cc]orrect:\s*)([A-D])',
            block,
            re.IGNORECASE
        )
        
        if len(answers) == 4 and correct_marker:
            try:
                correct_letter = correct_marker.group(1).upper()
                correct_index = ord(correct_letter) - ord('A')
                
                if 0 <= correct_index < len(answers):
                    question_entry = {
                        'question_number': question_number,
                        'question_text': question_text,
                        'correct_answer': answers[correct_index][1],
                        'wrong_answers': [ans[1] for i, ans in enumerate(answers) if i != correct_index][:3]
                    }
                    if validate_question(question_entry):
                        questions.append(question_entry)
                        logger.info(f"Successfully parsed question: {question_text[:50]}...")
                    
            except (ValueError, IndexError) as e:
                logger.warning(f"Error processing answers for question: {question_text} - {str(e)}")
                
    return questions

def validate_question(question: Dict) -> bool:
    """Validate a question entry with enhanced checks."""
    try:
        # Check required fields
        required_fields = ['question_text', 'correct_answer', 'wrong_answers']
        if not all(key in question for key in required_fields):
            logger.warning(f"Missing required fields in question")
            return False
        
        # Question structure validation
        question_text = question['question_text']
        
        # Basic format validation
        if not (
            len(question_text.split()) >= 3 and  # Minimum 3 words
            question_text.endswith('?') and  # Ends with question mark
            (
                re.match(r'^(?:\d+\.\s*)?[A-Z]', question_text) or  # Starts with number or capital
                re.match(r'^(?:\d+\.\s*)?(?:What|Who|When|Where|Why|How|Should|Can|Is|Are|Does|Do|Will|Which)\b', question_text, re.IGNORECASE)  # Has proper prefix
            )
        ):
            logger.warning(f"Invalid question structure: {question_text}")
            return False
        
        # Answer validation
        all_answers = [question['correct_answer']] + question['wrong_answers']
        
        if len(all_answers) != 4:
            logger.warning(f"Question must have exactly 4 answers")
            return False
        
        # Validate each answer
        for answer in all_answers:
            if not (
                len(answer.split()) >= 2 and  # Minimum 2 words
                answer[0].isupper() and  # Starts with capital
                answer[-1] in '.!?' and  # Proper ending punctuation
                len(answer) >= 10  # Minimum length for meaningful answer
            ):
                logger.warning(f"Invalid answer format: {answer}")
                return False
        
        # Check for answer distinctness (case-insensitive)
        if len(set(map(str.lower, all_answers))) != len(all_answers):
            logger.warning(f"Duplicate answers found")
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
            'appointed', 'salary', 'fees'
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