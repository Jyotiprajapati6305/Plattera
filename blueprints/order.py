from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from db import query_db, execute_db

order_bp = Blueprint('order', __name__, url_prefix='/orders')


@order_bp.route('/')
@login_required
def order_history():
    orders = query_db('''
        SELECT o.order_id, o.total_amount, o.order_status,
               o.created_at,
               oi.quantity, oi.price,
               p.p_name as product_name,
               pi.image_url,
               sp.shop_name
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        WHERE o.u_id = ?
        ORDER BY o.created_at DESC
    ''', [current_user.u_id])

    return render_template('order/order_history.html', orders=orders)


@order_bp.route('/<int:order_id>')
@login_required
def order_detail(order_id):
    order = query_db('''
        SELECT o.order_id, o.total_amount, o.order_status,
               o.created_at, o.shipping_address, o.payment_method
        FROM orders o
        WHERE o.order_id = ? AND o.u_id = ?
    ''', [order_id, current_user.u_id], one=True)

    if not order:
        flash('Order not found.', 'error')
        return redirect(url_for('order.order_history'))

    items = query_db('''
        SELECT oi.quantity, oi.price,
               p.p_name as product_name, p.p_id,
               pi.image_url
        FROM order_items oi
        JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        WHERE oi.order_id = ?
    ''', [order_id])

    return render_template('order/order_detail.html', order=order, items=items)
