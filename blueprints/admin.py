from flask import Blueprint, render_template, redirect, url_for, flash, request, session, jsonify
from flask_login import login_required, current_user, login_user, logout_user
from flask_mail import Message
from db import query_db, execute_db
from models import User
from extensions import mail

def send_artisan_email(email, name, approved=True):
    """Helper to send approval/rejection emails."""
    try:
        subject = "Welcome to Plattera! Your Artisan Shop is Approved" if approved else "Update regarding your Artisan Shop"
        
        if approved:
            body = f"Hi {name},\n\nCongratulations! Your artisan profile on Plattera has been approved. You can now login and start listing your amazing products.\n\nGo to your shop: http://127.0.0.1:5000/auth/login\n\nBest regards,\nPlattera Team"
        else:
            body = f"Hi {name},\n\nThank you for your interest in Plattera. After reviewing your artisan profile, we regret to inform you that we cannot approve your registration at this time.\n\nIf you have questions, please reach out to us.\n\nBest regards,\nPlattera Team"

        msg = Message(subject, recipients=[email])
        msg.body = body
        mail.send(msg)
        return True
    except Exception as e:
        print(f"ERROR: Email failed for {email}: {e}")
        return False

admin_bp = Blueprint('admin', __name__, template_folder='templates')

@admin_bp.route('/admin/login', methods=['GET', 'POST'])
def login():
    if session.get('admin_logged_in'):
        return redirect(url_for('admin.dashboard'))

    if request.method == 'POST':
        email = request.form.get('email')
        password = request.form.get('password')
        
        # Check for admin user in DB
        row = User.get_by_email(email)
        if row and row['u_role'] == 'admin' and row['u_password'] == password:
            user = User(
                u_id=row['u_id'],
                u_name=row['u_name'],
                u_email=row['u_email'],
                u_role=row['u_role'],
                approval_status=row['approval_status']
            )
            login_user(user)
            session['admin_logged_in'] = True
            return redirect(url_for('admin.dashboard'))
        else:
            flash('Invalid Admin Credentials', 'error')
            
    return render_template('admin/login.html')

@admin_bp.route('/admin/dashboard')
def dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    
    # Fetch real stats
    stats = {
        'total_sellers': query_db("SELECT COUNT(*) as count FROM users WHERE u_role = 'seller'", one=True)['count'],
        'total_buyers': query_db("SELECT COUNT(*) as count FROM users WHERE u_role = 'buyer'", one=True)['count'],
        'live_products': query_db("SELECT COUNT(*) as count FROM products WHERE p_status = 'Active'", one=True)['count'],
        'pending_approvals': query_db("SELECT COUNT(*) as count FROM users WHERE approval_status = 'Pending'", one=True)['count']
    }
    
    return render_template('admin/dashboard.html', stats=stats)

@admin_bp.route('/admin/sellers')
def manage_sellers():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    
    # Fetch all sellers
    sellers = query_db("""
        SELECT u.*, sp.shop_name 
        FROM users u 
        LEFT JOIN seller_profiles sp ON u.u_id = sp.u_id 
        WHERE u.u_role = 'seller' 
        ORDER BY u.created_at DESC
    """)
    
    # Fetch all buyers
    buyers = query_db("SELECT * FROM users WHERE u_role = 'buyer' ORDER BY created_at DESC")
    
    # Fetch pending approvals
    pending = query_db("""
        SELECT u.*, sp.shop_name 
        FROM users u 
        LEFT JOIN seller_profiles sp ON u.u_id = sp.u_id 
        WHERE u.approval_status = 'Pending' 
        ORDER BY u.created_at DESC
    """)

    # Overall stats for usermanage.html
    stats = {
        'total_sellers': len(sellers),
        'active_sellers': len([s for s in sellers if s['approval_status'] == 'Approved']),
        'suspended_sellers': len([s for s in sellers if s['approval_status'] == 'Rejected']),
        'total_buyers': len(buyers),
        'pending_apps': len(pending)
    }
    
    return render_template('admin/usermanage.html', 
                           sellers=sellers, 
                           buyers=buyers, 
                           pending=pending,
                           stats=stats)

@admin_bp.route('/admin/products')
def manage_products():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    
    # Fetch all products with seller names
    all_products = query_db("""
        SELECT p.*, sp.shop_name 
        FROM products p 
        LEFT JOIN users u ON p.seller_id = u.u_id
        LEFT JOIN seller_profiles sp ON u.u_id = sp.u_id
        ORDER BY p.created_at DESC
    """)
    
    active_products = [p for p in all_products if p['p_status'] == 'Active']
    pending_products = [p for p in all_products if p['p_status'] == 'Pending']
    reported_products = [p for p in all_products if p['p_status'] == 'Reported'] # Assuming 'Reported' is a status

    # Summary stats
    stats = {
        'total': len(all_products),
        'active': len(active_products),
        'pending': len(pending_products),
        'reported': len(reported_products)
    }
    
    return render_template('admin/product.html', 
                           all_products=all_products,
                           active_products=active_products,
                           pending_products=pending_products,
                           reported_products=reported_products,
                           stats=stats)

@admin_bp.route('/admin/approve_seller/<int:user_id>', methods=['POST'])
def approve_seller(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user = query_db("SELECT u_email, u_name FROM users WHERE u_id = ?", [user_id], one=True)
    if user:
        execute_db("UPDATE users SET approval_status = 'Approved', u_role = 'Seller' WHERE u_id = ?", [user_id])
        
        # Notify Seller via Email
        from flask_mail import Message
        from extensions import mail
        msg = Message("Seller Account Approved - Plattera", recipients=[user['u_email']])
        msg.body = f"Hello {user['u_name']},\n\nYour seller account on Plattera has been approved! You can now start listing your products.\n\nRegards,\nPlattera Team"
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Mail Error: {e}")
            
        flash(f'Seller {user["u_name"]} approved.', 'success')
    return redirect(url_for('admin.manage_sellers'))

@admin_bp.route('/admin/reject_seller/<int:user_id>', methods=['POST'])
def reject_seller(user_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    user = query_db("SELECT u_email, u_name FROM users WHERE u_id = ?", [user_id], one=True)
    if user:
        execute_db("UPDATE users SET approval_status = 'Rejected' WHERE u_id = ?", [user_id])
        
        from flask_mail import Message
        from extensions import mail
        msg = Message("Seller Account Status - Plattera", recipients=[user['u_email']])
        msg.body = f"Hello {user['u_name']},\n\nWe regret to inform you that your seller registration has been rejected.\n\nRegards,\nPlattera Team"
        try:
            mail.send(msg)
        except Exception as e:
            print(f"Mail Error: {e}")
            
        flash(f'Seller {user["u_name"]} rejected.', 'warning')
    return redirect(url_for('admin.manage_sellers'))

@admin_bp.route('/admin/approve_product/<int:product_id>', methods=['POST'])
def approve_product(product_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    execute_db("UPDATE products SET p_status = 'Active' WHERE p_id = ?", [product_id])
    flash(f'Product #{product_id} approved.', 'success')
    return redirect(url_for('admin.manage_products'))

@admin_bp.route('/admin/reject_product/<int:product_id>', methods=['POST'])
def reject_product(product_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    execute_db("UPDATE products SET p_status = 'Rejected' WHERE p_id = ?", [product_id])
    flash(f'Product #{product_id} rejected.', 'warning')
    return redirect(url_for('admin.manage_products'))

@admin_bp.route('/admin/delete_product/<int:product_id>', methods=['POST'])
def delete_product(product_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    execute_db("DELETE FROM product_images WHERE p_id = ?", [product_id])
    execute_db("DELETE FROM products WHERE p_id = ?", [product_id])
    flash(f'Product #{product_id} successfully deleted.', 'success')
    return redirect(url_for('admin.manage_products'))

@admin_bp.route('/admin/orders')
def manage_orders():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    
    # Fetch all orders with buyer and seller details
    # Using LEFT JOIN to ensure orders show even if items/products are missing
    orders = query_db("""
        SELECT o.*, u.u_name as buyer_name, sp.shop_name,
               (SELECT p_name FROM products p JOIN order_items oi ON p.p_id = oi.p_id WHERE oi.order_id = o.order_id LIMIT 1) as p_name,
               (SELECT pi.image_url FROM product_images pi JOIN order_items oi ON pi.p_id = oi.p_id WHERE oi.order_id = o.order_id LIMIT 1) as p_image,
               (SELECT COUNT(*) FROM order_items WHERE order_id = o.order_id) as item_count
        FROM orders o
        JOIN users u ON o.u_id = u.u_id
        LEFT JOIN seller_profiles sp ON o.seller_id = sp.u_id
        ORDER BY o.created_at DESC
    """)
    
    # Summary stats
    stats = {
        'total': len(orders),
        'active': len([o for o in orders if o['order_status'] not in ['Delivered', 'Cancelled']]),
        'completed': len([o for o in orders if o['order_status'] == 'Delivered']),
        'cancelled': len([o for o in orders if o['order_status'] == 'Cancelled']),
        'revenue': sum(o['total_amount'] for o in orders if o['total_amount'] is not None and o['order_status'] not in ['Delivered', 'Cancelled'])
    }
    
    return render_template('admin/orders.html', orders=orders, stats=stats)

@admin_bp.route('/admin/cancel_order/<int:order_id>', methods=['POST'])
def cancel_order(order_id):
    if not session.get('admin_logged_in'):
        return jsonify({'success': False, 'message': 'Unauthorized'}), 401
    
    execute_db("UPDATE orders SET order_status = 'Cancelled' WHERE order_id = ?", [order_id])
    flash(f'Order #{order_id} forcefully cancelled by Admin.', 'warning')
    return redirect(url_for('admin.manage_orders'))

@admin_bp.route('/admin/analytics')
def analytics():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    return render_template('admin/analytics.html')

@admin_bp.route('/admin/finance')
def finance():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    return render_template('admin/finance.html')

@admin_bp.route('/admin/learning')
def learning():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    return render_template('admin/learning.html')

@admin_bp.route('/admin/settings')
def settings():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin.login'))
    return render_template('admin/platformsetting.html')

@admin_bp.route('/admin/logout')
def logout():
    session.pop('admin_logged_in', None)
    logout_user() # Also clear flask-login session
    return redirect(url_for('admin.login'))
