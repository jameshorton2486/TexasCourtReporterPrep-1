import os
import logging
import json
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def generate_questions(topic: str, count: int = 3) -> Optional[List[Dict]]:
    """Generate questions using Perplexity AI API with improved formatting."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logger.error("Perplexity API key not found in environment")
        return None

    prompt = f"""Generate {count} multiple choice questions about {topic} for Texas Court Reporter exam preparation.
    Each question must:
    1. Have clear context and be specific to court reporting
    2. Include exactly 4 distinct answer choices (A, B, C, D)
    3. Have one clearly marked correct answer
    4. Follow proper question format
    5. Use domain-specific knowledge
    
    Example format:
    Question: "Under what circumstances must a court reporter disclose a conflict of interest?"
    A. Within 3 days of booking if scheduled in advance
    B. Within 5 days after discovering the conflict
    C. Only if specifically asked by an attorney
    D. After the deposition is completed
    Correct Answer: B

    Format each question as a JSON object with:
    {{
        "question_text": "Question: [Complete question text]?",
        "correct_answer": "The correct answer with proper punctuation.",
        "wrong_answers": ["Wrong answer 1.", "Wrong answer 2.", "Wrong answer 3."],
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
                'messages': [
                    {'role': 'system', 'content': 'You are an expert in court reporting and legal procedures.'},
                    {'role': 'user', 'content': prompt}
                ],
                'max_tokens': 2000,
                'temperature': 0.7
            }
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            questions = json.loads(content)
            
            # Validate and format questions
            formatted_questions = []
            for q in questions:
                # Ensure question starts with "Question: "
                if not q['question_text'].startswith('Question: '):
                    q['question_text'] = f"Question: {q['question_text']}"
                
                # Ensure proper punctuation
                if not q['question_text'].endswith('?'):
                    q['question_text'] = f"{q['question_text']}?"
                    
                # Format answers with proper punctuation
                if not q['correct_answer'].endswith(('.', '!', '?')):
                    q['correct_answer'] = f"{q['correct_answer']}."
                    
                q['wrong_answers'] = [
                    f"{ans}." if not ans.endswith(('.', '!', '?')) else ans
                    for ans in q['wrong_answers']
                ]
                
                formatted_questions.append(q)
                
            logger.info(f"Successfully generated {len(formatted_questions)} questions about {topic}")
            return formatted_questions
        else:
            logger.error(f"Error from Perplexity API: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        return None
