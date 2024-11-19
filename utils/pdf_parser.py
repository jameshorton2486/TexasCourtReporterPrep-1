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
        
        # Split text into potential sections, considering multiple line breaks as separators
        blocks = re.split(r'\n{2,}', text)
        current_category = None
        
        for block in blocks:
            block = block.strip()
            if not block:
                continue
            
            # Check for category headers
            if any(block.lower().startswith(cat.lower()) and block.endswith(('Questions:', 'QUESTIONS:')) 
               for cat in self.CATEGORIES.keys()):
                current_category = next(cat for cat in self.CATEGORIES.keys() 
                                 if block.lower().startswith(cat.lower()))
                self.current_category = current_category
                continue
            
            # Split block into lines for better question detection
            lines = block.split('\n')
            current_question = None
            current_answer = []
            
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                
                # Check for question patterns
                question_patterns = [
                    r'^(?:\d+\.?\s*)?(?:Q:)?\s*([^?]+\?)',  # Numbered or Q: prefix
                    r'^[•\-*]\s*([^?]+\?)',  # Bullet points
                    r'^(?:What|Who|Where|When|Why|How|Which|Whose|Whom)[^?]+\?'  # Question words
                ]
                
                is_question = any(re.match(pattern, line, re.IGNORECASE) for pattern in question_patterns)
                
                if is_question:
                    # Save previous question if exists
                    if current_question and current_answer:
                        answer_text = ' '.join(current_answer).strip()
                        if self._validate_question_text(current_question):
                            sections.append((current_question, answer_text))
                
                    # Extract new question
                    current_question = line
                    current_answer = []
                elif current_question and line:
                    # Check if line continues the question
                    if not current_answer and line.startswith(('A)', 'B)', 'C)', 'D)')):
                        current_question += f" {line}"
                    else:
                        current_answer.append(line)
        
            # Add last question from the block
            if current_question and current_answer:
                answer_text = ' '.join(current_answer).strip()
                if self._validate_question_text(current_question):
                    sections.append((current_question, answer_text))
    
        logger.info(f"Extracted {len(sections)} questions")
        return sections

    def _validate_question_text(self, text: str) -> bool:
        """Validate question text with improved checks."""
        if not text or not isinstance(text, str):
            return False
            
        # Clean up the text
        text = text.strip()
        
        # Basic format checks
        if not text.endswith('?'):
            return False
            
        # Length checks (between 5 and 100 words)
        words = text.split()
        if len(words) < 5 or len(words) > 100:
            return False
            
        # Check for question words (more comprehensive list)
        question_words = r'\b(what|who|where|when|why|how|which|whose|whom|explain|describe|discuss|define|compare|contrast|analyze|evaluate|list|identify)\b'
        if not re.search(question_words, text.lower()):
            return False
            
        # Check for proper sentence structure
        has_verb = re.search(r'\b(is|are|was|were|do|does|did|will|can|could|should|would|have|has|had|explain|describe|define)\b', text, re.IGNORECASE)
        if not has_verb:
            return False
            
        return True

    def _generate_wrong_answers(self, correct_answer: str) -> List[str]:
        """Generate plausible wrong answers based on the correct answer."""
        try:
            # Use category-specific knowledge for better wrong answers
            category_context = {
                'Legal & Judicial Terminology': {
                    'opposites': {
                        'plaintiff': 'defendant',
                        'prosecution': 'defense',
                        'civil': 'criminal',
                        'direct examination': 'cross examination'
                    },
                    'variations': [
                        'The term refers to a different legal concept',
                        'This definition applies to a different jurisdiction',
                        'This is a common misconception but incorrect'
                    ]
                },
                'Professional Standards & Ethics': {
                    'opposites': {
                        'must': 'should not',
                        'required': 'optional',
                        'immediately': 'within 30 days',
                        'confidential': 'public'
                    },
                    'variations': [
                        'This would violate ethical guidelines',
                        'This is not consistent with professional standards',
                        'This practice is no longer accepted'
                    ]
                },
                'Grammar & Vocabulary': {
                    'opposites': {
                        'italicize': 'bold',
                        'capitalize': 'lowercase',
                        'verbatim': 'paraphrase',
                        'formal': 'informal'
                    },
                    'variations': [
                        'This formatting is incorrect according to standards',
                        'This is an outdated style guideline',
                        'This violates current formatting rules'
                    ]
                },
                'Transcription Standards': {
                    'opposites': {
                        'real-time': 'post-session',
                        'certified': 'unofficial',
                        'original': 'copy',
                        'sealed': 'public'
                    },
                    'variations': [
                        'This format is not accepted in legal transcripts',
                        'This violates transcription guidelines',
                        'This is not the correct procedure'
                    ]
                }
            }

            current_category = self.current_category or 'Legal & Judicial Terminology'
            context = category_context.get(current_category, category_context['Legal & Judicial Terminology'])
            
            # Try to generate context-aware wrong answers first
            wrong_answers = []
            
            # 1. Try opposite-based answer
            for key, value in context['opposites'].items():
                if key.lower() in correct_answer.lower():
                    modified = correct_answer.lower().replace(key.lower(), value.lower())
                    wrong_answers.append(modified.capitalize())
                    break
                    
            # 2. Add a variation with qualification
            if len(wrong_answers) < 3:
                for variation in context['variations']:
                    wrong_answer = f"{variation}: {' '.join(correct_answer.split()[:3])}..."
                    wrong_answers.append(wrong_answer)
                    if len(wrong_answers) >= 3:
                        break
                        
            # 3. Use Perplexity API as a fallback
            if len(wrong_answers) < 3:
                try:
                    from utils.perplexity import generate_questions
                    prompt = f"""Given the correct answer: "{correct_answer}"
                    Generate {3 - len(wrong_answers)} plausible but incorrect answers that:
                    1. Are related to {current_category}
                    2. Have similar length and complexity
                    3. Are grammatically correct
                    4. Sound convincing but are factually wrong
                    5. Maintain a similar style and tone"""
                    
                    generated = generate_questions(current_category, count=1)
                    if generated and len(generated) > 0:
                        api_answers = generated[0].get('wrong_answers', [])
                        wrong_answers.extend(api_answers[:3 - len(wrong_answers)])
                        
                except Exception as e:
                    logger.warning(f"Error generating answers with API: {str(e)}")
                    
            # Ensure we have exactly 3 wrong answers
            while len(wrong_answers) < 3:
                wrong_answers.append(self._generate_fallback_wrong_answers(correct_answer)[0])
                
            return wrong_answers[:3]
            
        except Exception as e:
            logger.error(f"Error in wrong answer generation: {str(e)}")
            return self._generate_fallback_wrong_answers(correct_answer)

    def _generate_fallback_wrong_answers(self, correct_answer: str) -> List[str]:
        """Generate fallback wrong answers when API generation fails."""
        # Create variations by modifying key parts of the correct answer
        words = correct_answer.split()
        if len(words) < 3:
            return [
                "This is not the correct procedure or definition.",
                "The answer contains incorrect information or process.",
                "This explanation is not accurate for this context."
            ]
            
        # Generate wrong answers by modifying key elements
        wrong_answers = []
        
        # Modify numerical values if present
        numbers = re.findall(r'\d+', correct_answer)
        if numbers:
            modified = correct_answer
            for num in numbers:
                new_num = str(int(num) + 5)
                modified = modified.replace(num, new_num, 1)
            wrong_answers.append(modified)
            
        # Change key terms
        legal_terms = {
            'plaintiff': 'defendant',
            'defendant': 'plaintiff',
            'court': 'jury',
            'judge': 'attorney',
            'testimony': 'statement',
            'exhibit': 'document',
            'deposition': 'hearing',
            'trial': 'hearing',
            'witness': 'party',
            'motion': 'petition'
        }
        
        modified = correct_answer.lower()
        for term, replacement in legal_terms.items():
            if term in modified:
                wrong_answer = correct_answer.replace(term, replacement)
                wrong_answers.append(wrong_answer)
                if len(wrong_answers) >= 3:
                    break
                    
        # Add opposite meaning if needed
        if len(wrong_answers) < 3:
            negation = correct_answer
            if 'must' in negation:
                negation = negation.replace('must', 'should not')
            elif 'should' in negation:
                negation = negation.replace('should', 'should not')
            elif 'is' in negation:
                negation = negation.replace('is', 'is not')
            if negation != correct_answer:
                wrong_answers.append(negation)
                
        # Fill remaining slots with generic but contextual wrong answers
        while len(wrong_answers) < 3:
            generic = [
                f"The opposite approach is correct: {' '.join(words[-3:])}",
                f"This varies by jurisdiction and is not standardized",
                f"There is no specific requirement for this in court reporting"
            ]
            for ans in generic:
                if ans not in wrong_answers:
                    wrong_answers.append(ans)
                    if len(wrong_answers) >= 3:
                        break
                        
        return wrong_answers[:3]

    def _extract_answer_options(self, text: str) -> Optional[Dict[str, str]]:
        """Extract multiple choice options if present in the text."""
        try:
            options = {}
            option_pattern = r'([A-D])\.\s*([^\n]+)'
            matches = re.finditer(option_pattern, text)
            
            for match in matches:
                letter, answer = match.groups()
                options[letter] = answer.strip()
                
            # Only return if we found a complete set of options
            if len(options) == 4 and all(letter in options for letter in 'ABCD'):
                return options
            return None
            
        except Exception as e:
            logger.error(f"Error extracting answer options: {str(e)}")
            return None

    def _generate_context_aware_wrong_answers(self, correct_answer: str, category: str) -> List[str]:
        """Generate wrong answers based on the context and category."""
        try:
            # Get category-specific keywords
            keywords = self.CATEGORIES.get(category, [])
            
            # Basic transformations based on answer type
            if any(word in correct_answer.lower() for word in ['is', 'are', 'means']):
                # Definition-style answer
                return [
                    f"This refers to a different legal concept in {category}",
                    f"While related to {keywords[0] if keywords else 'the topic'}, this is incorrect",
                    f"This is a common misconception in {category}"
                ]
            elif re.search(r'\d+', correct_answer):
                # Numerical answer
                numbers = re.findall(r'\d+', correct_answer)
                if numbers:
                    num = int(numbers[0])
                    return [
                        correct_answer.replace(str(num), str(num + 5)),
                        correct_answer.replace(str(num), str(num - 5)),
                        correct_answer.replace(str(num), str(num * 2))
                    ]
            
            # Default format-based answers
            return [
                f"Incorrect approach in {category}",
                f"This violates standard practices in {category}",
                f"This is not recommended in {category}"
            ]
            
        except Exception as e:
            logger.error(f"Error generating wrong answers: {str(e)}")
            return self._generate_wrong_answers(correct_answer)  # Fallback to basic generation

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
                    # Extract answer options (if present)
                    options = self._extract_answer_options(answer_text)
                    if options:
                        answer_text = options.get(correct_answer_letter, answer_text)
                    
                    # Create question object
                    category = self._detect_category(question_text)
                    wrong_answers = self._generate_context_aware_wrong_answers(answer_text, category)
                    
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
        """Save processed questions to JSON file with enhanced validation."""
        try:
            if not questions:
                logger.warning("No questions to save")
                return None

            # Validate all questions before saving
            valid_questions = []
            for question in questions:
                if not isinstance(question, Question):
                    logger.warning(f"Invalid question object type: {type(question)}")
                    continue

                # Validate question format
                if not all([
                    question.question_text.strip(),
                    question.correct_answer.strip(),
                    isinstance(question.wrong_answers, list),
                    len(question.wrong_answers) == 3,
                    all(isinstance(ans, str) and ans.strip() for ans in question.wrong_answers),
                    question.category in self.CATEGORIES,
                    question.source_file.strip()
                ]):
                    logger.warning(f"Invalid question format: {question.question_text[:50]}...")
                    continue

                valid_questions.append(question)

            if not valid_questions:
                logger.warning("No valid questions to save")
                return None

            # Create output file with timestamp
            output_file = self.output_dir / f"{output_name}.json"
            
            # Save with proper JSON formatting
            with open(output_file, 'w', encoding='utf-8') as f:
                json_data = {
                    'metadata': {
                        'timestamp': datetime.utcnow().isoformat(),
                        'total_questions': len(valid_questions),
                        'source_file': valid_questions[0].source_file if valid_questions else None
                    },
                    'questions': [q.to_dict() for q in valid_questions]
                }
                json.dump(json_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Saved {len(valid_questions)} questions to {output_file}")
            return output_file

        except Exception as e:
            logger.error(f"Error saving questions: {str(e)}")
            return None

    def _extract_answer_options(self, text: str) -> Optional[Dict[str, str]]:
        """Extract multiple choice options if present in the text."""
        try:
            options = {}
            option_pattern = r'([A-D])\.\s*([^\n]+)'
            matches = re.finditer(option_pattern, text)
            
            for match in matches:
                letter, answer = match.groups()
                options[letter] = answer.strip()
                
            # Only return if we found a complete set of options
            if len(options) == 4 and all(letter in options for letter in 'ABCD'):
                return options
            return None
            
        except Exception as e:
            logger.error(f"Error extracting answer options: {str(e)}")
            return None

    def _generate_context_aware_wrong_answers(self, correct_answer: str, category: str) -> List[str]:
        """Generate wrong answers based on the context and category."""
        try:
            # Get category-specific keywords
            keywords = self.CATEGORIES.get(category, [])
            
            # Basic transformations based on answer type
            if any(word in correct_answer.lower() for word in ['is', 'are', 'means']):
                # Definition-style answer
                return [
                    f"This refers to a different legal concept in {category}",
                    f"While related to {keywords[0] if keywords else 'the topic'}, this is incorrect",
                    f"This is a common misconception in {category}"
                ]
            elif re.search(r'\d+', correct_answer):
                # Numerical answer
                numbers = re.findall(r'\d+', correct_answer)
                if numbers:
                    num = int(numbers[0])
                    return [
                        correct_answer.replace(str(num), str(num + 5)),
                        correct_answer.replace(str(num), str(num - 5)),
                        correct_answer.replace(str(num), str(num * 2))
                    ]
            
            # Default format-based answers
            return [
                f"Incorrect approach in {category}",
                f"This violates standard practices in {category}",
                f"This is not recommended in {category}"
            ]
            
        except Exception as e:
            logger.error(f"Error generating wrong answers: {str(e)}")
            return self._generate_wrong_answers(correct_answer)  # Fallback to basic generation

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
                    # Extract answer options (if present)
                    options = self._extract_answer_options(answer_text)
                    if options:
                        answer_text = options.get(correct_answer_letter, answer_text)
                    
                    # Create question object
                    category = self._detect_category(question_text)
                    wrong_answers = self._generate_context_aware_wrong_answers(answer_text, category)
                    
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