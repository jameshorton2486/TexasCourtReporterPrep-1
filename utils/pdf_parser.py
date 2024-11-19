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
    
    CATEGORIES = {
        'Legal & Judicial Terminology': ['legal', 'judicial', 'court', 'law'],
        'Professional Standards & Ethics': ['ethics', 'standards', 'professional', 'conduct'],
        'Grammar & Vocabulary': ['grammar', 'vocabulary', 'language', 'writing'],
        'Transcription Standards': ['transcription', 'format', 'reporting', 'record']
    }
    
    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = Path(input_dir)
        self.output_dir = Path(output_dir)
        self.errors: List[ProcessingError] = []
        self.current_category = None
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
                try:
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
                            if page_text:  # Only add non-empty cleaned text
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

                except PyPDF2.PdfReadError as e:
                    self.errors.append(ProcessingError("PDF_READ_ERROR", 
                        f"Error reading PDF: {str(e)}", pdf_path.name))
                    return None

        except Exception as e:
            self.errors.append(ProcessingError("TEXT_EXTRACTION_ERROR", str(e), pdf_path.name))
            logger.error(f"Error extracting text from PDF {pdf_path}: {str(e)}")
            return None

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text with improved formatting."""
        if not text:
            return ""

        # Remove non-printable characters except newlines and tabs
        text = ''.join(char for char in text if char.isprintable() or char in '\n\t')
        
        # Replace tabs with spaces
        text = text.replace('\t', ' ')
        
        # Normalize whitespace
        lines = []
        for line in text.split('\n'):
            # Remove extra whitespace while preserving meaningful line breaks
            line = ' '.join(part for part in line.split() if part)
            if line:
                lines.append(line)
        
        # Join lines with proper spacing
        text = '\n'.join(lines)
        
        # Normalize question marks and periods
        text = re.sub(r'\?+', '?', text)
        text = re.sub(r'\.+', '.', text)
        
        # Add space after punctuation if missing
        text = re.sub(r'([.?!])([A-Z])', r'\1 \2', text)
        
        # Remove multiple consecutive newlines
        text = re.sub(r'\n{3,}', '\n\n', text)
        
        return text.strip()

    def _detect_category(self, text: str) -> str:
        """Detect category from text content."""
        if self.current_category:
            return self.current_category
            
        text_lower = text.lower()
        scores = {cat: 0 for cat in self.CATEGORIES}
        
        for category, keywords in self.CATEGORIES.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    scores[category] += 1
                    
        if any(scores.values()):
            return max(scores.items(), key=lambda x: x[1])[0]
            
        return "Legal & Judicial Terminology"  # Default category

    def _extract_question_sections(self, text: str) -> List[Tuple[str, str]]:
        """Extract question-answer sections with improved pattern matching."""
        sections = []
        
        # Split text into potential sections
        blocks = re.split(r'\n{2,}', text)
        
        for block in blocks:
            block = block.strip()
            
            # Check for category headers
            if block.endswith('Questions:') or block.endswith('QUESTIONS:'):
                self.current_category = block.replace('Questions:', '').replace('QUESTIONS:', '').strip()
                continue
            
            # Enhanced question patterns
            question_patterns = [
                # Standard numbered format with optional Q: prefix
                r'^\d+\.?\s*(?:Q:)?\s*([^?]+\?)\s*[-:]?\s*(.+)$',
                # Bulleted format
                r'[•\-*]\s*([^?]+\?)\s*[-:]?\s*(.+)$',
                # Question with lettered/numbered answers
                r'^(?:Q:)?\s*([^?]+\?)\s*(?:\n\s*[A-D][\.)]\s*.+){2,}$',
                # Basic Q&A format
                r'^([^?]+\?)\s*[-:]?\s*(.+)$',
                # Multi-line format with answer on next line
                r'^(?:Q:)?\s*([^?]+\?)\s*\n\s*(?:A:)?\s*(.+)$'
            ]
            
            for pattern in question_patterns:
                match = re.match(pattern, block, re.DOTALL | re.MULTILINE)
                if match:
                    question = match.group(1).strip()
                    answer = match.group(2).strip()
                    
                    # Clean up the question and answer
                    question = re.sub(r'\s+', ' ', question)
                    answer = re.sub(r'\s+', ' ', answer)
                    
                    # Handle lettered/numbered answers
                    if re.search(r'[A-D][\.)]\s+', answer):
                        answers = re.findall(r'[A-D][\.)]\s+([^\n]+)(?:\n|$)', answer)
                        if answers:
                            answer = answers[0]  # Take first answer as correct
                
                # Validate question format
                if self._validate_question_text(question):
                    sections.append((question, answer))
                    logger.debug(f"Extracted question: {question[:50]}...")
                break
        
        # Try to extract multiple questions from a block
        if not match and len(block.split('\n')) > 2:
            current_question = None
            current_answer = []
            
            for line in block.split('\n'):
                line = line.strip()
                if not line:
                    if current_question and current_answer:
                        joined_answer = ' '.join(current_answer)
                        if self._validate_question_text(current_question):
                            sections.append((current_question, joined_answer))
                        current_question = None
                        current_answer = []
                    continue
                
                # Check for new question
                if re.match(r'^\d+\.?\s*|^Q:|^[•\-*]\s*', line) and '?' in line:
                    if current_question and current_answer:
                        joined_answer = ' '.join(current_answer)
                        if self._validate_question_text(current_question):
                            sections.append((current_question, joined_answer))
                    
                    question_match = re.match(r'^(?:\d+\.?\s*|Q:\s*|[•\-*]\s*)?([^?]+\?)(?:\s*[-:]?\s*(.+))?$', line)
                    if question_match:
                        current_question = question_match.group(1).strip()
                        current_answer = []
                        if question_match.group(2):
                            current_answer.append(question_match.group(2).strip())
                elif current_question:
                    # Add line to current answer if it's not a new question
                    if not re.match(r'^\d+\.?\s*|^Q:|^[•\-*]\s*', line):
                        current_answer.append(line)
            
            # Add last question if exists
            if current_question and current_answer:
                joined_answer = ' '.join(current_answer)
                if self._validate_question_text(current_question):
                    sections.append((current_question, joined_answer))
    
    logger.info(f"Extracted {len(sections)} questions")
    return sections

    def _validate_question_text(self, text: str) -> bool:
        """Validate question text with improved checks."""
        if not text or not isinstance(text, str):
            return False
            
        # Basic format checks
        if not text.strip().endswith('?'):
            return False
            
        # Length checks
        words = text.split()
        if len(words) < 5 or len(words) > 50:
            return False
            
        # Check for question words
        question_words = r'\b(what|who|where|when|why|how|which|whose|whom)\b'
        if not re.search(question_words, text.lower()):
            return False
            
        # Check for proper sentence structure
        has_verb = re.search(r'\b(is|are|was|were|do|does|did|will|can|could|should|would|have|has|had)\b', text, re.IGNORECASE)
        if not has_verb:
            return False
            
        return True

    def _generate_wrong_answers(self, correct_answer: str) -> List[str]:
        """Generate plausible wrong answers based on the correct answer."""
        # This is a placeholder - in production, you'd want to use
        # more sophisticated methods or AI to generate wrong answers
        return [
            f"Incorrect: {correct_answer}",
            f"Not quite: {correct_answer}",
            f"Wrong: {correct_answer}"
        ]

    def process_pdf(self, pdf_name: str) -> Tuple[List[Question], List[ProcessingError]]:
        """Process a single PDF file with enhanced error handling."""
        self.errors = []
        questions = []
        pdf_path = self.input_dir / pdf_name
        self.current_category = None  # Reset category for new file

        try:
            # Validate and backup file
            if not self.validate_file(pdf_path):
                return [], self.errors

            # Extract text
            text = self.extract_text(pdf_path)
            if not text:
                return [], self.errors

            # Extract and process sections
            sections = self._extract_question_sections(text)
            
            for question_text, answer_text in sections:
                try:
                    # Create question object
                    category = self._detect_category(question_text)
                    wrong_answers = self._generate_wrong_answers(answer_text)
                    
                    question = Question(
                        question_text=question_text,
                        correct_answer=answer_text,
                        wrong_answers=wrong_answers,
                        category=category,
                        source_file=pdf_name
                    )
                    
                    questions.append(question)
                    logger.info(f"Successfully extracted question: {question_text[:50]}...")
                    
                except Exception as e:
                    self.errors.append(ProcessingError(
                        "QUESTION_CREATION_ERROR",
                        f"Error creating question: {str(e)}",
                        pdf_name
                    ))
                    continue

            if not questions:
                logger.warning(f"No valid questions extracted from {pdf_name}")
            else:
                logger.info(f"Successfully extracted {len(questions)} questions from {pdf_name}")

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
                self.errors.append(ProcessingError("PDF_STRUCTURE_ERROR", 
                    f"Error verifying PDF structure: {str(e)}", file_path.name))
                return False

            return True

        except Exception as e:
            self.errors.append(ProcessingError("VALIDATION_ERROR", str(e), file_path.name))
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
            logger.error(f"Error creating backup: {str(e)}")
            return False

    def save_questions(self, questions: List[Question], output_name: str) -> Optional[Path]:
        """Save processed questions to JSON file."""
        try:
            output_path = self.output_dir / f"{output_name}.json"
            questions_data = [q.to_dict() for q in questions]
            
            with open(output_path, 'w', encoding='utf-8') as f:
                json.dump(questions_data, f, indent=2, ensure_ascii=False)
                
            logger.info(f"Saved {len(questions)} questions to {output_path}")
            return output_path
            
        except Exception as e:
            logger.error(f"Error saving questions: {str(e)}")
            return None