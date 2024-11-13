import os
import logging
import PyPDF2
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
    # Remove extra whitespace
    text = ' '.join(text.split())
    # Remove common PDF artifacts and marketing text
    text = re.sub(r'\s*Stuvia\.com.*?Study Material\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\([^)]*\)\s*$', '', text)
    text = re.sub(r'\s*-\s*correct answer\s*', ' - ', text, flags=re.IGNORECASE)
    return text.strip()

def split_into_qa_pairs(text: str) -> List[Dict]:
    """Split text into question-answer pairs."""
    pairs = []
    # Split on question patterns
    questions = re.split(r'(?=(?:[A-Z][^?]*\?|[A-Z][^:]*:))', text)
    
    for q in questions:
        if not q.strip():
            continue
            
        # Split into question and answer parts
        parts = re.split(r'\s*-\s*', q, maxsplit=1)
        if len(parts) == 2:
            question = clean_text(parts[0])
            answer = clean_text(parts[1])
            if question and answer and len(question.split()) >= 3:
                pairs.append({
                    'question': question,
                    'answer': answer
                })
    
    return pairs

def parse_questions(text: str) -> List[Dict]:
    """Parse questions, correct answers, and wrong answers from text."""
    questions = []
    # Split text into sections based on common delimiters
    sections = re.split(r'\n{2,}|\r\n{2,}', text)
    
    for section in sections:
        # Get question-answer pairs from this section
        qa_pairs = split_into_qa_pairs(section)
        
        for pair in qa_pairs:
            # Generate plausible wrong answers based on the category
            category = categorize_question(pair['question'])
            wrong_answers = generate_wrong_answers(pair['answer'], category)
            
            if wrong_answers and len(wrong_answers) >= 2:
                questions.append({
                    'question_text': pair['question'],
                    'correct_answer': pair['answer'],
                    'wrong_answers': wrong_answers
                })
    
    return questions

def generate_wrong_answers(correct_answer: str, category: str) -> List[str]:
    """Generate plausible wrong answers based on the category and correct answer."""
    if category == 'Professional Standards & Ethics':
        if correct_answer.lower() in ['yes', 'no']:
            return ['Yes', 'No', 'Only with permission']
        
        # Check for time periods
        time_match = re.search(r'\d+\s*(?:year|month)s?', correct_answer)
        if time_match:
            try:
                base = int(time_match.group(0).split()[0])
                return [
                    re.sub(r'\d+', str(base + 1), correct_answer),
                    re.sub(r'\d+', str(base - 1), correct_answer),
                    re.sub(r'\d+', str(base * 2), correct_answer)
                ]
            except (ValueError, AttributeError):
                pass
                
    elif category == 'Transcription Standards':
        # Check for WPM values
        wpm_match = re.search(r'\d+\s*WPM', correct_answer, re.IGNORECASE)
        if wpm_match:
            try:
                base = int(re.search(r'\d+', wpm_match.group(0)).group())
                return [
                    re.sub(r'\d+', str(base + 25), correct_answer),
                    re.sub(r'\d+', str(base - 25), correct_answer),
                    re.sub(r'\d+', str(base + 50), correct_answer)
                ]
            except (ValueError, AttributeError):
                pass
    
    # Default wrong answers for other categories
    return [
        f"Not {correct_answer}",
        f"The opposite of {correct_answer}",
        f"Something different than {correct_answer}"
    ]

def categorize_question(question_text: str) -> str:
    """Determine the category for a question based on its content."""
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

def validate_question(question: Dict) -> bool:
    """Validate a question entry."""
    if not question.get('question_text') or not question.get('correct_answer'):
        return False
        
    # Ensure question text is meaningful and ends with question mark or colon
    question_text = question['question_text']
    if len(question_text.split()) < 4 or not (question_text.endswith('?') or question_text.endswith(':')):
        return False
        
    # Ensure we have enough wrong answers
    if len(question.get('wrong_answers', [])) < 2:
        return False
        
    # Ensure answers are unique and meaningful
    answers = [question['correct_answer']] + question['wrong_answers']
    if len(set(answers)) != len(answers):
        return False
        
    # Ensure answers aren't too similar to each other
    for ans in answers:
        if len(ans.split()) < 1:
            return False
    
    return True

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
