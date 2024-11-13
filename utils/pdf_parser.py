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
    """Split text into question-answer pairs with improved separation."""
    pairs = []
    
    # Split on numbered questions or strong question patterns
    questions = re.split(r'(?:\d+\.\s+|\n\s*Q[.:]\s+|(?=(?:[A-Z][^.!?]*[.!?])(?:\s+[A-Z]|$)))', text)
    
    for q in questions:
        if not q.strip():
            continue
            
        # Look for answer delimiter patterns
        answer_patterns = [
            r'\s*-\s+',           # Dash delimiter
            r'\s*:\s+',           # Colon delimiter
            r'\s*Answer\s*[:.-]\s*',  # Explicit answer marker
            r'\s*A[:.]\s+'        # A. style answer marker
        ]
        
        for pattern in answer_patterns:
            parts = re.split(pattern, q, maxsplit=1)
            if len(parts) == 2:
                question = clean_text(parts[0])
                answer = clean_text(parts[1])
                
                # Verify question ends with proper punctuation
                if not re.search(r'[.!?]$', question):
                    question = question + '?'
                
                # Ensure minimum lengths and proper format
                if (question and answer and 
                    len(question.split()) >= 3 and 
                    not answer.lower().startswith('not') and
                    not question.lower().startswith('what is')):
                    pairs.append({
                        'question': question,
                        'answer': answer
                    })
                break
    
    return pairs

def generate_wrong_answers(correct_answer: str, category: str) -> List[str]:
    """Generate contextually relevant wrong answers based on category and correct answer."""
    wrong_answers = []
    
    if category == 'Professional Standards & Ethics':
        if correct_answer.lower() in ['yes', 'no']:
            return ['Yes', 'No', 'Only with court permission', 'Only in federal courts']
        
        # Time period answers
        time_match = re.search(r'(\d+)\s*(year|month|day)s?', correct_answer)
        if time_match:
            try:
                base = int(time_match.group(1))
                unit = time_match.group(2)
                alternatives = [
                    f"{base * 2} {unit}s",
                    f"{max(1, base - 1)} {unit}s",
                    f"{base + 2} {unit}s"
                ]
                return [alt for alt in alternatives if alt != correct_answer]
            except (ValueError, AttributeError):
                pass
                
    elif category == 'Transcription Standards':
        # WPM-related answers
        wpm_match = re.search(r'(\d+)\s*WPM', correct_answer, re.IGNORECASE)
        if wpm_match:
            try:
                base = int(wpm_match.group(1))
                return [
                    f"{base - 25} WPM",
                    f"{base + 25} WPM",
                    f"{base * 2} WPM"
                ]
            except (ValueError, AttributeError):
                pass
        
        # Formatting-related answers
        if 'margin' in correct_answer.lower():
            return ['1 inch', '1.5 inches', '2 inches', '2.5 inches']
        if 'font' in correct_answer.lower():
            return ['Times New Roman 12pt', 'Arial 12pt', 'Courier New 12pt']
            
    elif category == 'Legal & Judicial Terminology':
        # For legal terms, provide contextually relevant but incorrect definitions
        if len(correct_answer.split()) > 3:
            base_terms = ['court', 'judge', 'attorney', 'witness', 'evidence', 'testimony']
            return [
                f"A legal process requiring {term} approval" for term in base_terms
                if term not in correct_answer.lower()
            ][:3]
    
    # If no specific rules matched, generate contextual alternatives
    words = correct_answer.split()
    if len(words) > 2:
        # Create variations by changing key terms
        variations = []
        for i in range(len(words)):
            if len(words[i]) > 3:
                new_words = words.copy()
                if words[i].lower() in ['must', 'shall', 'will']:
                    new_words[i] = 'may'
                elif words[i].lower() in ['all', 'every']:
                    new_words[i] = 'some'
                elif words[i].isdigit():
                    new_words[i] = str(int(words[i]) * 2)
                variations.append(' '.join(new_words))
        if variations:
            return variations[:3]
    
    # Fallback with opposite or modified meanings
    base_words = ['must', 'shall', 'all', 'never', 'always']
    return [
        f"Only when specifically ordered by the court",
        f"At the discretion of the {random.choice(['judge', 'attorney', 'court reporter'])}",
        f"Under special circumstances only"
    ]

def validate_question(question: Dict) -> bool:
    """Validate a question entry with enhanced checks."""
    if not question.get('question_text') or not question.get('correct_answer'):
        return False
        
    question_text = question['question_text']
    correct_answer = question['correct_answer']
    wrong_answers = question.get('wrong_answers', [])
    
    # Question format validation
    if (len(question_text.split()) < 4 or 
        not re.search(r'[?:.]$', question_text) or
        len(correct_answer.split()) < 2):
        return False
    
    # Answer distinctness validation
    answers = [correct_answer] + wrong_answers
    if len(set(answers)) != len(answers):
        return False
    
    # Check for answer relevance
    for answer in wrong_answers:
        # Answers shouldn't be too similar to the question
        if (answer.lower() in question_text.lower() or 
            question_text.lower() in answer.lower()):
            return False
        # Answers shouldn't be template-style responses
        if (answer.lower().startswith('not ') or 
            answer.lower().startswith('the opposite of ')):
            return False
        # Answers should have meaningful content
        if len(answer.split()) < 2:
            return False
    
    # Check for nonsensical answers
    common_words = {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for'}
    for answer in answers:
        words = set(answer.lower().split())
        if len(words - common_words) < 1:
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

def parse_questions(text: str) -> List[Dict]:
    """Parse questions, correct answers, and wrong answers from text."""
    questions = []
    # Split text into sections based on common delimiters
    sections = re.split(r'\n{2,}|\r\n{2,}|\f', text)
    
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
