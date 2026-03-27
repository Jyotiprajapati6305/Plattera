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
               COALESCE(p.p_name, oi.product_name) as product_name,
               COALESCE((SELECT image_url FROM product_images WHERE p_id = p.p_id LIMIT 1), cr.reference_image) as image_url,
               sp.shop_name
        FROM orders o
        JOIN order_items oi ON o.order_id = oi.order_id
        LEFT JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN custom_requests cr ON oi.custom_request_id = cr.cr_id
        LEFT JOIN seller_profiles sp ON COALESCE(p.seller_id, cr.seller_id) = sp.u_id
        WHERE o.u_id = ?
        GROUP BY oi.oi_id
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
               COALESCE(p.p_name, oi.product_name) as product_name, p.p_id,
               COALESCE((SELECT image_url FROM product_images WHERE p_id = p.p_id LIMIT 1), cr.reference_image) as image_url
        FROM order_items oi
        LEFT JOIN products p ON oi.p_id = p.p_id
        LEFT JOIN custom_requests cr ON oi.custom_request_id = cr.cr_id
        WHERE oi.order_id = ?
    ''', [order_id])

    return render_template('order/order_detail.html', order=order, items=items)
