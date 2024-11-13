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
    text = ' '.join(text.split())
    text = re.sub(r'\s*Stuvia\.com.*?Study Material\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\([^)]*\)\s*$', '', text)
    text = re.sub(r'\s*-\s*correct answer\s*', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\s*\[.*?\]\s*', ' ', text)  # Remove bracketed content
    text = re.sub(r'\s+', ' ', text)  # Normalize whitespace
    return text.strip()

def add_question_prefix(question: str) -> str:
    """Add appropriate prefix to questions if missing."""
    question = question.strip()
    
    # List of common question prefixes
    prefixes = ['Should', 'Can', 'Is', 'Are', 'Does', 'Do', 'Will', 'What', 'How', 'Why', 'When', 'Where', 'Which']
    
    # Check if question already starts with a prefix
    if any(question.startswith(prefix) for prefix in prefixes):
        return question
        
    # Determine appropriate prefix based on context
    lower_q = question.lower()
    if any(word in lower_q for word in ['allowed', 'permitted', 'acceptable']):
        prefix = 'Is it'
    elif any(word in lower_q for word in ['requirement', 'standard', 'rule']):
        prefix = 'What is'
    elif any(word in lower_q for word in ['process', 'procedure', 'method']):
        prefix = 'How should'
    else:
        prefix = 'Should'
    
    return f"{prefix} {question[0].lower()}{question[1:]}"

def split_into_qa_pairs(text: str) -> List[Dict]:
    """Split text into question-answer pairs with multiple choice support."""
    questions = []
    
    # Split into question blocks
    blocks = re.split(r'\n{2,}|\r\n{2,}|\f', text)
    
    for block in blocks:
        # Find question text
        question_match = re.match(r'^(?:\d+\.\s*)?(?:Q[:.]\s*)?([^?]+\??)', block, re.IGNORECASE)
        if not question_match:
            continue
            
        # Clean and format question text
        question_text = clean_text(question_match.group(1))
        if not question_text.endswith('?'):
            question_text += '?'
        question_text = add_question_prefix(question_text)
        
        # Find answer choices with proper ordering
        answer_pattern = r'(?:^|\n)\s*(?:[A-D][\)\.]\s*|\([A-D]\)\s*)(.*?)(?=(?:\n\s*[A-D][\)\.]\s*|\([A-D]\)\s*|$))'
        answer_matches = re.finditer(answer_pattern, block[question_match.end():], re.DOTALL)
        
        answers = []
        for match in answer_matches:
            answer_text = clean_text(match.group(1))
            if answer_text:
                # Ensure answer is a complete sentence
                if not answer_text.endswith(('.', '!', '?')):
                    answer_text += '.'
                if not answer_text[0].isupper():
                    answer_text = answer_text[0].upper() + answer_text[1:]
                answers.append(answer_text)
        
        # Find correct answer marker
        correct_marker = re.search(r'(?:correct(?:\s+answer)?[:.-]\s*|answer[:.-]\s*)([A-D])', block, re.IGNORECASE)
        
        if len(answers) >= 4 and correct_marker:
            try:
                correct_index = ord(correct_marker.group(1).upper()) - ord('A')
                if 0 <= correct_index < len(answers):
                    question_entry = {
                        'question_text': question_text,
                        'correct_answer': answers[correct_index],
                        'wrong_answers': [ans for i, ans in enumerate(answers) if i != correct_index][:3]
                    }
                    if validate_question(question_entry):
                        questions.append(question_entry)
            except (ValueError, IndexError):
                logger.warning(f"Invalid correct answer marker in question: {question_text}")
                
    return questions

def validate_question(question: Dict) -> bool:
    """Validate a question entry with enhanced checks."""
    try:
        # Check required fields
        if not all(key in question for key in ['question_text', 'correct_answer', 'wrong_answers']):
            logger.warning(f"Missing required fields in question: {question}")
            return False
        
        # Question structure validation
        question_text = question['question_text']
        if not (len(question_text.split()) >= 4 and  # Minimum 4 words
                re.match(r'^[A-Z]', question_text) and  # Starts with capital letter
                question_text.endswith('?') and  # Ends with question mark
                re.match(r'^(?:Should|Can|Is|Are|Does|Do|Will|What|How|Why|When|Where|Which)\s', question_text)):  # Has proper prefix
            logger.warning(f"Invalid question structure: {question_text}")
            return False
        
        # Answer validation
        all_answers = [question['correct_answer']] + question['wrong_answers']
        
        if len(all_answers) != 4:
            logger.warning(f"Question must have exactly 4 answers: {question_text}")
            return False
        
        # Validate each answer
        for answer in all_answers:
            # Check for complete sentence structure
            if not (len(answer.split()) >= 3 and  # Minimum 3 words
                    re.match(r'^[A-Z]', answer) and  # Starts with capital letter
                    re.search(r'[.!?]$', answer) and  # Ends with proper punctuation
                    any(char.isupper() for char in answer)):  # Contains at least one capital letter
                logger.warning(f"Invalid answer format: {answer}")
                return False
        
        # Check for answer distinctness
        if len(set(map(str.lower, all_answers))) != len(all_answers):
            logger.warning(f"Duplicate answers found in question: {question_text}")
            return False
        
        # Check for answer relevance
        question_keywords = set(re.findall(r'\b\w+\b', question_text.lower()))
        question_keywords -= {'should', 'can', 'is', 'are', 'does', 'do', 'will', 'what', 'how', 'why', 'when', 'where', 'which'}
        
        for answer in all_answers:
            answer_keywords = set(re.findall(r'\b\w+\b', answer.lower()))
            # Calculate semantic relevance
            common_words = question_keywords & answer_keywords
            if len(common_words) < 1:  # Must share at least one significant word
                logger.warning(f"Answer not contextually relevant: {answer}")
                return False
            
            # Check for answer completeness
            if len(answer_keywords) < 3:  # Must have at least 3 meaningful words
                logger.warning(f"Answer too short or incomplete: {answer}")
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
        
        # Validate and categorize questions
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
            category = categorize_question(pair['question_text'])
            wrong_answers = generate_wrong_answers(pair['correct_answer'], category)
            
            if wrong_answers and len(wrong_answers) >= 2:
                questions.append({
                    'question_text': pair['question_text'],
                    'correct_answer': pair['correct_answer'],
                    'wrong_answers': wrong_answers
                })
    
    return questions