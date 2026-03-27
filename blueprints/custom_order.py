from flask import Blueprint, render_template, request, redirect, url_for, flash, current_app
from flask_login import login_required, current_user
from db import query_db, execute_db
from extensions import mail
from flask_mail import Message

custom_order_bp = Blueprint('custom_order', __name__, url_prefix='/custom-orders')


import os
from werkzeug.utils import secure_filename

UPLOAD_FOLDER = 'static/uploads/custom_requests'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

@custom_order_bp.route('/new', methods=['GET', 'POST'])
@custom_order_bp.route('/new/<int:seller_id>', methods=['GET', 'POST'])
@login_required
def new_request(seller_id=None):
    sellers = query_db('''
        SELECT sp.u_id as seller_id, sp.shop_name, u.first_name, u.last_name
        FROM seller_profiles sp
        JOIN users u ON sp.u_id = u.u_id
        ORDER BY sp.shop_name
    ''')
    
    categories = query_db('SELECT * FROM categories ORDER BY c_name')

    if request.method == 'POST':
        product_type = request.form.get('product_type')
        product_size = request.form.get('product_size')
        color_complexity = request.form.get('color_complexity')
        personalization = request.form.getlist('personalization')
        urgency = request.form.get('urgency')
        quantity = request.form.get('quantity', 1, type=int)
        estimated_price = request.form.get('estimated_price', type=float)
        seller_id = request.form.get('seller_id', type=int)
        custom_message = request.form.get('custom_message', '').strip()
        
        # Handle file upload
        filename = None
        if 'reference_image' in request.files:
            file = request.files['reference_image']
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(UPLOAD_FOLDER, filename))

        execute_db('''
            INSERT INTO custom_requests (
                u_id, seller_id, product_type, product_size, color_complexity, 
                personalization_details, custom_message, urgency, quantity, 
                estimated_price, reference_image, status, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', datetime('now'))
        ''', [
            current_user.u_id, seller_id, product_type, product_size, color_complexity,
            ", ".join(personalization), custom_message, urgency, quantity, estimated_price, filename
        ])

        # Send Email to Seller
        seller = query_db('SELECT u_email, shop_name FROM seller_profiles sp JOIN users u ON sp.u_id = u.u_id WHERE sp.u_id = ?', [seller_id], one=True)
        if seller:
            try:
                msg = Message(f"New Custom Order Request for {seller['shop_name']}",
                              recipients=[seller['u_email']])
                msg.body = f"""
Hello,

You have received a new custom order request from {current_user.first_name} {current_user.last_name}.

Product Type: {product_type}
Quantity: {quantity}
Estimated Price: ₹{estimated_price}
Details: {custom_message}

Please log in to your dashboard to review and confirm this request.

Best regards,
Plattera Team
"""
                mail.send(msg)
            except Exception as e:
                print(f"Error sending email to seller: {e}")
                flash('Request sent, but notification email to seller failed.', 'warning')

        flash('Your custom order request has been sent!', 'success')
        return redirect(url_for('custom_order.my_requests'))

    return render_template('custom_order/new_request.html', sellers=sellers, current_seller_id=seller_id, categories=categories)

@custom_order_bp.route('/process/<int:cr_id>', methods=['POST'])
@login_required
def process_request(cr_id):
    if current_user.u_role != 'seller':
        flash('Access denied.', 'error')
        return redirect(url_for('auth.login'))

    action = request.form.get('action') # 'accept' or 'reject'
    final_price = request.form.get('final_price', type=float)
    delivery_time = request.form.get('delivery_time')

    if action == 'accept':
        execute_db('''
            UPDATE custom_requests 
            SET status = 'accepted', final_price = ?, delivery_time = ? 
            WHERE cr_id = ? AND seller_id = ?
        ''', [final_price, delivery_time, cr_id, current_user.u_id])
        
        # Notify User
        req = query_db('SELECT u.u_email, u.first_name, cr.product_type FROM custom_requests cr JOIN users u ON cr.u_id = u.u_id WHERE cr.cr_id = ?', [cr_id], one=True)
        if req:
            try:
                subject = f"Your Custom Request for '{req['product_type']}' is Approved! 🎨"
                msg = Message(subject, recipients=[req['u_email']])
                msg.body = f"""Hello {req['first_name']},

Great news! Your custom order request for '{req['product_type']}' has been approved by the artisan.

--- ORDER DETAILS ---
Final Price: ₹{final_price}
Estimated Delivery: {delivery_time}
--------------------

Your custom order is now available in your cart. Please proceed with the payment to confirm your order and allow the artisan to begin crafting your unique piece.

Click here to view your cart and pay: http://127.0.0.1:5000/cart/

Best regards,
Plattera team"""
                mail.send(msg)
                flash('Request approved! The buyer has been notified via email to proceed with payment.', 'success')
            except Exception as e:
                print(f"Error sending acceptance email: {e}")
                flash('Status updated, but notification email failed. Please notify the buyer manually.', 'warning')
    else:
        execute_db("UPDATE custom_requests SET status = 'rejected' WHERE cr_id = ? AND seller_id = ?", [cr_id, current_user.u_id])
        
        # Notify User of Rejection
        req = query_db('SELECT u.u_email, u.first_name, cr.product_type FROM custom_requests cr JOIN users u ON cr.u_id = u.u_id WHERE cr.cr_id = ?', [cr_id], one=True)
        if req:
            try:
                subject = f"Update on your Custom Request: {req['product_type']}"
                msg = Message(subject, recipients=[req['u_email']])
                msg.body = f"""Hello {req['first_name']},

Thank you for your interest in a custom creation. After careful review, our artisan is unable to accept your custom request for '{req['product_type']}' at this time.

Don't worry! You can still explore our gallery for hundreds of beautiful ready-made items or try sending a request to another talented artisan on Plattera.

Best regards,
Plattera team"""
                mail.send(msg)
                flash('Request denied. The buyer has been notified.', 'info')
            except Exception as e:
                print(f"Error sending rejection email: {e}")
                flash('Status updated, but notification email failed.', 'warning')

    return redirect(url_for('seller.dashboard'))


@custom_order_bp.route('/my-requests')
@login_required
def my_requests():
    requests_list = query_db('''
        SELECT cr.cr_id, cr.product_type, cr.estimated_price, cr.status as request_status, 
               cr.created_at, cr.personalization_details, cr.custom_message,
               cr.product_size, cr.color_complexity, cr.urgency, cr.quantity,
               cr.final_price, cr.delivery_time,
               sp.shop_name, u.first_name || ' ' || u.last_name as seller_name, u.phone_number as seller_phone
        FROM custom_requests cr
        JOIN seller_profiles sp ON cr.seller_id = sp.u_id
        JOIN users u ON sp.u_id = u.u_id
        WHERE cr.u_id = ?
        ORDER BY cr.created_at DESC
    ''', [current_user.u_id])

    return render_template('custom_order/my_requests.html', requests=requests_list)
