import os
import secrets
from flask import Flask
from flask_login import LoginManager
from db import close_db
from models import User
from extensions import mail

# Blueprints
from blueprints.auth import auth_bp
from blueprints.product import product_bp
from blueprints.order import order_bp
from blueprints.custom_order import custom_order_bp
from blueprints.complaint import complaint_bp
from blueprints.cart import cart_bp
from blueprints.seller import seller_bp
from blueprints.admin import admin_bp

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def create_app():
    app = Flask(__name__, template_folder='templates', static_folder='static')
    app.secret_key = secrets.token_hex(32)

    # --- Email Configuration (Gmail SMTP) ---
    app.config['MAIL_SERVER'] = 'smtp.gmail.com'
    app.config['MAIL_PORT'] = 587
    app.config['MAIL_USE_TLS'] = True
    app.config['MAIL_USERNAME'] = 'jrp6305@gmail.com'
    app.config['MAIL_PASSWORD'] = 'mffq dbbw gona nipm'
    app.config['MAIL_DEFAULT_SENDER'] = 'jrp6305@gmail.com'
    
    mail.init_app(app)

    # --- Razorpay Configuration ---
    app.config['RAZORPAY_KEY_ID'] = 'rzp_test_SPAX3rLNKC7AsO'
    app.config['RAZORPAY_KEY_SECRET'] = 'Kx5CCmWJv92z5ylqSut9ETyZ'

    # --- Flask-Login Setup ---
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please login to access this page.'
    login_manager.login_message_category = 'info'

    @login_manager.user_loader
    def load_user(user_id):
        return User.get(int(user_id))

    # --- Teardown DB ---
    app.teardown_appcontext(close_db)

    # --- Register Blueprints ---
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(product_bp)
    app.register_blueprint(order_bp)
    app.register_blueprint(custom_order_bp)
    app.register_blueprint(complaint_bp)
    app.register_blueprint(cart_bp)
    app.register_blueprint(seller_bp)
    app.register_blueprint(admin_bp)

    @app.context_processor
    def utility_processor():
        from flask_login import current_user
        from db import query_db
        cart_count = 0
        if current_user.is_authenticated:
            # Query from DB
            res = query_db('SELECT SUM(quantity) as count FROM cart WHERE u_id = ?', [current_user.u_id], one=True)
            if res and res['count']:
                cart_count = res['count']
        return dict(cart_count=cart_count)

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, port=5000)
