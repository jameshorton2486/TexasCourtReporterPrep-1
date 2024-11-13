import os
import logging
import json
import requests
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def validate_answer_relevance(question: str, answers: List[str]) -> bool:
    """Validate that answers are relevant to the question."""
    try:
        api_key = os.environ.get('PERPLEXITY_API_KEY')
        if not api_key:
            return True  # Skip validation if no API key
            
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        prompt = f"""Rate the relevance of these answers to the question on a scale of 1-10:
        Question: {question}
        Answers:
        {chr(10).join(f'{i+1}. {ans}' for i, ans in enumerate(answers))}
        
        Return a JSON object with scores and explanation:
        {{
            "scores": [1-10 ratings],
            "explanation": "Brief explanation of ratings"
        }}"""
        
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json={
                'model': 'mistral-7b-instruct',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 1000
            }
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            result = json.loads(content)
            # Consider answers relevant if all scores are 7 or higher
            return all(score >= 7 for score in result['scores'])
            
    except Exception as e:
        logger.error(f"Error validating answer relevance: {str(e)}")
        
    return True  # Default to True on error to not block question generation

def perform_qa_check(question: Dict) -> bool:
    """Perform quality assurance check on question-answer pair."""
    try:
        api_key = os.environ.get('PERPLEXITY_API_KEY')
        if not api_key:
            return True  # Skip validation if no API key
            
        headers = {
            'Authorization': f'Bearer {api_key}',
            'Content-Type': 'application/json'
        }
        
        all_answers = [question['correct_answer']] + question['wrong_answers']
        
        prompt = f"""Evaluate this multiple-choice question for quality and consistency:
        Question: {question['question_text']}
        Correct Answer: {question['correct_answer']}
        Wrong Answers: {', '.join(question['wrong_answers'])}
        
        Check for:
        1. Question clarity and context
        2. Answer relevance to court reporting
        3. Correct answer superiority
        4. Wrong answers plausibility
        5. Complete sentences
        
        Return a JSON object:
        {{
            "passes_quality_check": true/false,
            "issues": ["list of issues if any"]
        }}"""
        
        response = requests.post(
            'https://api.perplexity.ai/chat/completions',
            headers=headers,
            json={
                'model': 'mistral-7b-instruct',
                'messages': [{'role': 'user', 'content': prompt}],
                'max_tokens': 1000
            }
        )
        
        if response.status_code == 200:
            content = response.json()['choices'][0]['message']['content']
            result = json.loads(content)
            return result['passes_quality_check']
            
    except Exception as e:
        logger.error(f"Error performing QA check: {str(e)}")
        
    return True  # Default to True on error

def generate_questions(topic: str, count: int = 3) -> Optional[List[Dict]]:
    """Generate questions using Perplexity AI API with improved formatting and validation."""
    api_key = os.environ.get('PERPLEXITY_API_KEY')
    if not api_key:
        logger.error("Perplexity API key not found in environment")
        return None

    prompt = f"""Generate {count} multiple-choice questions about {topic} for Texas Court Reporter exam preparation.
    Each question must adhere to these strict requirements:
    1. Focus specifically on court reporting procedures, ethics, and legal requirements
    2. Include complete context and background information
    3. Follow exact format:
       Question: "[Clear, contextual question about court reporting]?"
       A. [Complete sentence answer]
       B. [Complete sentence answer]
       C. [Complete sentence answer]
       D. [Complete sentence answer]
       Correct: [Letter]
    
    Requirements for answers:
    1. All answers must be complete, grammatically correct sentences
    2. Correct answer must be clearly superior but not obviously different in style
    3. Wrong answers must be plausible but clearly incorrect
    4. All answers must be relevant to court reporting and the specific question
    5. Answers should be similar in length and detail level
    
    Example format:
    Question: "What is the proper procedure when a conflict of interest is discovered?"
    A. Report to all parties within 3 days of discovery and withdraw if necessary.
    B. Notify only the hiring attorney and continue with the assignment.
    C. Document in personal records only and proceed with caution.
    D. Wait for someone to inquire about potential conflicts.
    Correct: A

    Format each question as a JSON object:
    {{
        "question_text": "Question: [Complete question text]?",
        "correct_answer": "The complete correct answer as a full sentence.",
        "wrong_answers": ["Wrong answer 1.", "Wrong answer 2.", "Wrong answer 3."],
        "category": "Category name (Legal & Judicial Terminology, Professional Standards & Ethics, or Transcription Standards)"
    }}"""

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
                    {'role': 'system', 'content': 'You are an expert in court reporting with deep knowledge of Texas court procedures, ethics, and legal requirements.'},
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
            validated_questions = []
            for q in questions:
                # Format validation
                if not q['question_text'].startswith('Question: '):
                    q['question_text'] = f"Question: {q['question_text']}"
                if not q['question_text'].endswith('?'):
                    q['question_text'] = f"{q['question_text']}?"
                    
                # Ensure proper punctuation
                if not q['correct_answer'].endswith(('.', '!', '?')):
                    q['correct_answer'] = f"{q['correct_answer']}."
                q['wrong_answers'] = [
                    f"{ans}." if not ans.endswith(('.', '!', '?')) else ans
                    for ans in q['wrong_answers']
                ]
                
                # Validate answer relevance
                all_answers = [q['correct_answer']] + q['wrong_answers']
                if validate_answer_relevance(q['question_text'], all_answers):
                    # Perform quality assurance check
                    if perform_qa_check(q):
                        validated_questions.append(q)
                    else:
                        logger.warning(f"Question failed QA check: {q['question_text']}")
                else:
                    logger.warning(f"Question failed relevance check: {q['question_text']}")
                
            logger.info(f"Successfully generated and validated {len(validated_questions)} questions about {topic}")
            return validated_questions
        else:
            logger.error(f"Error from Perplexity API: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error generating questions: {str(e)}")
        return None
