from flask import Blueprint, render_template, redirect, url_for, flash, request, current_app
from flask_login import login_required, current_user
from werkzeug.utils import secure_filename
import os
from db import query_db, execute_db
from functools import wraps

seller_bp = Blueprint('seller', __name__, url_prefix='/seller')

def seller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated or current_user.u_role != 'seller':
            flash('Access denied. Seller account required.', 'error')
            return redirect(url_for('auth.login'))
        return f(*args, **kwargs)
    return decorated_function

def seed_dummy_seller_data(sid):
    # Check if they have products
    count = query_db('SELECT COUNT(*) as count FROM products WHERE seller_id = ?', [sid], one=True)
    if count and count['count'] == 0:
        buyer = query_db("SELECT u_id FROM users WHERE u_role = 'buyer' LIMIT 1", one=True)
        buyer_id = buyer['u_id'] if buyer else sid
        
        # Insert Products
        # pid1 = execute_db("INSERT INTO products (seller_id, c_id, p_name, p_desc, p_price, p_stock, created_at) VALUES (?, 1, 'Cozy Winter Scarf', 'Warm and fuzzy handmade scarf.', 1500, 10, datetime('now'))", [sid])
        # execute_db("INSERT INTO product_images (p_id, image_url) VALUES (?, 'winter-cardigen.jpg')", [pid1])
        
        # pid2 = execute_db("INSERT INTO products (seller_id, c_id, p_name, p_desc, p_price, p_stock, created_at) VALUES (?, 2, 'Boho Chic Tote Bag', 'Large crochet tote perfect for everyday use.', 1200, 5, datetime('now'))", [sid])
        # execute_db("INSERT INTO product_images (p_id, image_url) VALUES (?, 'totebag.jpg')", [pid2])
        
        # Insert Orders
        # order_id = execute_db("INSERT INTO orders (u_id, seller_id, total_amount, order_status, shipping_address, payment_method, created_at) VALUES (?, ?, 2700, 'processing', '123 Handcraft Lane, Crochet City', 'COD', datetime('now', '-2 days'))", [buyer_id, sid])
        
        # execute_db("INSERT INTO order_items (order_id, p_id, product_name, price, quantity) VALUES (?, ?, 'Cozy Winter Scarf', 1500, 1)", [order_id, pid1])
        # execute_db("INSERT INTO order_items (order_id, p_id, product_name, price, quantity) VALUES (?, ?, 'Boho Chic Tote Bag', 1200, 1)", [order_id, pid2])
        
        # Insert a Custom Request
        # execute_db("INSERT INTO custom_requests (u_id, seller_id, product_type, product_size, color_complexity, personalization_details, custom_message, estimated_price, status, urgency, quantity, created_at) VALUES (?, ?, 'Amigurumi Doll', '350', '250', 'Embroidery', 'A cute little bear with a red scarf.', 1500, 'pending', 'standard', 1, datetime('now', '-1 days'))", [buyer_id, sid])
        
        # Insert a Review
        # execute_db("INSERT INTO reviews (u_id, p_id, rating, comment, created_at) VALUES (?, ?, 5, 'Absolutely love this! The quality is amazing and it feels so well made.', datetime('now', '-12 hours'))", [buyer_id, pid1])

@seller_bp.route('/dashboard')
@login_required
@seller_required
def dashboard():
    sid = current_user.u_id
    
    # Auto-seed some data if the seller is brand new so the dashboard isn't completely empty
    seed_dummy_seller_data(sid)
    
    # Seller Profile
    profile = query_db('SELECT * FROM seller_profiles WHERE u_id = ?', [sid], one=True)
    
    # 1. Total Revenue (Excluding cancelled)
    # Revenue from regular products
    revenue_data = query_db('''
        SELECT SUM(oi.price * oi.quantity) as revenue
        FROM order_items oi
        JOIN products p ON oi.p_id = p.p_id
        JOIN orders o ON oi.order_id = o.order_id
        WHERE p.seller_id = ? AND o.order_status != "cancelled"
    ''', [sid], one=True)
    
    # Revenue from custom requests
    custom_revenue_data = query_db('''
        SELECT SUM(oi.price * oi.quantity) as cr_rev
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN custom_requests cr ON oi.custom_request_id = cr.cr_id
        WHERE cr.seller_id = ? AND o.order_status != "cancelled" AND oi.is_custom = 1
    ''', [sid], one=True)

    reg_rev = (revenue_data['revenue'] if revenue_data and revenue_data['revenue'] else 0)
    cr_rev = (custom_revenue_data['cr_rev'] if custom_revenue_data and custom_revenue_data['cr_rev'] else 0)
    total_revenue = reg_rev + cr_rev
    
    # 2. Total Orders (Distinct)
    orders_count_data = query_db('''
        SELECT COUNT(DISTINCT o.order_id) as total_orders
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN custom_requests cr ON oi.custom_request_id = cr.cr_id
        WHERE p.seller_id = ? OR cr.seller_id = ?
    ''', [sid, sid], one=True)
    total_orders = orders_count_data['total_orders'] if orders_count_data else 0
    
    # 3. Custom Orders (Pending)
    custom_data = query_db('''
        SELECT COUNT(*) as pending_count
        FROM custom_requests
        WHERE seller_id = ? AND status = "pending"
    ''', [sid], one=True)
    pending_custom = custom_data['pending_count'] if custom_data else 0
    
    # 4. Recent Orders (Both products and custom)
    recent_orders = query_db('''
        SELECT o.order_id, u.u_name as buyer_name, 
               COALESCE(p.p_name, oi.product_name) as display_name, 
               oi.quantity,
               (oi.price * oi.quantity) as amount, o.order_status, o.created_at,
               sp.shop_name as seller_name, oi.is_custom
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN users u ON o.u_id = u.u_id
        LEFT JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN custom_requests cr ON oi.custom_request_id = cr.cr_id
        LEFT JOIN seller_profiles sp ON o.seller_id = sp.u_id
        WHERE p.seller_id = ? OR cr.seller_id = ?
        ORDER BY o.created_at DESC
        LIMIT 10
    ''', [sid, sid])
    
    # 5. Top Products
    top_products = query_db('''
        SELECT p.p_id, p.p_name, SUM(oi.quantity) as sold_count, 
               SUM(oi.price * oi.quantity) as revenue, pi.image_url
        FROM order_items oi
        JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        WHERE p.seller_id = ?
        GROUP BY p.p_id
        ORDER BY sold_count DESC
        LIMIT 5
    ''', [sid])
    
    # 6. Low Stock Alerts
    low_stock = query_db('''
        SELECT p_name, p_stock FROM products 
        WHERE seller_id = ? AND p_stock <= 5
        ORDER BY p_stock ASC
    ''', [sid])
    
    # 7. Recent Reviews
    recent_reviews = query_db('''
        SELECT r.rating, r.comment, u.u_name as reviewer_name, p.p_name as product_name, r.created_at
        FROM reviews r
        JOIN products p ON r.p_id = p.p_id
        JOIN users u ON r.u_id = u.u_id
        WHERE p.seller_id = ?
        ORDER BY r.created_at DESC
        LIMIT 3
    ''', [sid])
    
    # 9. Custom Requests
    custom_requests = query_db('''
        SELECT cr.cr_id, cr.product_type, cr.quantity, cr.estimated_price, cr.status, 
               cr.created_at, u.u_name as buyer_name, cr.custom_message, cr.personalization_details
        FROM custom_requests cr
        JOIN users u ON cr.u_id = u.u_id
        WHERE cr.seller_id = ?
        ORDER BY cr.created_at DESC
    ''', [sid])
    
    return render_template('seller/dashboard.html',
        profile=profile,
        total_revenue=total_revenue,
        total_orders=total_orders,
        pending_custom=pending_custom,
        recent_orders=recent_orders,
        top_products=top_products,
        low_stock=low_stock,
        recent_reviews=recent_reviews,
        custom_requests=custom_requests
    )
@seller_bp.route('/inventory')
@login_required
@seller_required
def inventory():
    sid = current_user.u_id
    
    # Auto-seed some data if the seller is brand new
    seed_dummy_seller_data(sid)
    
    products = query_db('''
        SELECT p.*, c.c_name, (SELECT image_url FROM product_images WHERE p_id = p.p_id LIMIT 1) as main_image
        FROM products p
        LEFT JOIN categories c ON p.c_id = c.c_id
        WHERE p.seller_id = ?
        ORDER BY p.created_at DESC
    ''', [sid])
    return render_template('seller/inventory.html', products=products)

@seller_bp.route('/orders')
@login_required
@seller_required
def orders():
    sid = current_user.u_id
    all_orders = query_db('''
        SELECT o.order_id, u.u_name as buyer_name, 
               COALESCE(p.p_name, oi.product_name) as p_name, 
               oi.quantity, (oi.price * oi.quantity) as amount, 
               o.order_status, o.created_at, sp.shop_name as seller_name,
               (SELECT image_url FROM product_images WHERE p_id = p.p_id LIMIT 1) as p_image,
               oi.is_custom
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN users u ON o.u_id = u.u_id
        LEFT JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN custom_requests cr ON oi.custom_request_id = cr.cr_id
        LEFT JOIN seller_profiles sp ON o.seller_id = sp.u_id
        WHERE p.seller_id = ? OR cr.seller_id = ?
        ORDER BY o.created_at DESC
    ''', [sid, sid])
    return render_template('seller/orders.html', orders=all_orders)

@seller_bp.route('/earnings')
@login_required
@seller_required
def earnings():
    sid = current_user.u_id
    # Monthly earnings summary (Simplified)
    monthly_data = query_db('''
        SELECT STRFTIME('%Y-%m', o.created_at) as month, SUM(oi.price * oi.quantity) as revenue
        FROM order_items oi
        JOIN orders o ON oi.order_id = o.order_id
        JOIN products p ON oi.p_id = p.p_id
        WHERE p.seller_id = ? AND o.order_status != 'cancelled'
        GROUP BY month
        ORDER BY month DESC
    ''', [sid])
    return render_template('seller/earnings.html', monthly_data=monthly_data)

@seller_bp.route('/learning')
@login_required
@seller_required
def learning():
    return render_template('seller/learning.html')

@seller_bp.route('/settings', methods=['GET', 'POST'])
@login_required
@seller_required
def settings():
    sid = current_user.u_id
    if request.method == 'POST':
        shop_name = request.form.get('shop_name')
        bio = request.form.get('bio')
        address = request.form.get('address')
        
        execute_db('''
            UPDATE seller_profiles 
            SET shop_name = ?, seller_bio = ?, workshop_address = ?
            WHERE u_id = ?
        ''', [shop_name, bio, address, sid])
        flash('Shop profile updated successfully!', 'success')
        return redirect(url_for('seller.settings'))
        
    profile = query_db('SELECT * FROM seller_profiles WHERE u_id = ?', [sid], one=True)
    return render_template('seller/settings.html', profile=profile)

@seller_bp.route('/product/add', methods=['GET', 'POST'])
@login_required
@seller_required
def add_product():
    if request.method == 'POST':
        name = request.form.get('name')
        price = float(request.form.get('price', 0))
        stock = int(request.form.get('stock', 0))
        description = request.form.get('description')
        cid = request.form.get('category')
        occasion = request.form.get('occasion')
        
        # Insert product
        product_id = execute_db('''
            INSERT INTO products (p_name, p_price, p_stock, p_description, c_id, seller_id, p_occasion)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', [name, price, stock, description, cid, current_user.u_id, occasion])
        
        # Handle images
        if 'product_images' in request.files:
            files = request.files.getlist('product_images')
            upload_folder = os.path.join('static', 'uploads', 'products')
            if not os.path.exists(upload_folder):
                os.makedirs(upload_folder)
                
            for file in files:
                if file and file.filename:
                    filename = secure_filename(f"{product_id}_{file.filename}")
                    file_path = os.path.join(upload_folder, filename)
                    file.save(file_path)
                    
                    # Store in DB
                    db_path = f"static/uploads/products/{filename}"
                    execute_db('INSERT INTO product_images (p_id, image_url) VALUES (?, ?)', [product_id, db_path])

        flash('Product added successfully!', 'success')
        return redirect(url_for('seller.inventory'))
        
    categories = query_db('SELECT * FROM categories')
    return render_template('seller/add_product.html', categories=categories)

@seller_bp.route('/product/edit/<int:pid>', methods=['GET', 'POST'])
@login_required
@seller_required
def edit_product(pid):
    # Verify ownership
    prod = query_db('SELECT * FROM products WHERE p_id = ? AND seller_id = ?', [pid, current_user.u_id], one=True)
    if not prod:
        flash('Permission denied.', 'error')
        return redirect(url_for('seller.inventory'))
        
    if request.method == 'POST':
        name = request.form.get('name')
        price = float(request.form.get('price', 0))
        stock = int(request.form.get('stock', 0))
        description = request.form.get('description')
        cid = request.form.get('category')
        occasion = request.form.get('occasion')
        
        execute_db('''
            UPDATE products 
            SET p_name = ?, p_price = ?, p_stock = ?, p_description = ?, c_id = ?, p_occasion = ?
            WHERE p_id = ?
        ''', [name, price, stock, description, cid, occasion, pid])
        
        # Handle images
        if 'product_images' in request.files:
            files = request.files.getlist('product_images')
            # Check if any valid file was submitted
            valid_files = [f for f in files if f and f.filename]
            if valid_files:
                upload_folder = os.path.join('static', 'uploads', 'products')
                if not os.path.exists(upload_folder):
                    os.makedirs(upload_folder)
                    
                execute_db('DELETE FROM product_images WHERE p_id = ?', [pid])
                
                for file in valid_files:
                    filename = secure_filename(f"{pid}_{file.filename}")
                    file_path = os.path.join(upload_folder, filename)
                    file.save(file_path)
                    
                    # Store in DB
                    db_path = f"static/uploads/products/{filename}"
                    execute_db('INSERT INTO product_images (p_id, image_url) VALUES (?, ?)', [pid, db_path])
                    
        flash('Product updated successfully!', 'success')
        return redirect(url_for('seller.inventory'))
        
    categories = query_db('SELECT * FROM categories')
    return render_template('seller/edit_product.html', product=prod, categories=categories)

@seller_bp.route('/product/delete/<int:pid>')
@login_required
@seller_required
def delete_product(pid):
    # Verify ownership
    prod = query_db('SELECT * FROM products WHERE p_id = ? AND seller_id = ?', [pid, current_user.u_id], one=True)
    if prod:
        execute_db('DELETE FROM products WHERE p_id = ?', [pid])
        flash('Product deleted successfully.', 'success')
    else:
        flash('Permission denied.', 'error')
    return redirect(url_for('seller.inventory'))
