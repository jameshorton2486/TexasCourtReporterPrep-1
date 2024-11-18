import os
import logging
import json
import requests
from typing import List, Dict, Optional

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

def generate_questions(topic: str, count: int = 3) -> Optional[List[Dict]]:
    """Generate questions using Perplexity AI API with strict format."""
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

    Example:
    Question: "What is the proper format for indicating a change in speakers in a court transcript?"
    A. Start a new paragraph with the speaker's name in all caps
    B. Use quotation marks around the speaker's name
    C. Place the speaker's name in parentheses
    D. Continue on the same line with a semicolon
    Correct: A
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
            }
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # Parse the response into structured format
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
                        questions.append(question)
                    
                except Exception as e:
                    logger.error(f"Error parsing question: {str(e)}")
                    continue
            
            logger.info(f"Successfully generated {len(questions)} questions about {topic}")
            return questions
            
        else:
            logger.error(f"Error from Perplexity API: {response.status_code} - {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        return None
