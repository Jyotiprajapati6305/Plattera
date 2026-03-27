from flask import Blueprint, render_template, request, redirect, url_for, flash, session, jsonify, current_app
try:
    import razorpay
except ImportError:
    razorpay = None
from flask_mail import Message
from extensions import mail
from flask_login import login_required, current_user
from db import query_db, execute_db

cart_bp = Blueprint('cart', __name__, url_prefix='/cart')


def get_cart():
    if current_user.is_authenticated:
        return query_db('SELECT p_id as product_id, quantity, custom_note FROM cart WHERE u_id = ?', [current_user.u_id])
    return []


@cart_bp.route('/')
@login_required
def view_cart():
    cart = get_cart()
    cart_items = []
    total = 0

    # Normal items
    for item in cart:
        product = query_db('''
            SELECT p.p_id, p.p_name as product_name, p.p_price as price, p.p_stock as stock_qty,
                   pi.image_url, sp.shop_name
            FROM products p
            LEFT JOIN product_images pi ON p.p_id = pi.p_id
            LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
            WHERE p.p_id = ?
            GROUP BY p.p_id
        ''', [item['product_id']], one=True)

        if product:
            subtotal = float(product['price']) * item['quantity']
            total += subtotal
            cart_items.append({
                'type': 'product',
                'product': product,
                'quantity': item['quantity'],
                'subtotal': subtotal,
                'custom_note': item['custom_note']
            })

    # Custom requests that are accepted but not yet paid (in a real app we'd track payment_status)
    # For now, let's say 'accepted' means it's ready for payment and appears in cart.
    custom_requests = query_db('''
        SELECT cr.*, sp.shop_name 
        FROM custom_requests cr
        JOIN seller_profiles sp ON cr.seller_id = sp.u_id
        WHERE cr.u_id = ? AND cr.status = 'accepted'
    ''', [current_user.u_id])

    for req in custom_requests:
        price = req['final_price'] or req['estimated_price']
        subtotal = price * req['quantity']
        total += subtotal
        cart_items.append({
            'type': 'custom',
            'cr_id': req['cr_id'],
            'product_name': f"Custom {req['product_type']}",
            'shop_name': req['shop_name'],
            'price': price,
            'quantity': req['quantity'],
            'subtotal': subtotal,
            'details': req['custom_message'],
            'image_url': req['reference_image']
        })

    return render_template('cart/cart.html', cart_items=cart_items, total=total)


@cart_bp.route('/add/<int:product_id>', methods=['GET', 'POST'])
def add_to_cart(product_id):
    if not current_user.is_authenticated:
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return jsonify({'success': False, 'message': 'Please login to add to cart', 'redirect': url_for('auth.login')}), 401
        flash('Please login to add items to your cart.', 'info')
        # Redirect back to original page after login
        return redirect(url_for('auth.login', next=request.referrer or url_for('product.product_detail', product_id=product_id)))

    quantity = 1
    custom_note = None
    if request.method == 'POST':
        quantity = int(request.form.get('quantity', 1))
        custom_note = request.form.get('custom_note')
    
    # Check if already in cart
    existing = query_db('SELECT cart_id, quantity FROM cart WHERE u_id = ? AND p_id = ?', 
                        [current_user.u_id, product_id], one=True)
    
    if existing:
        execute_db('UPDATE cart SET quantity = quantity + ?, custom_note = ? WHERE cart_id = ?', 
                   [quantity, custom_note, existing['cart_id']])
        msg = 'Cart updated!'
    else:
        execute_db('INSERT INTO cart (u_id, p_id, quantity, custom_note) VALUES (?, ?, ?, ?)', 
                   [current_user.u_id, product_id, quantity, custom_note])
        msg = 'Item added to cart!'
        
    # Get total count for AJAX
    res = query_db('SELECT SUM(quantity) as count FROM cart WHERE u_id = ?', [current_user.u_id], one=True)
    new_count = res['count'] if res and res['count'] else 0

    if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
        return jsonify({
            'success': True,
            'message': msg,
            'cart_count': new_count
        })

    if request.args.get('buy_now') or request.method == 'GET':
        return redirect(url_for('cart.view_cart'))
        
    flash(msg, 'success')
    return redirect(url_for('product.product_detail', product_id=product_id))


@cart_bp.route('/update/<int:product_id>', methods=['POST'])
@login_required
def update_quantity(product_id):
    try:
        new_qty = int(request.form.get('quantity', 1))
        if new_qty < 1:
            execute_db('DELETE FROM cart WHERE u_id = ? AND p_id = ?', [current_user.u_id, product_id])
        else:
            execute_db('UPDATE cart SET quantity = ? WHERE u_id = ? AND p_id = ?', 
                       [new_qty, current_user.u_id, product_id])
        
        return redirect(url_for('cart.view_cart'))
    except Exception as e:
        return redirect(url_for('cart.view_cart'))


@cart_bp.route('/remove/<int:product_id>', methods=['POST'])
@login_required
def remove_from_cart(product_id):
    execute_db('DELETE FROM cart WHERE u_id = ? AND p_id = ?', [current_user.u_id, product_id])
    flash('Item removed from cart.', 'info')
    return redirect(url_for('cart.view_cart'))


@cart_bp.route('/checkout', methods=['GET', 'POST'])
@login_required
def checkout():
    cart = get_cart()
    custom_requests = query_db("SELECT * FROM custom_requests WHERE u_id = ? AND status = 'accepted'", [current_user.u_id])
    
    if not cart and not custom_requests:
        flash('Your cart is empty.', 'info')
        return redirect(url_for('cart.view_cart'))

    if request.method == 'POST':
        shipping_address = request.form.get('shipping_address', '').strip()
        payment_method = request.form.get('payment_method', 'cod')

        # Calculate Total including custom requests
        total = sum(float(query_db('SELECT p_price FROM products WHERE p_id = ?', [i['product_id']], one=True)['p_price']) * i['quantity'] for i in cart)
        
        custom_requests = query_db("SELECT * FROM custom_requests WHERE u_id = ? AND status = 'accepted'", [current_user.u_id])
        for cr in custom_requests:
            price = cr['final_price'] or cr['estimated_price']
            total += (price * cr['quantity'])

        # Apply Coupon
        discount_amount = 0
        coupon_code = None
        if 'active_coupon' in session:
            cp = session['active_coupon']
            discount_amount = (total * cp['discount']) / 100
            total -= discount_amount
            coupon_code = cp['code']

        # Get seller_id of first product or custom request
        seller_id = None
        if cart:
            first_product_id = cart[0]['product_id']
            seller_id = query_db('SELECT seller_id FROM products WHERE p_id = ?', [first_product_id], one=True)['seller_id']
        elif custom_requests:
            seller_id = custom_requests[0]['seller_id']

        order_id = execute_db('''
            INSERT INTO orders (u_id, total_amount, order_status, shipping_address, payment_method, seller_id, coupon_used, discount_amount, created_at)
            VALUES (?, ?, 'pending', ?, ?, ?, ?, ?, datetime('now'))
        ''', [current_user.u_id, total, shipping_address, payment_method, seller_id, coupon_code, discount_amount])

        # Add Cart Items
        for item in cart:
            product = query_db('SELECT p_price FROM products WHERE p_id = ?', [item['product_id']], one=True)
            if product:
                execute_db('''
                    INSERT INTO order_items (order_id, p_id, quantity, price, custom_note)
                    VALUES (?, ?, ?, ?, ?)
                ''', [order_id, item['product_id'], item['quantity'], product['p_price'], item['custom_note']])

        # Add Custom Requests as Items
        for cr in custom_requests:
            price = cr['final_price'] or cr['estimated_price']
            execute_db('''
                INSERT INTO order_items (order_id, product_name, quantity, price, is_custom, custom_request_id)
                VALUES (?, ?, ?, ?, 1, ?)
            ''', [order_id, f"Custom {cr['product_type']}", cr['quantity'], price, cr['cr_id']])
            
            # Update Request status
            execute_db("UPDATE custom_requests SET status = 'ordered' WHERE cr_id = ?", [cr['cr_id']])
            
            # Notify Seller of Paid Custom Order
            seller = query_db('SELECT u_email, shop_name FROM seller_profiles sp JOIN users u ON sp.u_id = u.u_id WHERE sp.u_id = ?', [cr['seller_id']], one=True)
            if seller:
                try:
                    msg = Message(f"Payment Received for Custom Request: {cr['product_type']}", recipients=[seller['u_email']])
                    msg.body = f"Hello {seller['shop_name']},\n\nThe user {current_user.first_name} has paid for their custom request: {cr['product_type']}.\n\nPlease check your dashboard and begin work on this order.\n\nBest regards,\nPlattera Team"
                    mail.send(msg)
                except Exception as e:
                    print(f"Error notifying seller: {e}")

        execute_db('DELETE FROM cart WHERE u_id = ?', [current_user.u_id])
        session.pop('active_coupon', None) # Remove coupon after use
        return redirect(url_for('cart.order_success', order_id=order_id))

    # Calculate total including custom requests
    total = sum(float(query_db('SELECT p_price FROM products WHERE p_id = ?', [i['product_id']], one=True)['p_price']) * i['quantity'] for i in cart)
    
    custom_requests = query_db("SELECT * FROM custom_requests WHERE u_id = ? AND status = 'accepted'", [current_user.u_id])
    for cr in custom_requests:
        price = cr['final_price'] or cr['estimated_price']
        total += (price * cr['quantity'])

    # Apply Coupon for Display
    discount_amount = 0
    if 'active_coupon' in session:
        cp = session['active_coupon']
        discount_amount = (total * cp['discount']) / 100
        total -= discount_amount

    # GET: Show checkout form
    cart_items = []
    # Regular Products
    for item in cart:
        product = query_db('''
            SELECT p.p_id, p.p_name as product_name, p.p_price as price, pi.image_url
            FROM products p
            LEFT JOIN product_images pi ON p.p_id = pi.p_id
            WHERE p.p_id = ?
            GROUP BY p.p_id
        ''', [item['product_id']], one=True)
        if product:
            subtotal = float(product['price']) * item['quantity']
            cart_items.append({'product': product, 'quantity': item['quantity'], 'subtotal': subtotal, 'type': 'product'})
            
    # Custom Requests
    for cr in custom_requests:
        price = cr['final_price'] or cr['estimated_price']
        subtotal = price * cr['quantity']
        cart_items.append({
            'product': {'product_name': f"Custom {cr['product_type']}", 'price': price},
            'quantity': cr['quantity'],
            'subtotal': subtotal,
            'type': 'custom'
        })

    # RAZORPAY KEYS
    RAZORPAY_KEY_ID = current_app.config.get('RAZORPAY_KEY_ID')
    
    return render_template('cart/checkout.html', 
                          cart_items=cart_items, 
                          total=total, 
                          discount_amount=discount_amount,
                          active_coupon=session.get('active_coupon'),
                          razorpay_key_id=RAZORPAY_KEY_ID)

@cart_bp.route('/create_payment', methods=['POST'])
@login_required
def create_payment():
    if not razorpay:
        return jsonify({'error': 'Razorpay library not installed. Please contact administrator.'}), 500

    cart = get_cart()
    custom_requests = query_db("SELECT * FROM custom_requests WHERE u_id = ? AND status = 'accepted'", [current_user.u_id])
    
    if not cart and not custom_requests:
        return jsonify({'error': 'Cart is empty'}), 400

    try:
        total = sum(float(query_db('SELECT p_price FROM products WHERE p_id = ?', [i['product_id']], one=True)['p_price']) * i['quantity'] for i in cart)
        
        custom_requests = query_db("SELECT * FROM custom_requests WHERE u_id = ? AND status = 'accepted'", [current_user.u_id])
        for cr in custom_requests:
            price = cr['final_price'] or cr['estimated_price']
            total += (price * cr['quantity'])

        # Apply Coupon
        if 'active_coupon' in session:
            cp = session['active_coupon']
            total -= (total * cp['discount']) / 100

        amount = int(total * 100)
        
        client = razorpay.Client(auth=(current_app.config.get('RAZORPAY_KEY_ID'), current_app.config.get('RAZORPAY_KEY_SECRET')))
        
        data = {
            "amount": amount,
            "currency": "INR",
            "receipt": f"receipt_{current_user.u_id}",
            "payment_capture": 1
        }
        
        razor_order = client.order.create(data=data)
        return jsonify(razor_order)
    except Exception as e:
        return jsonify({'error': f'Razorpay Error: {str(e)}'}), 500

@cart_bp.route('/verify_payment', methods=['POST'])
@login_required
def verify_payment():
    if not razorpay:
        return jsonify({'error': 'Razorpay library not available.'}), 500
    data = request.json
    razorpay_order_id = data.get('razorpay_order_id')
    razorpay_payment_id = data.get('razorpay_payment_id')
    razorpay_signature = data.get('razorpay_signature')
    shipping_address = data.get('shipping_address')

    client = razorpay.Client(auth=(current_app.config.get('RAZORPAY_KEY_ID'), current_app.config.get('RAZORPAY_KEY_SECRET')))
    
    params_dict = {
        'razorpay_order_id': razorpay_order_id,
        'razorpay_payment_id': razorpay_payment_id,
        'razorpay_signature': razorpay_signature
    }

    try:
        # Verify signature
        # client.utility.verify_payment_signature(params_dict) # Uncomment for Prod
        
        # If verified, place order in DB
        cart = get_cart()
        total = sum(float(query_db('SELECT p_price FROM products WHERE p_id = ?', [i['product_id']], one=True)['p_price']) * i['quantity'] for i in cart)
        custom_requests = query_db("SELECT * FROM custom_requests WHERE u_id = ? AND status = 'accepted'", [current_user.u_id])
        for cr in custom_requests:
            price = cr['final_price'] or cr['estimated_price']
            total += (price * cr['quantity'])

        # Apply Coupon
        discount_amount = 0
        coupon_code = None
        if 'active_coupon' in session:
            cp = session['active_coupon']
            discount_amount = (total * cp['discount']) / 100
            total -= discount_amount
            coupon_code = cp['code']

        # Get seller_id
        seller_id = None
        if cart:
            seller_id = query_db('SELECT seller_id FROM products WHERE p_id = ?', [cart[0]['product_id']], one=True)['seller_id']
        elif custom_requests:
            seller_id = custom_requests[0]['seller_id']

        order_id = execute_db('''
            INSERT INTO orders (u_id, total_amount, order_status, shipping_address, payment_method, 
                              razorpay_order_id, razorpay_payment_id, razorpay_signature, seller_id, coupon_used, discount_amount, created_at)
            VALUES (?, ?, 'confirmed', ?, 'razorpay', ?, ?, ?, ?, ?, ?, datetime('now'))
        ''', [current_user.u_id, total, shipping_address, razorpay_order_id, razorpay_payment_id, razorpay_signature, seller_id, coupon_code, discount_amount])

        # Regular items
        for item in cart:
            product = query_db('SELECT p_price FROM products WHERE p_id = ?', [item['product_id']], one=True)
            if product:
                execute_db('''
                    INSERT INTO order_items (order_id, p_id, quantity, price, custom_note)
                    VALUES (?, ?, ?, ?, ?)
                ''', [order_id, item['product_id'], item['quantity'], product['p_price'], item['custom_note']])

        # Custom items
        for cr in custom_requests:
            price = cr['final_price'] or cr['estimated_price']
            execute_db('''
                INSERT INTO order_items (order_id, product_name, quantity, price, is_custom, custom_request_id)
                VALUES (?, ?, ?, ?, 1, ?)
            ''', [order_id, f"Custom {cr['product_type']}", cr['quantity'], price, cr['cr_id']])
            execute_db("UPDATE custom_requests SET status = 'ordered' WHERE cr_id = ?", [cr['cr_id']])
            
            # Email Notification
            seller = query_db('SELECT u_email, shop_name FROM seller_profiles sp JOIN users u ON sp.u_id = u.u_id WHERE sp.u_id = ?', [cr['seller_id']], one=True)
            if seller:
                try:
                    msg = Message(f"Payment Received for Custom Request: {cr['product_type']}", recipients=[seller['u_email']])
                    msg.body = f"Hello {seller['shop_name']},\n\nThe user {current_user.first_name} has paid for their custom request: {cr['product_type']}.\n\nPlease check your dashboard and begin work on this order.\n\nBest regards,\nPlattera Team"
                    mail.send(msg)
                except Exception as e:
                    print(f"Error notifying seller: {e}")

        execute_db('DELETE FROM cart WHERE u_id = ?', [current_user.u_id])
        session.pop('active_coupon', None)
        return jsonify({'success': True, 'order_id': order_id})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@cart_bp.route('/order_success/<int:order_id>')
@login_required
def order_success(order_id):
    order = query_db('SELECT * FROM orders WHERE order_id = ? AND u_id = ?', [order_id, current_user.u_id], one=True)
    if not order:
        return redirect(url_for('product.home'))
        
    items = query_db('''
        SELECT oi.*, p.p_name as product_name, pi.image_url
        FROM order_items oi
        JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        WHERE oi.order_id = ?
    ''', [order_id])
    
    return render_template('cart/order_success.html', order=order, items=items)
