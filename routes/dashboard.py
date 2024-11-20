from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from models import UserQuestionPerformance, Category, Question, Test
from sqlalchemy import func
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)
dashboard = Blueprint('dashboard', __name__)

@dashboard.route('/dashboard')
@login_required
def show_dashboard():
    try:
        # Overall statistics
        total_questions = UserQuestionPerformance.query.filter_by(user_id=current_user.id).count()
        correct_answers = UserQuestionPerformance.query.filter_by(
            user_id=current_user.id
        ).with_entities(
            func.sum(UserQuestionPerformance.correct_attempts)
        ).scalar() or 0
        
        total_attempts = UserQuestionPerformance.query.filter_by(
            user_id=current_user.id
        ).with_entities(
            func.sum(UserQuestionPerformance.total_attempts)
        ).scalar() or 0
        
        # Calculate accuracy
        accuracy = (correct_answers / total_attempts * 100) if total_attempts > 0 else 0
        
        # Performance by category
        category_stats = db.session.query(
            Category.name,
            func.count(Question.id).label('total_questions'),
            func.avg(UserQuestionPerformance.ease_factor).label('avg_ease'),
            func.avg(
                (UserQuestionPerformance.correct_attempts * 100.0 / 
                UserQuestionPerformance.total_attempts)
            ).label('accuracy')
        ).join(
            Question, Category.id == Question.category_id
        ).join(
            UserQuestionPerformance, Question.id == UserQuestionPerformance.question_id
        ).filter(
            UserQuestionPerformance.user_id == current_user.id
        ).group_by(Category.name).all()
        
        # Recent progress (last 7 days)
        today = datetime.utcnow().date()
        daily_progress = []
        for i in range(7):
            date = today - timedelta(days=i)
            next_date = date + timedelta(days=1)
            
            daily_stats = db.session.query(
                func.count(Test.id).label('tests_taken'),
                func.avg(Test.score).label('avg_score')
            ).filter(
                Test.user_id == current_user.id,
                Test.created_at >= date,
                Test.created_at < next_date,
                Test.completed == True
            ).first()
            
            daily_progress.append({
                'date': date.strftime('%Y-%m-%d'),
                'tests_taken': daily_stats[0] or 0,
                'avg_score': float(daily_stats[1] or 0)
            })
        
        # Areas needing improvement
        weak_areas = db.session.query(
            Category.name,
            func.avg(
                (UserQuestionPerformance.correct_attempts * 100.0 / 
                UserQuestionPerformance.total_attempts)
            ).label('accuracy')
        ).join(
            Question, Category.id == Question.category_id
        ).join(
            UserQuestionPerformance, Question.id == UserQuestionPerformance.question_id
        ).filter(
            UserQuestionPerformance.user_id == current_user.id
        ).group_by(Category.name).having(
            func.avg(
                (UserQuestionPerformance.correct_attempts * 100.0 / 
                UserQuestionPerformance.total_attempts)
            ) < 70
        ).all()
        
        return render_template(
            'dashboard/index.html',
            total_questions=total_questions,
            accuracy=round(accuracy, 2),
            category_stats=category_stats,
            daily_progress=daily_progress,
            weak_areas=weak_areas
        )
        
    except Exception as e:
        logger.error(f"Error in dashboard: {str(e)}", exc_info=True)
        return render_template('error.html', error="Error loading dashboard")

@dashboard.route('/api/performance/category/<int:category_id>')
@login_required
def category_performance(category_id):
    """API endpoint for category-specific performance data"""
    try:
        performance = UserQuestionPerformance.query.join(
            Question
        ).filter(
            UserQuestionPerformance.user_id == current_user.id,
            Question.category_id == category_id
        ).all()
        
        data = {
            'accuracy': [],
            'response_times': [],
            'dates': []
        }
        
        for perf in performance:
            data['accuracy'].append(perf.accuracy)
            data['response_times'].append(perf.average_response_time or 0)
            data['dates'].append(perf.last_attempt_date.strftime('%Y-%m-%d'))
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error in category performance: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to load category performance'}), 500
