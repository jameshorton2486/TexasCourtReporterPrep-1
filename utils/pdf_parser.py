from __future__ import annotations
import os
import logging
import PyPDF2
import magic
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
import re
from pathlib import Path
import hashlib
import json
from datetime import datetime

logger = logging.getLogger(__name__)

@dataclass
class ProcessingError:
    error_type: str
    message: str
    file_name: str
    timestamp: str = datetime.utcnow().isoformat()

@dataclass
class Question:
    question_text: str
    correct_answer: str
    wrong_answers: List[str]
    category: str
    source_file: str
    content_hash: str = ""
    
    def __post_init__(self):
        # Generate content hash for deduplication
        content = f"{self.question_text}|{self.correct_answer}|{'|'.join(self.wrong_answers)}"
        self.content_hash = hashlib.sha256(content.encode()).hexdigest()

    def to_dict(self) -> Dict:
        return {
            'question_text': self.question_text,
            'correct_answer': self.correct_answer,
            'wrong_answers': self.wrong_answers,
            'category': self.category,
            'source_file': self.source_file,
            'content_hash': self.content_hash
        }

class QuestionProcessor:
    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB limit
    ALLOWED_MIME_TYPES = {'application/pdf'}
    
    def __init__(self, input_dir: str, output_dir: str):
        """Initialize the question processor with input and output directories."""
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.errors: List[ProcessingError] = []
        self._setup_directories()

    def _setup_directories(self):
        """Create necessary directories if they don't exist."""
        try:
            self.input_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directories set up: {self.input_dir}, {self.output_dir}")
        except Exception as e:
            logger.error(f"Error setting up directories: {str(e)}")
            raise

    def validate_file(self, file_path: Path) -> bool:
        """Validate file type, size, and content."""
        try:
            if not file_path.exists():
                self.errors.append(ProcessingError("FILE_NOT_FOUND", f"File not found: {file_path}", file_path.name))
                return False

            # Check file size
            file_size = file_path.stat().st_size
            if file_size > self.MAX_FILE_SIZE:
                self.errors.append(ProcessingError("FILE_TOO_LARGE", 
                    f"File exceeds size limit of {self.MAX_FILE_SIZE/1024/1024}MB", file_path.name))
                return False

            # Check file type using python-magic
            mime_type = magic.from_file(str(file_path), mime=True)
            if mime_type not in self.ALLOWED_MIME_TYPES:
                self.errors.append(ProcessingError("INVALID_FILE_TYPE", 
                    f"Invalid file type: {mime_type}", file_path.name))
                return False

            return True

        except Exception as e:
            self.errors.append(ProcessingError("VALIDATION_ERROR", str(e), file_path.name))
            logger.error(f"Error validating file {file_path}: {str(e)}")
            return False

    def extract_text(self, pdf_path: Path) -> Optional[str]:
        """Extract text from PDF with enhanced error handling."""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                if not reader.pages:
                    self.errors.append(ProcessingError("EMPTY_PDF", 
                        "PDF file has no pages", pdf_path.name))
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
                    except Exception as e:
                        self.errors.append(ProcessingError("PAGE_EXTRACTION_ERROR", 
                            f"Error extracting page {i}: {str(e)}", pdf_path.name))
                        continue

                return text.strip() if text.strip() else None

        except Exception as e:
            self.errors.append(ProcessingError("TEXT_EXTRACTION_ERROR", str(e), pdf_path.name))
            logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
            return None

    def parse_answers(self, answer_section: str) -> Tuple[Optional[str], List[str]]:
        """Parse answers with flexible format detection."""
        answer_patterns = [
            # Standard A/B/C/D format
            r'(?:^|\n)\s*([A-D])[\s.:-]+([^\n]+)(?=(?:\n[A-D][\s.:-]+|\n*$))',
            # Numbered format
            r'(?:^|\n)\s*(\d+)[\s.:-]+([^\n]+)(?=(?:\n\d+[\s.:-]+|\n*$))',
            # Bullet point format
            r'(?:^|\n)\s*[•\-*][\s.:-]+([^\n]+)'
        ]

        correct_answer = None
        all_answers = []

        for pattern in answer_patterns:
            matches = list(re.finditer(pattern, answer_section, re.MULTILINE))
            if len(matches) >= 4:  # We need at least 4 answers
                answers = []
                for match in matches[:4]:
                    answer_text = match.group(2) if len(match.groups()) > 1 else match.group(1)
                    answer_text = answer_text.strip()
                    if answer_text:
                        answers.append(answer_text)

                if len(answers) == 4:
                    # Look for correct answer marker
                    correct_markers = [
                        r'(?:correct[\s.:]+|answer[\s.:]+|key[\s.:]+)([A-D1-4])',
                        r'(?:^|\n)\s*correct\s*(?:answer)?[\s.:]+([^\n]+)',
                    ]

                    for marker in correct_markers:
                        correct_match = re.search(marker, answer_section, re.IGNORECASE)
                        if correct_match:
                            marker_value = correct_match.group(1)
                            if marker_value in 'ABCD1234':
                                index = (ord(marker_value) - ord('A')) if marker_value in 'ABCD' else int(marker_value) - 1
                                if 0 <= index < len(answers):
                                    correct_answer = answers[index]
                                    wrong_answers = [ans for i, ans in enumerate(answers) if i != index]
                                    return correct_answer, wrong_answers

        return None, []

    def validate_question(self, question: Question) -> bool:
        """Validate a question for quality and completeness."""
        try:
            # Basic validation
            if not question.question_text.strip():
                logger.warning("Empty question text")
                return False

            # Question format validation
            if not question.question_text.endswith('?'):
                logger.warning(f"Question doesn't end with '?': {question.question_text[:100]}")
                return False

            if len(question.question_text.split()) < 5:
                logger.warning(f"Question too short: {question.question_text}")
                return False

            # Answer validation
            if not question.correct_answer or not question.wrong_answers:
                logger.warning("Missing answers")
                return False

            if len(question.wrong_answers) != 3:
                logger.warning("Wrong number of wrong answers")
                return False

            # Check for duplicate answers
            all_answers = [question.correct_answer] + question.wrong_answers
            unique_answers = {ans.lower() for ans in all_answers}
            if len(unique_answers) != len(all_answers):
                logger.warning("Duplicate answers found")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating question: {str(e)}")
            return False

    def process_pdf(self, pdf_name: str) -> Tuple[List[Question], List[ProcessingError]]:
        """Process a single PDF file and extract questions."""
        self.errors = []  # Reset errors for new file
        questions: List[Question] = []
        pdf_path = self.input_dir / pdf_name

        try:
            # Validate file
            if not self.validate_file(pdf_path):
                return [], self.errors

            # Extract text
            text = self.extract_text(pdf_path)
            if not text:
                return [], self.errors

            # Split into question blocks
            blocks = re.split(r'\n{2,}|\r\n{2,}', text)
            
            for block in blocks:
                try:
                    # Look for question pattern
                    question_match = re.search(r'^[^?]+\?', block, re.MULTILINE)
                    if not question_match:
                        continue

                    question_text = question_match.group().strip()
                    answer_section = block[question_match.end():].strip()

                    # Parse answers
                    correct_answer, wrong_answers = self.parse_answers(answer_section)
                    if not correct_answer or not wrong_answers:
                        continue

                    # Create question object
                    question = Question(
                        question_text=question_text,
                        correct_answer=correct_answer,
                        wrong_answers=wrong_answers,
                        category='Legal & Judicial Terminology',  # Default category
                        source_file=pdf_name
                    )

                    # Validate question
                    if self.validate_question(question):
                        questions.append(question)
                        logger.info(f"Successfully parsed question: {question_text[:50]}...")

                except Exception as e:
                    self.errors.append(ProcessingError("QUESTION_PARSING_ERROR", 
                        f"Error parsing question block: {str(e)}", pdf_name))
                    continue

            return questions, self.errors

        except Exception as e:
            self.errors.append(ProcessingError("PROCESSING_ERROR", str(e), pdf_name))
            logger.error(f"Error processing PDF {pdf_name}: {str(e)}")
            return [], self.errors

    def save_questions(self, questions: List[Question], output_name: str) -> Optional[str]:
        """Save processed questions to output directory."""
        try:
            output_path = self.output_dir / f"{output_name}.json"
            questions_data = [q.to_dict() for q in questions]
            
            with open(output_path, 'w') as f:
                json.dump(questions_data, f, indent=2)
            
            logger.info(f"Saved {len(questions)} questions to {output_path}")
            return str(output_path)
            
        except Exception as e:
            self.errors.append(ProcessingError("SAVE_ERROR", str(e), output_name))
            logger.error(f"Error saving questions: {str(e)}")
            return None

def process_pdf_file(pdf_path: str) -> Tuple[List[Dict], List[str]]:
    """Legacy wrapper for backward compatibility."""
    processor = QuestionProcessor(os.path.dirname(pdf_path), 'processed_questions')
    questions, errors = processor.process_pdf(os.path.basename(pdf_path))
    return [q.to_dict() for q in questions], [e.message for e in errors]
