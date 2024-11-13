import os
import logging
import json
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def generate_questions(topic: str, count: int = 3) -> Optional[List[Dict]]:
    """Generate questions using Perplexity AI API."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logger.error("Perplexity API key not found in environment")
        return None

    prompt = f"""Generate {count} multiple choice questions about {topic} for Texas Court Reporter exam preparation.
    Format each question as a JSON object with the following structure:
    {{
        "question_text": "The question text ending with ?",
        "correct_answer": "The correct answer",
        "wrong_answers": ["Wrong answer 1", "Wrong answer 2", "Wrong answer 3"],
        "category": "Category name (Legal & Judicial Terminology, Professional Standards & Ethics, or Transcription Standards)"
    }}
    Return an array of these question objects."""

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
                'messages': [{'role': 'user', 'content': prompt}]
            }
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            # Extract JSON array from the response
            questions = json.loads(content)
            logger.info(f"Successfully generated {len(questions)} questions about {topic}")
            return questions
        else:
            logger.error(f"Error from Perplexity API: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        return None
