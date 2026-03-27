from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from db import query_db, execute_db

complaint_bp = Blueprint('complaint', __name__, url_prefix='/complaints')


@complaint_bp.route('/my-complaints')
@login_required
def my_complaints():
    complaints = query_db('''
        SELECT c.comp_id, c.complaint_text, c.complaint_status, c.created_at,
               o.order_number
        FROM complaints c
        LEFT JOIN orders o ON c.o_id = o.o_id
        WHERE c.u_id = ?
        ORDER BY c.created_at DESC
    ''', [current_user.u_id])

    return render_template('complaint/my_complaints.html', complaints=complaints)


@complaint_bp.route('/new', methods=['GET', 'POST'])
@login_required
def new_complaint():
    # Get user's orders for complaint selection
    user_orders = query_db('''
        SELECT o_id, order_number, created_at FROM orders
        WHERE buyer_id = ?
        ORDER BY created_at DESC
    ''', [current_user.u_id])

    if request.method == 'POST':
        order_id = request.form.get('order_id', type=int)
        complaint_text = request.form.get('complaint_text', '').strip()

        if not complaint_text:
            flash('Please describe your complaint.', 'error')
            return redirect(url_for('complaint.new_complaint'))

        execute_db('''
            INSERT INTO complaints (u_id, o_id, complaint_text, complaint_status, created_at)
            VALUES (?, ?, ?, 'open', datetime('now'))
        ''', [current_user.u_id, order_id, complaint_text])

        flash('Your complaint has been submitted.', 'success')
        return redirect(url_for('complaint.my_complaints'))

    return render_template('complaint/new_complaint.html', user_orders=user_orders)
