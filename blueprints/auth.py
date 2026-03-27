from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_user, logout_user, login_required, current_user
from flask_mail import Message
from extensions import mail
from werkzeug.security import generate_password_hash, check_password_hash
from db import query_db, execute_db
from models import User
import secrets
from datetime import datetime, timedelta

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('product.home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip()
        password = request.form.get('password', '')

        row = User.get_by_email(email)
        # Check password - supports both plain text (from user's update) and hashed (for new registrations)
        if row:
            is_valid = False
            if row['u_password'] == password: # Plain text check
                is_valid = True
            else:
                try:
                    is_valid = check_password_hash(row['u_password'], password)
                except:
                    is_valid = False
            
            if is_valid:
                user = User(
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

                # NEW: Block non-approved sellers
                if user.role == 'seller':
                    if user.approval_status == 'Pending':
                        flash('Your seller account is pending approval. You will be able to login once the admin approves your profile.', 'info')
                        return redirect(url_for('auth.login'))
                    elif user.approval_status == 'Rejected':
                        flash('Your seller registration has been rejected. Please contact support if you believe this is a mistake.', 'error')
                        return redirect(url_for('auth.login'))

                login_user(user)
                
                # Migrate session cart to DB if any (optional but good)
                session_cart = session.pop('cart', [])
                if session_cart:
                    for item in session_cart:
                        # Check if already in DB
                        exists = query_db('SELECT cart_id FROM cart WHERE u_id = ? AND p_id = ?', 
                                         [user.id, item['product_id']], one=True)
                        if exists:
                            execute_db('UPDATE cart SET quantity = quantity + ? WHERE cart_id = ?', 
                                       [item['quantity'], exists['cart_id']])
                        else:
                            execute_db('INSERT INTO cart (u_id, p_id, quantity) VALUES (?, ?, ?)', 
                                       [user.id, item['product_id'], item['quantity']])

                next_page = request.args.get('next')
                return redirect(next_page or url_for('auth.dashboard'))
            else:
                flash('Invalid email or password. Please try again.', 'error')
        else:
            flash('Invalid email or password. Please try again.', 'error')

    return render_template('auth/login.html')


@auth_bp.route('/register', methods=['GET', 'POST'])
def register():
    if current_user.is_authenticated:
        return redirect(url_for('product.home'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        name = f"{first_name} {last_name}"
        email = request.form.get('email', '').strip().lower()
        phone_number = request.form.get('phone_number', '').strip()
        password = request.form.get('password', '')
        role = request.form.get('role', 'buyer')
        shop_name = request.form.get('shop_name', '').strip()
        address = request.form.get('address', '').strip()

        # Validate
        if not all([first_name, email, password]):
            flash('Name, Email and Password are required.', 'error')
            return redirect(url_for('auth.register'))

        # Check existing email
        existing = User.get_by_email(email)
        if existing:
            flash('An account with that email already exists.', 'error')
            return redirect(url_for('auth.register'))

        password_hash = generate_password_hash(password)

        # Default status: Buyers are Approved, Sellers are Pending
        initial_status = 'Approved' if role == 'buyer' else 'Pending'

        user_id = execute_db(
            '''INSERT INTO users (u_name, first_name, last_name, u_email, phone_number, u_password, u_role, approval_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
            [name, first_name, last_name, email, phone_number, password_hash, role, initial_status]
        )

        # If seller, create seller profile (shop_name is optional)
        if role == 'seller':
            execute_db(
                '''INSERT INTO seller_profiles (u_id, shop_name, address, created_at)
                   VALUES (?, ?, ?, datetime('now'))''',
                [user_id, shop_name or f"{name}'s Shop", address]
            )

        flash('Account created successfully! Please log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/register.html')


@auth_bp.route('/register-seller', methods=['GET', 'POST'])
def register_seller():
    if current_user.is_authenticated:
        return redirect(url_for('product.home'))

    if request.method == 'POST':
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        name = f"{first_name} {last_name}"
        email = request.form.get('email', '').strip().lower()
        phone_number = request.form.get('phone_number', '').strip()
        password = request.form.get('password', '')
        shop_name = request.form.get('shop_name', '').strip()
        address = request.form.get('address', '').strip()

        # Validate
        if not all([first_name, email, password, address]):
            flash('All required fields must be filled.', 'error')
            return redirect(url_for('auth.register_seller'))

        # Check existing email
        existing = User.get_by_email(email)
        if existing:
            flash('An account with that email already exists.', 'error')
            return redirect(url_for('auth.register_seller'))

        password_hash = generate_password_hash(password)

        user_id = execute_db(
            '''INSERT INTO users (u_name, first_name, last_name, u_email, phone_number, u_password, u_role, approval_status, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))''',
            [name, first_name, last_name, email, phone_number, password_hash, 'seller', 'Pending']
        )

        execute_db(
            '''INSERT INTO seller_profiles (u_id, shop_name, address, created_at)
               VALUES (?, ?, ?, datetime('now'))''',
            [user_id, shop_name or f"{name}'s Shop", address]
        )

        flash('Seller registration submitted! Please wait for admin approval.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/seller_register.html')


@auth_bp.route('/logout')
@login_required
def logout():
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('product.home'))


@auth_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.u_role == 'admin':
        return redirect(url_for('admin.manage_sellers'))
    if current_user.u_role == 'seller':
        return redirect(url_for('seller.dashboard'))
    
    uid = current_user.u_id

    # Total orders
    order_counts = query_db('''
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN order_status IN ("pending","confirmed","processing","shipped") THEN 1 ELSE 0 END), 0) AS active
        FROM orders WHERE u_id = ?
    ''', [uid], one=True)

    # Custom requests
    custom_counts = query_db('''
        SELECT COUNT(*) AS total,
               COALESCE(SUM(CASE WHEN status = "pending" THEN 1 ELSE 0 END), 0) AS pending,
               COALESCE(SUM(CASE WHEN status = "accepted" THEN 1 ELSE 0 END), 0) AS accepted
        FROM custom_requests WHERE u_id = ?
    ''', [uid], one=True)

    # Pending reviews (orders delivered but not yet reviewed)
    pending_reviews = query_db('''
        SELECT COUNT(*) AS cnt
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        WHERE o.u_id = ? AND o.order_status = "delivered"
          AND NOT EXISTS (
              SELECT 1 FROM reviews r
              WHERE r.p_id = oi.p_id AND r.u_id = ?
          )
    ''', [uid, uid], one=True)

    # Last 3 orders
    recent_orders = query_db('''
        SELECT o.order_id, o.total_amount,
               o.order_status, o.created_at,
               p.p_name as product_name, pi.image_url
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        WHERE o.u_id = ?
        GROUP BY o.order_id
        ORDER BY o.created_at DESC
        LIMIT 3
    ''', [uid])

    # Recent custom requests
    recent_custom = query_db('''
        SELECT cr.cr_id, cr.request_details,
               cr.status as request_status, cr.created_at
        FROM custom_requests cr
        WHERE cr.u_id = ?
        ORDER BY cr.created_at DESC
        LIMIT 3
    ''', [uid])

    # Trending products
    trending = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, 
               COALESCE(AVG(r.rating), 0) AS avg_rating, 
               COUNT(r.r_id) AS review_count,
               pi.image_url
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN reviews r ON p.p_id = r.p_id
        GROUP BY p.p_id
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 3
    ''') or []

    # New arrivals
    new_arrivals = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, 
               pi.image_url, COALESCE(AVG(r.rating), 0) AS avg_rating
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN reviews r ON p.p_id = r.p_id
        GROUP BY p.p_id
        ORDER BY p.created_at DESC
        LIMIT 3
    ''') or []

    # Fetch all products for the "Explore Collections" marquee
    all_products = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, c.c_name as category_name, pi.image_url
        FROM products p
        JOIN categories c ON p.c_id = c.c_id
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        GROUP BY p.p_id
        ORDER BY p.created_at DESC
        LIMIT 21
    ''')
    
    user_wishlist = []
    if current_user.is_authenticated:
        w_res = query_db('SELECT p_id FROM wishlist WHERE u_id = ?', [uid])
        user_wishlist = [w['p_id'] for w in w_res]

    # Occasion Based Products (e.g., Valentine's or Diwali)
    # We can dynamically decide which occasion to show or just show one that has products.
    occasion_products = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, 
               p.p_occasion, pi.image_url
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        WHERE p.p_occasion IS NOT NULL
        GROUP BY p.p_id
        ORDER BY RANDOM()
        LIMIT 6
    ''')

    return render_template('auth/dashboard.html',
        order_total=order_counts['total'] if order_counts else 0,
        order_active=order_counts['active'] if order_counts else 0,
        custom_total=custom_counts['total'] if custom_counts else 0,
        custom_pending=custom_counts['pending'] if custom_counts else 0,
        custom_accepted=custom_counts['accepted'] if custom_counts else 0,
        pending_reviews=pending_reviews['cnt'] if pending_reviews else 0,
        recent_orders=recent_orders,
        recent_custom=recent_custom,
        trending=trending,
        new_arrivals=new_arrivals,
        all_products=all_products,
        occasion_products=occasion_products,
        user_wishlist=user_wishlist
    )

@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        u_name = request.form.get('u_name', '').strip()
        first_name = request.form.get('first_name', '').strip()
        last_name = request.form.get('last_name', '').strip()
        
        if u_name and first_name and last_name:
            execute_db(
                'UPDATE users SET u_name = ?, first_name = ?, last_name = ? WHERE u_id = ?',
                [u_name, first_name, last_name, current_user.u_id]
            )
            flash('Profile updated successfully!', 'success')
        else:
            flash('All fields are required.', 'error')
        return redirect(url_for('auth.profile'))
        
    wishlist_items = query_db('''
        SELECT p.p_id, p.p_name, p.p_price, pi.image_url, sp.shop_name 
        FROM wishlist w
        JOIN products p ON w.p_id = p.p_id
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        WHERE w.u_id = ?
        GROUP BY p.p_id
        ORDER BY w.created_at DESC
    ''', [current_user.u_id])
            
    return render_template('auth/profile.html', wishlist_items=wishlist_items)

@auth_bp.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for('product.home'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        user = User.get_by_email(email)

        if user:
            token = secrets.token_urlsafe(32)
            # Link expires in 1 hour
            expiry = datetime.now() + timedelta(hours=1)
            
            execute_db(
                'UPDATE users SET reset_token = ?, reset_expiry = ? WHERE u_id = ?',
                [token, expiry, user['u_id']]
            )

            reset_link = url_for('auth.reset_password', token=token, _external=True)
            
            # Send Email
            try:
                msg = Message("Password Reset Request | Plattera",
                               recipients=[email])
                
                msg.html = render_template('auth/email_forgot_password.html', 
                                         user_name=user['first_name'], 
                                         reset_link=reset_link)
                mail.send(msg)
                flash('An email with instruction to reset your password has been sent.', 'success')
            except Exception as e:
                print(f"Error sending reset email: {e}")
                flash('An error occurred while sending the email. Please try again later.', 'error')
        else:
            # For security, don't confirm if the email exists
            flash('If an account exists with this email, you will receive reset instructions.', 'info')
        
        return redirect(url_for('auth.login'))

    return render_template('auth/forgot_password.html')

@auth_bp.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    if current_user.is_authenticated:
        return redirect(url_for('product.home'))

    # Verify token
    user = query_db('SELECT u_id, reset_expiry FROM users WHERE reset_token = ?', [token], one=True)
    
    if not user:
        flash('Invalid or expired reset link.', 'error')
        return redirect(url_for('auth.forgot_password'))

    # Check expiry
    expiry_time = datetime.strptime(user['reset_expiry'], '%Y-%m-%d %H:%M:%S.%f') if isinstance(user['reset_expiry'], str) else user['reset_expiry']
    if datetime.now() > expiry_time:
        flash('This reset link has expired.', 'error')
        return redirect(url_for('auth.forgot_password'))

    if request.method == 'POST':
        password = request.form.get('password')
        confirm_password = request.form.get('confirm_password')

        if not password or password != confirm_password:
            flash('Passwords do not match.', 'error')
            return render_template('auth/reset_password.html', token=token)

        password_hash = generate_password_hash(password)
        
        execute_db(
            'UPDATE users SET u_password = ?, reset_token = NULL, reset_expiry = NULL WHERE u_id = ?',
            [password_hash, user['u_id']]
        )
        
        flash('Your password has been reset successfully! You can now log in.', 'success')
        return redirect(url_for('auth.login'))

    return render_template('auth/reset_password.html', token=token)

@auth_bp.route('/save_spin_result', methods=['POST'])
@login_required
def save_spin_result():
    from flask import jsonify
    data = request.get_json()
    coupon_code = data.get('coupon_code')
    if coupon_code:
        # Check if coupon is valid in DB
        coupon = query_db('SELECT * FROM coupons WHERE cp_code = ? AND cp_status = "active"', [coupon_code], one=True)
        if coupon:
            session['active_coupon'] = {
                'code': coupon['cp_code'],
                'discount': coupon['cp_discount_perc']
            }
            return jsonify({'success': True, 'message': f'Coupon {coupon_code} will be applied at checkout!'})
    return jsonify({'success': False, 'message': 'Invalid coupon or better luck next time!'}), 400

@auth_bp.route('/wishlist/toggle', methods=['POST'])
@login_required
def toggle_wishlist():
    from flask import jsonify
    data = request.get_json()
    product_id = data.get('product_id')
    
    if not product_id:
        return jsonify({'success': False, 'message': 'Product ID missing'}), 400
        
    existing = query_db('SELECT w_id FROM wishlist WHERE u_id = ? AND p_id = ?', [current_user.u_id, product_id], one=True)
    if existing:
        execute_db('DELETE FROM wishlist WHERE w_id = ?', [existing['w_id']])
        action = 'removed'
    else:
        execute_db('INSERT INTO wishlist (u_id, p_id) VALUES (?, ?)', [current_user.u_id, product_id])
        action = 'added'
        
    return jsonify({'success': True, 'action': action})
