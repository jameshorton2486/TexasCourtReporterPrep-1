from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from models import UserQuestionPerformance, Category, Question, Test, db
from sqlalchemy import func, desc
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
        
        # Calculate accuracy and study time
        accuracy = (correct_answers / total_attempts * 100) if total_attempts > 0 else 0
        avg_response_time = UserQuestionPerformance.query.filter_by(
            user_id=current_user.id
        ).with_entities(
            func.avg(UserQuestionPerformance.average_response_time)
        ).scalar() or 0
        
        # Performance by category with detailed metrics
        category_stats = db.session.query(
            Category.name,
            func.count(Question.id).label('total_questions'),
            func.avg(UserQuestionPerformance.ease_factor).label('avg_ease'),
            func.avg(
                (UserQuestionPerformance.correct_attempts * 100.0 / 
                func.nullif(UserQuestionPerformance.total_attempts, 0))
            ).label('accuracy'),
            func.avg(UserQuestionPerformance.average_response_time).label('avg_response_time')
        ).join(
            Question, Category.id == Question.category_id
        ).join(
            UserQuestionPerformance, Question.id == UserQuestionPerformance.question_id
        ).filter(
            UserQuestionPerformance.user_id == current_user.id
        ).group_by(Category.name).all()
        
        # Recent progress (last 7 days) with detailed metrics
        today = datetime.utcnow().date()
        daily_progress = []
        for i in range(7):
            date = today - timedelta(days=i)
            next_date = date + timedelta(days=1)
            
            daily_stats = db.session.query(
                func.count(Test.id).label('tests_taken'),
                func.avg(Test.score).label('avg_score'),
                func.sum(Test.total_time).label('study_time'),
                func.count(UserQuestionPerformance.id).label('questions_practiced')
            ).outerjoin(
                UserQuestionPerformance, 
                db.and_(
                    UserQuestionPerformance.user_id == Test.user_id,
                    func.date(UserQuestionPerformance.last_attempt_date) == date
                )
            ).filter(
                Test.user_id == current_user.id,
                Test.created_at >= date,
                Test.created_at < next_date,
                Test.completed == True
            ).first()
            
            daily_progress.append({
                'date': date.strftime('%Y-%m-%d'),
                'tests_taken': daily_stats[0] or 0,
                'avg_score': float(daily_stats[1] or 0),
                'study_time': float(daily_stats[2] or 0),
                'questions_practiced': daily_stats[3] or 0
            })
        
        # Areas needing improvement with specific recommendations
        weak_areas = db.session.query(
            Category.name,
            func.avg(
                (UserQuestionPerformance.correct_attempts * 100.0 / 
                func.nullif(UserQuestionPerformance.total_attempts, 0))
            ).label('accuracy'),
            func.count(Question.id).label('total_questions'),
            func.avg(UserQuestionPerformance.ease_factor).label('difficulty')
        ).join(
            Question, Category.id == Question.category_id
        ).join(
            UserQuestionPerformance, Question.id == UserQuestionPerformance.question_id
        ).filter(
            UserQuestionPerformance.user_id == current_user.id
        ).group_by(Category.name).having(
            func.avg(
                (UserQuestionPerformance.correct_attempts * 100.0 / 
                func.nullif(UserQuestionPerformance.total_attempts, 0))
            ) < 70
        ).order_by('accuracy').all()
        
        # Most challenging questions
        challenging_questions = db.session.query(
            Question.question_text,
            Category.name.label('category'),
            UserQuestionPerformance.accuracy,
            UserQuestionPerformance.total_attempts
        ).join(
            Category, Question.category_id == Category.id
        ).join(
            UserQuestionPerformance, Question.id == UserQuestionPerformance.question_id
        ).filter(
            UserQuestionPerformance.user_id == current_user.id,
            UserQuestionPerformance.total_attempts > 0,
            UserQuestionPerformance.accuracy < 50
        ).order_by(
            UserQuestionPerformance.accuracy
        ).limit(5).all()
        
        return render_template(
            'dashboard/index.html',
            total_questions=total_questions,
            accuracy=round(accuracy, 2),
            avg_response_time=round(avg_response_time, 2),
            category_stats=category_stats,
            daily_progress=daily_progress,
            weak_areas=weak_areas,
            challenging_questions=challenging_questions
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
        ).order_by(
            UserQuestionPerformance.last_attempt_date
        ).all()
        
        data = {
            'accuracy': [],
            'response_times': [],
            'dates': [],
            'ease_factors': []
        }
        
        for perf in performance:
            data['accuracy'].append(perf.accuracy or 0)
            data['response_times'].append(perf.average_response_time or 0)
            data['dates'].append(perf.last_attempt_date.strftime('%Y-%m-%d'))
            data['ease_factors'].append(perf.ease_factor or 1.0)
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error in category performance: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to load category performance'}), 500
