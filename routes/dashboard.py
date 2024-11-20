from flask import Blueprint, render_template, jsonify
from flask_login import login_required, current_user
from models import UserQuestionPerformance, Category, Question, Test, StudySession, db
from sqlalchemy import func, desc, and_
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

        # Study time analytics
        total_study_time = db.session.query(
            func.sum(StudySession.actual_duration)
        ).filter(
            StudySession.user_id == current_user.id,
            StudySession.is_completed == True
        ).scalar() or 0

        # Recent activity summary
        recent_activity = db.session.query(
            func.date(Test.created_at).label('date'),
            func.count(Test.id).label('tests_taken'),
            func.avg(Test.score).label('avg_score'),
            func.sum(Test.completion_time).label('total_time')
        ).filter(
            Test.user_id == current_user.id,
            Test.created_at >= datetime.utcnow() - timedelta(days=7)
        ).group_by(
            func.date(Test.created_at)
        ).order_by(desc('date')).all()
        
        # Performance by category with detailed metrics
        category_stats = db.session.query(
            Category.name,
            func.count(Question.id).label('total_questions'),
            func.avg(UserQuestionPerformance.ease_factor).label('avg_ease'),
            func.avg(
                (UserQuestionPerformance.correct_attempts * 100.0 / 
                func.nullif(UserQuestionPerformance.total_attempts, 0))
            ).label('accuracy'),
            func.avg(UserQuestionPerformance.average_response_time).label('avg_response_time'),
            func.count(UserQuestionPerformance.id).label('questions_attempted')
        ).join(
            Question, Category.id == Question.category_id
        ).outerjoin(
            UserQuestionPerformance, 
            and_(Question.id == UserQuestionPerformance.question_id,
                 UserQuestionPerformance.user_id == current_user.id)
        ).group_by(Category.name).all()

        # Study streak calculation
        study_dates = db.session.query(
            func.date(StudySession.start_time)
        ).filter(
            StudySession.user_id == current_user.id,
            StudySession.is_completed == True
        ).distinct().order_by(
            func.date(StudySession.start_time)
        ).all()

        current_streak = 0
        if study_dates:
            today = datetime.utcnow().date()
            last_date = None
            for date_tuple in reversed(study_dates):
                date = date_tuple[0]
                if last_date is None or (last_date - date).days == 1:
                    current_streak += 1
                    last_date = date
                else:
                    break

        # Weak areas identification
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
            UserQuestionPerformance.total_attempts,
            UserQuestionPerformance.average_response_time
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
            total_study_time=total_study_time,
            current_streak=current_streak,
            category_stats=category_stats,
            recent_activity=recent_activity,
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
        # Get performance data over time
        performance_data = db.session.query(
            func.date(Test.created_at).label('date'),
            func.avg(Test.score).label('score'),
            func.count(Test.id).label('tests_taken'),
            func.avg(Test.completion_time).label('avg_completion_time')
        ).filter(
            Test.user_id == current_user.id,
            Test.category_id == category_id,
            Test.completed == True
        ).group_by(
            func.date(Test.created_at)
        ).order_by(
            func.date(Test.created_at)
        ).all()
        
        data = {
            'dates': [str(p.date) for p in performance_data],
            'scores': [float(p.score) for p in performance_data],
            'tests_taken': [int(p.tests_taken) for p in performance_data],
            'avg_completion_time': [float(p.avg_completion_time or 0) for p in performance_data]
        }
            
        return jsonify(data)
        
    except Exception as e:
        logger.error(f"Error in category performance: {str(e)}", exc_info=True)
        return jsonify({'error': 'Failed to load category performance'}), 500
