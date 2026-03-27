from flask_login import UserMixin
from db import query_db


class User(UserMixin):
    """User model backed by sqlite3."""

    def __init__(self, u_id, u_name, u_email, u_role, approval_status='Approved', phone_number=None, first_name=None, last_name=None, created_at=None):
        self.id = u_id          # Flask-Login requires 'id'
        self.u_id = u_id
        self.u_name = u_name
        self.u_email = u_email
        self.u_role = u_role
        self.role = u_role  # Added for template compatibility
        self.approval_status = approval_status
        self.phone_number = phone_number
        self.first_name = first_name
        self.last_name = last_name
        self.created_at = created_at

    @staticmethod
    def get(user_id):
        """Load a user by primary key."""
        row = query_db(
            'SELECT u_id, u_name, u_email, u_role, approval_status, phone_number, first_name, last_name, created_at FROM users WHERE u_id = ?',
            [user_id], one=True
        )
        if row is None:
            return None
        return User(
            u_id=row['u_id'],
            u_name=row['u_name'],
            u_email=row['u_email'],
            u_role=row['u_role'],
            approval_status=row['approval_status'],
            phone_number=row['phone_number'],
            first_name=row['first_name'],
            last_name=row['last_name'],
            created_at=row['created_at']
        )

    @staticmethod
    def get_by_email(email):
        """Load a user by email."""
        row = query_db(
            'SELECT u_id, u_name, first_name, last_name, u_email, u_password, u_role, approval_status, phone_number, created_at FROM users WHERE u_email = ?',
            [email], one=True
        )
        return row  # Returns a sqlite3.Row so caller can check u_password

    def is_active(self):
        return True # Default to True as account_status column is missing
