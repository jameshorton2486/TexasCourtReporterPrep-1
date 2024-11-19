import magic
import os
import logging
import PyPDF2
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional, Set
import re
from pathlib import Path
import hashlib
import json
from datetime import datetime
import shutil

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
    MAX_FILE_SIZE = 20 * 1024 * 1024  # 20MB limit
    ALLOWED_MIME_TYPES = {'application/pdf', 'application/x-pdf', 'binary/octet-stream'}
    
    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.errors: List[ProcessingError] = []
        self._setup_directories()

    def _setup_directories(self):
        """Create necessary directories if they don't exist."""
        try:
            self.input_dir.mkdir(parents=True, exist_ok=True)
            self.output_dir.mkdir(parents=True, exist_ok=True)
            backup_dir = self.input_dir / 'backup'
            backup_dir.mkdir(parents=True, exist_ok=True)
            logger.info(f"Directories set up: {self.input_dir}, {self.output_dir}, {backup_dir}")
        except Exception as e:
            logger.error(f"Error setting up directories: {str(e)}")
            raise

    def extract_text(self, pdf_path: Path) -> Optional[str]:
        """Extract text from PDF with enhanced error handling."""
        try:
            with open(pdf_path, 'rb') as file:
                reader = PyPDF2.PdfReader(file)
                if not reader.pages:
                    self.errors.append(ProcessingError("EMPTY_PDF", 
                        "PDF file has no pages", pdf_path.name))
                    return None

                text = []
                total_pages = len(reader.pages)
                logger.info(f"Processing {total_pages} pages from {pdf_path}")

                for i, page in enumerate(reader.pages, 1):
                    try:
                        page_text = page.extract_text()
                        if not page_text:
                            logger.warning(f"Empty text content in page {i} of {pdf_path}")
                            continue

                        # Clean and normalize text
                        page_text = self._clean_text(page_text)
                        text.append(page_text)

                    except Exception as e:
                        self.errors.append(ProcessingError("PAGE_EXTRACTION_ERROR", 
                            f"Error extracting page {i}: {str(e)}", pdf_path.name))
                        continue

                if not text:
                    self.errors.append(ProcessingError("NO_TEXT_CONTENT", 
                        "No text content extracted from PDF", pdf_path.name))
                    return None

                return '\n'.join(text)

        except Exception as e:
            self.errors.append(ProcessingError("TEXT_EXTRACTION_ERROR", str(e), pdf_path.name))
            logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
            return None

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text with improved formatting."""
        # Remove non-printable characters except newlines
        text = ''.join(char for char in text if char.isprintable() or char == '\n')
        
        # Remove extra whitespace while preserving meaningful line breaks
        text = '\n'.join(line.strip() for line in text.split('\n'))
        
        # Normalize question marks and periods
        text = re.sub(r'\?+', '?', text)
        text = re.sub(r'\.+', '.', text)
        
        # Add space after punctuation if missing
        text = re.sub(r'([.?!])([A-Z])', r'\1 \2', text)
        
        # Remove multiple consecutive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def _extract_question_sections(self, text: str) -> List[Tuple[str, str]]:
        """Extract question-answer sections with improved pattern matching."""
        sections = []
        
        # Split text into potential question blocks
        blocks = re.split(r'\n{2,}', text)
        
        for block in blocks:
            # Various question patterns
            question_patterns = [
                # Standard question with question mark
                r'^([^?]+\?)\s*(.+)$',
                # Numbered question
                r'^\d+[\.)]\s*([^?]+\?)\s*(.+)$',
                # Question with "Question:" prefix
                r'^(?:Question:\s*)?([^?]+\?)\s*(.+)$',
                # Question-answer separated by newline
                r'^([^?]+\?)\n(.+)$'
            ]
            
            for pattern in question_patterns:
                match = re.match(pattern, block, re.DOTALL | re.MULTILINE)
                if match:
                    question = match.group(1).strip()
                    answer_section = match.group(2).strip()
                    if self._validate_question_text(question):
                        sections.append((question, answer_section))
                        break
        
        return sections

    def _validate_question_text(self, text: str) -> bool:
        """Validate question text format with improved checks."""
        if not text or not text.strip():
            return False
        
        # Must end with question mark
        if not text.endswith('?'):
            return False
        
        # Minimum length check (at least 5 words)
        if len(text.split()) < 5:
            return False
        
        # Check for invalid patterns
        invalid_patterns = [
            r'^[A-D][\.)]\s',  # Starts with answer letter
            r'^\d+[\.)]\s*$',  # Just a number
            r'^Answer:',      # Starts with "Answer:"
            r'^Correct:',     # Starts with "Correct:"
            r'^[^a-zA-Z]*$'   # Contains no letters
        ]
        
        if any(re.match(pattern, text) for pattern in invalid_patterns):
            return False
        
        # Check for reasonable question structure
        has_verb = re.search(r'\b(is|are|was|were|do|does|did|will|can|could|should|would|have|has|had)\b', text, re.IGNORECASE)
        if not has_verb:
            return False
        
        return True

    def parse_answers(self, answer_section: str) -> Tuple[Optional[str], List[str]]:
        """Parse answers with enhanced format detection."""
        if not answer_section:
            return None, []

        # Clean up answer section
        answer_section = self._clean_text(answer_section)
        
        # Common answer formats
        answer_formats = [
            # Standard format (A. Answer)
            (r'(?:^|\n)\s*([A-D])\.?\s+([^\n]+)(?=\n[A-D]\.|\Z)', False),
            # Parentheses format (A) Answer)
            (r'(?:^|\n)\s*([A-D])\)\s+([^\n]+)(?=\n[A-D]\)|\Z)', False),
            # Dash format (A - Answer)
            (r'(?:^|\n)\s*([A-D])\s*-\s*([^\n]+)(?=\n[A-D]\s*-|\Z)', False),
            # Simple format (A Answer)
            (r'(?:^|\n)\s*([A-D])\s+([^\n]+)(?=\n[A-D]\s|\Z)', False),
            # List format (1. Answer)
            (r'(?:^|\n)\s*(\d+)\.?\s+([^\n]+)(?=\n\d+\.?|\Z)', True),
            # Bullet format (• Answer)
            (r'(?:^|\n)\s*[•\-*]\s+([^\n]+)', True)
        ]

        # Try each format
        for pattern, is_numbered in answer_formats:
            matches = list(re.finditer(pattern, answer_section, re.MULTILINE))
            
            if len(matches) >= 4:
                answers = []
                answer_map = {}
                
                for i, match in enumerate(matches[:4]):
                    if is_numbered:
                        # For numbered or bulleted lists, use position for letter
                        letter = chr(ord('A') + i)
                        answer_text = match.group(1) if len(match.groups()) == 1 else match.group(2)
                    else:
                        # For lettered formats
                        letter = match.group(1)
                        answer_text = match.group(2)
                    
                    answer_text = answer_text.strip()
                    if self._validate_answer_text(answer_text):
                        answer_map[letter] = answer_text
                        answers.append(answer_text)

                if len(answers) == 4:
                    # Look for correct answer indicator
                    correct_letter = self._find_correct_answer(answer_section, answer_map.keys())
                    if correct_letter and correct_letter in answer_map:
                        correct_answer = answer_map[correct_letter]
                        wrong_answers = [ans for letter, ans in answer_map.items() 
                                      if letter != correct_letter]
                        return correct_answer, wrong_answers

        return None, []

    def _find_correct_answer(self, text: str, valid_letters: Set[str]) -> Optional[str]:
        """Find the correct answer letter with improved pattern matching."""
        correct_markers = [
            r'(?i)correct(?:\ answer)?[\s:]+([A-D])',
            r'(?i)answer[\s:]+([A-D])',
            r'(?i)key[\s:]+([A-D])',
            r'(?i)\(([A-D])\)\s+is\s+correct',
            r'(?i)([A-D])\s+is\s+correct',
            r'(?i)the\s+correct\s+(?:answer|option)\s+is\s+([A-D])'
        ]

        for marker in correct_markers:
            match = re.search(marker, text)
            if match:
                letter = match.group(1).upper()
                if letter in valid_letters:
                    return letter

        # If no explicit marker, look for other indicators
        text_lower = text.lower()
        for letter in valid_letters:
            indicators = [
                f"option {letter}",
                f"answer {letter}",
                f"{letter} is the best",
                f"{letter} correctly"
            ]
            if any(indicator in text_lower for indicator in indicators):
                return letter

        return None

    def _validate_answer_text(self, answer: str) -> bool:
        """Validate individual answer text with improved checks."""
        if not answer or len(answer.strip()) < 2:
            return False

        # Minimum word count (typically answers should be at least 2 words)
        if len(answer.split()) < 2:
            return False

        # Check for invalid patterns
        invalid_patterns = [
            r'^[A-D][\.)]\s',  # Starts with letter and punctuation
            r'^\d+[\.)]\s',    # Starts with number and punctuation
            r'^Answer:\s',     # Starts with "Answer:"
            r'^Correct:\s',    # Starts with "Correct:"
            r'^[^a-zA-Z]*$',   # Contains no letters
            r'^None\s+of\s+the\s+above$',  # Generic answers
            r'^All\s+of\s+the\s+above$'
        ]

        if any(re.match(pattern, answer, re.IGNORECASE) for pattern in invalid_patterns):
            return False

        # Check for reasonable answer length and content
        words = answer.split()
        if len(max(words, key=len, default='')) > 30:  # Very long words are suspicious
            return False

        # Check for complete sentence structure
        has_verb = re.search(r'\b(is|are|was|were|do|does|did|will|can|could|should|would|have|has|had)\b', answer, re.IGNORECASE)
        has_noun = re.search(r'\b[A-Z][a-z]+\b|\b[a-z]+(?:ing|tion|ment|ence)\b', answer)
        
        return bool(has_verb and has_noun)

    def process_pdf(self, pdf_name: str) -> Tuple[List[Question], List[ProcessingError]]:
        """Process a single PDF file with enhanced error handling."""
        self.errors = []
        questions = []
        pdf_path = self.input_dir / pdf_name

        try:
            # Validate and backup file
            if not self.validate_file(pdf_path):
                return [], self.errors

            if not self.backup_file(pdf_path):
                logger.warning(f"Failed to create backup for {pdf_path}")

            # Extract text
            text = self.extract_text(pdf_path)
            if not text:
                return [], self.errors

            # Extract question sections
            sections = self._extract_question_sections(text)
            
            for question_text, answer_section in sections:
                try:
                    # Parse answers
                    correct_answer, wrong_answers = self.parse_answers(answer_section)
                    if not correct_answer or not wrong_answers:
                        continue

                    # Create and validate question
                    question = Question(
                        question_text=question_text,
                        correct_answer=correct_answer,
                        wrong_answers=wrong_answers,
                        category=self._detect_category(question_text),
                        source_file=pdf_name
                    )

                    if self.validate_question(question):
                        questions.append(question)
                        logger.info(f"Successfully parsed question: {question_text[:50]}...")

                except Exception as e:
                    self.errors.append(ProcessingError("QUESTION_PARSING_ERROR", 
                        f"Error parsing question: {str(e)}", pdf_name))
                    continue

            return questions, self.errors

        except Exception as e:
            self.errors.append(ProcessingError("PROCESSING_ERROR", str(e), pdf_name))
            logger.error(f"Error processing PDF {pdf_path}: {str(e)}")
            return [], self.errors

    def validate_file(self, file_path: Path) -> bool:
        """Validate PDF file with enhanced checks."""
        try:
            if not file_path.exists():
                self.errors.append(ProcessingError("FILE_NOT_FOUND", 
                    f"File not found: {file_path}", file_path.name))
                return False

            # Size checks
            file_size = file_path.stat().st_size
            if file_size == 0:
                self.errors.append(ProcessingError("EMPTY_FILE", 
                    "File is empty", file_path.name))
                return False

            if file_size > self.MAX_FILE_SIZE:
                self.errors.append(ProcessingError("FILE_TOO_LARGE", 
                    f"File exceeds size limit of {self.MAX_FILE_SIZE/1024/1024}MB", file_path.name))
                return False

            # MIME type validation
            try:
                mime_type = magic.from_file(str(file_path), mime=True)
                if mime_type not in self.ALLOWED_MIME_TYPES:
                    self.errors.append(ProcessingError("INVALID_FILE_TYPE", 
                        f"Invalid file type: {mime_type}", file_path.name))
                    return False
            except Exception as e:
                self.errors.append(ProcessingError("MIME_TYPE_ERROR", 
                    f"Error checking file type: {str(e)}", file_path.name))
                return False

            # Verify PDF structure
            try:
                with open(file_path, 'rb') as f:
                    reader = PyPDF2.PdfReader(f)
                    if not reader.pages:
                        self.errors.append(ProcessingError("INVALID_PDF_STRUCTURE", 
                            "PDF file has no pages", file_path.name))
                        return False
            except Exception as e:
                self.errors.append(ProcessingError("INVALID_PDF_STRUCTURE", 
                    f"Invalid PDF structure: {str(e)}", file_path.name))
                return False

            return True

        except Exception as e:
            self.errors.append(ProcessingError("VALIDATION_ERROR", str(e), file_path.name))
            logger.error(f"Error validating file {file_path}: {str(e)}")
            return False

    def backup_file(self, file_path: Path) -> bool:
        """Create a backup of the file before processing."""
        try:
            backup_dir = self.input_dir / 'backup'
            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            backup_path = backup_dir / f"{file_path.stem}_{timestamp}{file_path.suffix}"
            
            shutil.copy2(file_path, backup_path)
            logger.info(f"Created backup: {backup_path}")
            return True
        except Exception as e:
            logger.error(f"Error creating backup for {file_path}: {str(e)}")
            return False

    def _detect_category(self, question_text: str) -> str:
        """Detect question category with improved keyword matching."""
        categories = {
            'Legal & Judicial Terminology': [
                r'\b(?:court|legal|judge|judicial|jurisdiction|motion|pleading|statute|law|testimony|brief|counsel|verdict|evidence|ruling)\b'
            ],
            'Professional Standards & Ethics': [
                r'\b(?:ethic|confidential|professional|conduct|responsibility|duty|obligation|standard|integrity|privacy)\b'
            ],
            'Grammar & Vocabulary': [
                r'\b(?:grammar|punctuation|spell|vocabulary|word|sentence|phrase|meaning|syntax|clause|verb|noun)\b'
            ],
            'Transcription Standards': [
                r'\b(?:format|transcript|record|report|margin|paragraph|style|citation|indent|spacing|header|footer)\b'
            ]
        }

        # Count matches for each category
        category_scores = {}
        for category, patterns in categories.items():
            score = sum(len(re.findall(pattern, question_text, re.IGNORECASE)) for pattern in patterns)
            category_scores[category] = score

        # Return category with highest score, or default if no matches
        max_score = max(category_scores.values())
        if max_score > 0:
            for category, score in category_scores.items():
                if score == max_score:
                    return category

        return 'Legal & Judicial Terminology'

    def validate_question(self, question: Question) -> bool:
        """Validate question with comprehensive checks."""
        try:
            # Validate question text
            if not self._validate_question_text(question.question_text):
                return False

            # Validate answers
            if not question.correct_answer or not question.wrong_answers:
                logger.warning("Missing answers")
                return False

            if len(question.wrong_answers) != 3:
                logger.warning("Wrong number of wrong answers")
                return False

            # Check for duplicate answers
            all_answers = [question.correct_answer] + question.wrong_answers
            if len(set(map(str.lower, all_answers))) != len(all_answers):
                logger.warning("Duplicate answers found")
                return False

            # Validate each answer
            if not all(self._validate_answer_text(answer) for answer in all_answers):
                logger.warning("Invalid answer format detected")
                return False

            return True

        except Exception as e:
            logger.error(f"Error validating question: {str(e)}")
            return False

    def save_questions(self, questions: List[Question], output_name: str) -> Optional[str]:
        """Save processed questions to JSON file."""
        try:
            if not questions:
                return None
                
            output_path = self.output_dir / f"{output_name}.json"
            questions_data = [q.to_dict() for q in questions]
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(questions_data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Saved {len(questions)} questions to {output_path}")
            return str(output_path)
            
        except Exception as e:
            logger.error(f"Error saving questions: {str(e)}")
            return None

def process_pdf_file(pdf_path: str) -> Tuple[List[Dict], List[str]]:
    """Process a single PDF file and return extracted questions and errors."""
    processor = QuestionProcessor(os.path.dirname(pdf_path), 'processed_questions')
    questions, errors = processor.process_pdf(os.path.basename(pdf_path))
    return [q.to_dict() for q in questions], [e.message for e in errors]
