from flask import Blueprint

bp = Blueprint('main', __name__)

from . import dashboard  # Import views after creating blueprint to avoid circular imports

def create_admin_user():
    """Create admin user if not exists."""
    from models import User, db
    import os
    
    admin_email = os.environ.get('ADMIN_EMAIL')
    admin_username = os.environ.get('ADMIN_USERNAME')
    admin_password = os.environ.get('ADMIN_PASSWORD')
    
    if not all([admin_email, admin_username, admin_password]):
        return False
        
    admin = User.query.filter_by(email=admin_email).first()
    if not admin:
        admin = User(
            username=admin_username,
            email=admin_email,
            is_admin=True
        )
        admin.set_password(admin_password)
        db.session.add(admin)
        db.session.commit()
        return True
    return True
