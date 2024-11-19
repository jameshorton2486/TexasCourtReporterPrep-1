import os
import logging
import json
import requests
import time
from typing import List, Dict, Optional
from tenacity import retry, stop_after_attempt, wait_exponential

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

def validate_generated_question(question: Dict) -> bool:
    """Validate a generated question for quality and completeness."""
    try:
        # Check required fields
        if not all(key in question for key in ['question_text', 'correct_answer', 'wrong_answers']):
            logger.warning("Missing required fields in generated question")
            return False
            
        # Content validation
        question_text = question['question_text']
        if not (
            isinstance(question_text, str) and
            len(question_text.split()) >= 5 and
            question_text.endswith('?')
        ):
            logger.warning(f"Invalid question format: {question_text[:100]}")
            return False
            
        # Answer validation
        if not isinstance(question['correct_answer'], str) or not question['correct_answer'].strip():
            logger.warning("Invalid correct answer")
            return False
            
        if not isinstance(question['wrong_answers'], list) or len(question['wrong_answers']) != 3:
            logger.warning("Wrong answers must be a list of exactly 3 items")
            return False
            
        # Check for duplicate answers
        all_answers = [question['correct_answer']] + question['wrong_answers']
        if len(set(map(str.lower, all_answers))) != len(all_answers):
            logger.warning("Duplicate answers found")
            return False
            
        return True
        
    except Exception as e:
        logger.error(f"Error validating generated question: {str(e)}")
        return False

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=4, max=10),
    reraise=True
)
def generate_questions(topic: str, count: int = 3) -> Optional[List[Dict]]:
    """Generate questions using Perplexity AI API with retry mechanism and validation."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logger.error("Perplexity API key not found in environment")
        return None

    prompt = f'''Generate {count} multiple-choice questions about {topic} for Texas Court Reporter exam preparation.
    Format each question exactly like this:
    
    Question: "[Complete question text]?"
    A. [First option]
    B. [Second option]
    C. [Third option]
    D. [Fourth option]
    Correct: [A/B/C/D]
    '''

    try:
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json={
                'model': 'mistral-7b-instruct',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 2000,
                'temperature': 0.8,
                'top_p': 0.9
            },
            timeout=30
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            questions = []
            raw_questions = content.split('\n\nQuestion: ')
            
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
                        
                except Exception as e:
                    logger.error(f"Error parsing generated question: {str(e)}")
                    continue
            
            if questions:
                logger.info(f"Successfully generated {len(questions)} valid questions about {topic}")
                return questions
            else:
                logger.warning(f"No valid questions were generated for {topic}")
                return None
            
        else:
            logger.error(f"Error from Perplexity API: {response.status_code} - {response.text}")
            return None
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error generating questions: {str(e)}")
        raise  # Let retry handle the error
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        return None
