import os
import logging
import PyPDF2
import random
from typing import Dict, List, Tuple, Optional
import re

logger = logging.getLogger(__name__)

def extract_text_from_pdf(pdf_path: str) -> Optional[str]:
    """Extract text content from a PDF file with enhanced error handling."""
    try:
        with open(pdf_path, 'rb') as file:
            reader = PyPDF2.PdfReader(file)
            if not reader.pages:
                logger.error(f"PDF file {pdf_path} has no pages")
                return None
                
            text = ''
            total_pages = len(reader.pages)
            logger.info(f"Processing {total_pages} pages from {pdf_path}")
            
            for i, page in enumerate(reader.pages, 1):
                try:
                    page_text = page.extract_text()
                    if not page_text:
                        logger.warning(f"Empty text content in page {i} of {pdf_path}")
                        continue
                    text += page_text + '\n'
                    logger.debug(f"Successfully extracted text from page {i}/{total_pages}")
                except Exception as e:
                    logger.error(f"Error extracting text from page {i} in {pdf_path}: {str(e)}")
                    continue
                    
            if not text.strip():
                logger.error(f"No valid text content extracted from {pdf_path}")
                return None
                
            logger.info(f"Successfully extracted text from {pdf_path}")
            return text.strip()
            
    except Exception as e:
        logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
        return None

def clean_text(text: str) -> Optional[str]:
    """Clean and normalize text content."""
    if not text or not text.strip():
        return None
        
    try:
        # Basic cleaning
        text = text.strip()
        text = re.sub(r'\s+', ' ', text)
        
        # Remove common artifacts
        text = re.sub(r'Question\s+\d+[\.:]\s*', '', text)
        text = re.sub(r'^\d+[\.:]\s*', '', text)
        
        # Ensure proper question format if it looks like a question
        if any(word in text.lower() for word in ['what', 'who', 'when', 'where', 'why', 'how', 'which', 'is', 'are', 'can', 'should']):
            if not text.endswith('?'):
                text = text.rstrip('.') + '?'
        
        # Ensure capitalization
        if text and text[0].islower():
            text = text[0].upper() + text[1:]
            
        return text
        
    except Exception as e:
        logger.error(f"Error cleaning text: {str(e)}")
        return None

def split_into_qa_pairs(text: str) -> List[Dict]:
    """Split text into question-answer pairs with improved pattern matching."""
    questions = []
    
    try:
        # Split text into potential question blocks
        blocks = re.split(r'\n{2,}|\r\n{2,}', text)
        
        for block in blocks:
            try:
                # Look for question patterns
                question_match = re.search(r'^[^?]+\?', block, re.MULTILINE)
                if not question_match:
                    continue
                    
                question_text = clean_text(question_match.group())
                if not question_text:
                    continue
                
                # Extract answer section
                answer_section = block[question_match.end():].strip()
                
                # Try different answer patterns
                answers = []
                
                # Pattern 1: Standard A/B/C/D format
                pattern1 = r'([A-D])[\s.:-]+([^A-D\n]+)(?=(?:[A-D][\s.:-]+|$))'
                matches = list(re.finditer(pattern1, answer_section, re.DOTALL))
                
                # Pattern 2: Numbered format
                pattern2 = r'(?:^|\n)\s*(\d+)[\s.:-]+([^\n]+)'
                
                if len(matches) == 4:  # Standard A/B/C/D format
                    for match in matches:
                        answer_text = clean_text(match.group(2))
                        if answer_text:
                            answers.append((match.group(1), answer_text))
                else:
                    # Try numbered format
                    matches = list(re.finditer(pattern2, answer_section, re.MULTILINE))
                    if len(matches) >= 4:
                        for i, match in enumerate(matches[:4]):
                            answer_text = clean_text(match.group(2))
                            if answer_text:
                                answers.append((chr(65 + i), answer_text))  # Convert 1,2,3,4 to A,B,C,D
                
                if len(answers) == 4:
                    # Look for correct answer marker
                    correct_marker = re.search(
                        r'(?:correct[\s.:]+|answer[\s.:]+|key[\s.:]+)([A-D1-4])',
                        answer_section,
                        re.IGNORECASE
                    )
                    
                    if correct_marker:
                        correct_letter = correct_marker.group(1)
                        if correct_letter.isdigit():
                            correct_letter = chr(64 + int(correct_letter))  # Convert 1,2,3,4 to A,B,C,D
                        
                        correct_index = ord(correct_letter) - ord('A')
                        if 0 <= correct_index < len(answers):
                            question_entry = {
                                'question_text': question_text,
                                'correct_answer': answers[correct_index][1],
                                'wrong_answers': [ans[1] for i, ans in enumerate(answers) if i != correct_index],
                                'category': 'Legal & Judicial Terminology'  # Default category
                            }
                            questions.append(question_entry)
                            logger.info(f"Successfully parsed question: {question_text[:50]}...")
                
            except Exception as e:
                logger.error(f"Error processing question block: {str(e)}")
                continue
                
        return questions
        
    except Exception as e:
        logger.error(f"Error splitting text into QA pairs: {str(e)}")
        return []

def validate_question(question: Dict) -> bool:
    """Validate a question entry with basic validation."""
    try:
        # Check required fields
        if not all(key in question for key in ['question_text', 'correct_answer', 'wrong_answers']):
            return False
            
        # Basic validation
        if not (isinstance(question['question_text'], str) and 
                isinstance(question['correct_answer'], str) and 
                isinstance(question['wrong_answers'], list)):
            return False
            
        # Content validation
        if not question['question_text'].strip() or not question['correct_answer'].strip():
            return False
            
        if len(question['wrong_answers']) != 3:
            return False
            
        # Check for duplicate answers
        all_answers = [question['correct_answer']] + question['wrong_answers']
        if len(set(map(str.lower, all_answers))) != len(all_answers):
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
        logger.info(f"Starting to process PDF file: {pdf_path}")
        
        # Basic file validation
        if not os.path.exists(pdf_path):
            error_msg = f"PDF file not found: {pdf_path}"
            logger.error(error_msg)
            return [], [error_msg]
            
        # Extract text content
        text = extract_text_from_pdf(pdf_path)
        if not text:
            error_msg = f"Failed to extract text from {pdf_path}"
            logger.error(error_msg)
            return [], [error_msg]
            
        # Process extracted text
        extracted_questions = split_into_qa_pairs(text)
        processed_count = 0
        
        # Validate and process questions
        for q in extracted_questions:
            if validate_question(q):
                questions.append(q)
                processed_count += 1
            else:
                errors.append(f"Invalid question format: {q.get('question_text', 'No question text')[:100]}...")
        
        logger.info(f"Successfully processed {processed_count} valid questions from {pdf_path}")
        
        if not questions:
            logger.warning(f"No valid questions extracted from {pdf_path}")
        
        return questions, errors
        
    except Exception as e:
        error_msg = f"Error processing PDF {pdf_path}: {str(e)}"
        logger.error(error_msg)
        return [], [error_msg]