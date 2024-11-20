import os
import logging
import json
import requests
import time
import uuid
from typing import List, Dict, Optional, Union
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import re

logger = logging.getLogger(__name__)

COURT_REPORTER_TOPICS = [
    'Legal & Judicial Terminology',
    'Professional Standards & Ethics',
    'Grammar & Vocabulary',
    'Transcription Standards',
    'Court Procedures',
    'Deposition Protocol',
    'Reporting Equipment',
    'Certification Requirements'
]

# Existing fallback questions...
FALLBACK_QUESTIONS = {
    'Legal & Judicial Terminology': [
        {
            'question_text': 'What is the meaning of "voir dire" in legal proceedings?',
            'correct_answer': 'It is a preliminary examination of a witness or juror to determine their qualifications.',
            'wrong_answers': [
                'It is a final argument presented to the jury.',
                'It is a type of legal document filed with the court.',
                'It is a meeting between attorneys and the judge.'
            ],
            'category': 'Legal & Judicial Terminology'
        }
    ],
    'Professional Standards & Ethics': [
        {
            'question_text': 'What is the primary duty of a court reporter regarding confidentiality?',
            'correct_answer': 'To maintain strict confidentiality of all information obtained during proceedings.',
            'wrong_answers': [
                'To share information only with other court reporters.',
                'To discuss cases only after they are closed.',
                'To maintain records for personal reference.'
            ],
            'category': 'Professional Standards & Ethics'
        }
    ]
}

class PerplexityAPIError(Exception):
    """Custom exception for Perplexity API errors"""
    def __init__(self, message: str, status_code: Optional[int] = None, response_data: Optional[dict] = None):
        self.message = message
        self.status_code = status_code
        self.response_data = response_data
        super().__init__(self.message)

def should_retry_error(exception):
    """Determine if we should retry based on the error type"""
    if isinstance(exception, PerplexityAPIError):
        # Retry on rate limits and server errors
        return exception.status_code in {429, 500, 502, 503, 504}
    return isinstance(exception, (requests.ConnectionError, requests.Timeout))

@retry(
    retry=retry_if_exception_type(should_retry_error),
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=2, min=4, max=60),
    reraise=True
)
def generate_questions(topic: str, count: int = 3) -> Optional[List[Dict]]:
    """Generate questions using Perplexity AI API with enhanced error handling and retries."""
    request_id = str(uuid.uuid4())
    logger.info(f"Starting question generation for topic: {topic}, count: {count}, request_id: {request_id}")
    
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logger.error(f"Perplexity API key not found in environment, request_id: {request_id}")
        return get_fallback_questions(topic, count)

    prompt = format_prompt(topic, count)
    
    try:
        start_time = time.time()
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json={
                'model': 'llama-3.1-sonar-small-128k-online',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 2048,
                'temperature': 0.7,
                'top_p': 0.9,
                'stop': ["\nQuestion: ", "\nCorrect:"]  # Added stop sequences
            },
            timeout=30
        )
        
        response_time = time.time() - start_time
        logger.info(f"API response time: {response_time:.2f}s, request_id: {request_id}")
        
        try:
            response_data = response.json()
        except ValueError as e:
            raise PerplexityAPIError(
                f"Invalid JSON response: {str(e)}",
                status_code=response.status_code
            )

        if response.status_code != 200:
            error_msg = response_data.get('error', {}).get('message', 'Unknown error')
            raise PerplexityAPIError(
                f"API error {response.status_code}: {error_msg}",
                status_code=response.status_code,
                response_data=response_data
            )
            
        content = response_data.get('choices', [{}])[0].get('message', {}).get('content')
        if not content:
            logger.error(f"Empty or invalid response from API, request_id: {request_id}")
            return get_fallback_questions(topic, count)
            
        questions = []
        raw_questions = content.split('\n\nQuestion: ')
        
        logger.info(f"Processing {len(raw_questions)-1} raw questions, request_id: {request_id}")
        
        for raw_q in raw_questions[1:]:  # Skip first empty split
            try:
                lines = raw_q.strip().split('\n')
                question_text = lines[0].strip('"')
                options = []
                correct_letter = None
                
                for line in lines[1:]:
                    if line.startswith('Correct:'):
                        correct_letter = line.split(':')[1].strip()
                    elif line.startswith(('A.', 'B.', 'C.', 'D.')):
                        options.append(line[2:].strip())
                
                if len(options) == 4 and correct_letter in ['A', 'B', 'C', 'D']:
                    correct_index = ord(correct_letter) - ord('A')
                    question = {
                        'question_text': question_text,
                        'correct_answer': options[correct_index],
                        'wrong_answers': [opt for i, opt in enumerate(options) if i != correct_index],
                        'category': topic
                    }
                    
                    if validate_generated_question(question):
                        questions.append(question)
                        logger.debug(f"Successfully parsed question: {question_text[:50]}...")
                    else:
                        logger.warning(f"Question validation failed: {question_text[:50]}...")
                    
            except Exception as e:
                logger.error(f"Error parsing generated question: {str(e)}, request_id: {request_id}", exc_info=True)
                continue
        
        if questions:
            logger.info(f"Successfully generated {len(questions)} valid questions, request_id: {request_id}")
            return questions
        else:
            logger.warning(f"No valid questions were generated, falling back to default questions, request_id: {request_id}")
            return get_fallback_questions(topic, count)
        
    except PerplexityAPIError as e:
        logger.error(f"Perplexity API error: {str(e)}, status_code: {e.status_code}, request_id: {request_id}")
        if should_retry_error(e):
            raise  # Let retry handle the error
        return get_fallback_questions(topic, count)
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}, request_id: {request_id}", exc_info=True)
        raise  # Let retry handle the error
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}, request_id: {request_id}", exc_info=True)
        return get_fallback_questions(topic, count)

def validate_generated_question(question: Dict) -> bool:
    """Validate a generated question for quality and completeness."""
    try:
        # Check required fields
        required_fields = ['question_text', 'correct_answer', 'wrong_answers', 'category']
        if not all(key in question for key in required_fields):
            logger.warning(f"Missing required fields in question. Has: {list(question.keys())}")
            return False
            
        # Question text validation
        question_text = question['question_text']
        if not isinstance(question_text, str):
            logger.warning("Question text must be a string")
            return False
            
        # Question content validation
        if not (question_text.strip() and 
                len(question_text.split()) >= 5 and 
                question_text.endswith('?')):
            logger.warning(f"Invalid question format: {question_text[:100]}")
            return False
            
        # Check for question structure
        question_words = r'\b(what|who|where|when|why|how|which|whose|whom)\b'
        if not re.search(question_words, question_text, re.IGNORECASE):
            logger.warning("Question lacks proper question word")
            return False
            
        # Answer validations
        if not isinstance(question['correct_answer'], str) or not question['correct_answer'].strip():
            logger.warning("Invalid correct answer")
            return False
            
        if not isinstance(question['wrong_answers'], list) or len(question['wrong_answers']) != 3:
            logger.warning(f"Wrong answers must be a list of exactly 3 items, got {len(question.get('wrong_answers', []))}")
            return False
            
        # Validate all answers
        all_answers = [question['correct_answer']] + question['wrong_answers']
        
        # Check each answer
        for answer in all_answers:
            if not isinstance(answer, str) or len(answer.split()) < 2:
                logger.warning(f"Invalid answer format: {answer}")
                return False
                
            # Check for complete sentence structure
            if not re.search(r'\b(is|are|was|were|will|can|have|has|had)\b', answer, re.IGNORECASE):
                logger.warning(f"Answer lacks proper sentence structure: {answer}")
                return False
        
        # Check for duplicates or similar answers
        answer_lower = [ans.lower() for ans in all_answers]
        if len(set(answer_lower)) != len(all_answers):
            logger.warning("Duplicate answers found")
            return False
            
        # Check for answer overlap
        for i, ans1 in enumerate(answer_lower):
            words1 = set(ans1.split())
            for ans2 in answer_lower[i+1:]:
                words2 = set(ans2.split())
                overlap = words1.intersection(words2)
                if len(overlap) / min(len(words1), len(words2)) > 0.5:
                    logger.warning("Answers have too much overlap")
                    return False
        
        # Category validation
        if question['category'] not in COURT_REPORTER_TOPICS:
            logger.warning(f"Invalid category: {question['category']}")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error validating generated question: {str(e)}", exc_info=True)
        return False

def format_prompt(topic: str, count: int) -> str:
    """Format the prompt for question generation."""
    return f'''Generate {count} multiple-choice questions about {topic} for Texas Court Reporter exam preparation.
    Each question should:
    1. Be relevant to {topic}
    2. Have exactly one correct answer and three wrong answers
    3. Be clear and unambiguous
    4. Use proper grammar and punctuation
    5. Include a question mark at the end of the question
    6. Have answers that are complete sentences
    7. Avoid overlapping or similar answer choices
    
    Format each question exactly like this:
    
    Question: "[Complete question text]?"
    A. [First option]
    B. [Second option]
    C. [Third option]
    D. [Fourth option]
    Correct: [A/B/C/D]
    '''

def get_fallback_questions(topic: str, count: int) -> List[Dict]:
    """Get fallback questions when API generation fails."""
    logger.info(f"Using fallback questions for topic: {topic}")
    if topic in FALLBACK_QUESTIONS:
        questions = FALLBACK_QUESTIONS[topic]
        return questions[:count]  # Return only requested number of questions
    return []