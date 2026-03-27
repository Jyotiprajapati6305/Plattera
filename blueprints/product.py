from flask import Blueprint, render_template, request, redirect, url_for, flash, session
from flask_login import login_required, current_user
from db import query_db, execute_db

product_bp = Blueprint('product', __name__)


@product_bp.route('/')
def home():
    # Fetch categories with product counts
    categories = query_db('''
        SELECT c.c_id, c.c_name as category_name, COUNT(p.p_id) as product_count
        FROM categories c
        LEFT JOIN products p ON c.c_id = p.c_id
        GROUP BY c.c_id
        ORDER BY c.c_name
    ''')

    # Fetch featured products (latest 6 products with images and rating)
    trending = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, p.p_description as description,
               pi.image_url,
               AVG(r.rating) AS avg_rating,
               COUNT(r.r_id) as review_count,
               sp.shop_name, sp.u_id as seller_id
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        LEFT JOIN reviews r ON p.p_id = r.p_id
        GROUP BY p.p_id
        ORDER BY avg_rating DESC, p.created_at DESC
        LIMIT 6
    ''')

    # Fetch artisans for "Meet the Makers" section
    artisans = query_db('''
        SELECT sp.u_id as seller_id, sp.shop_name, sp.shop_description,
               u.u_name
        FROM seller_profiles sp
        JOIN users u ON sp.u_id = u.u_id
        ORDER BY sp.sp_id DESC
        LIMIT 4
    ''')

    # Fetch occasion-based products
    valentine_products = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, pi.image_url, sp.shop_name, sp.u_id as seller_id
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        WHERE p.p_occasion = "Valentine's"
        GROUP BY p.p_id
        LIMIT 4
    ''')

    diwali_products = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, pi.image_url, sp.shop_name, sp.u_id as seller_id
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        WHERE p.p_occasion = "Diwali"
        GROUP BY p.p_id
        LIMIT 4
    ''')

    return render_template('product/home.html', 
                          categories=categories, 
                          trending=trending, 
                          artisans=artisans,
                          valentine_products=valentine_products,
                          diwali_products=diwali_products)


@product_bp.route('/shop')
def shop():
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category', type=int)
    seller_id = request.args.get('seller', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    sort = request.args.get('sort', 'newest')

    # Build query
    base_query = '''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, p.p_description as description,
               pi.image_url, sp.u_id as seller_id,
               AVG(r.rating) AS avg_rating,
               COUNT(r.r_id) as review_count,
               sp.shop_name, c.c_name as category_name
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        LEFT JOIN categories c ON p.c_id = c.c_id
        LEFT JOIN reviews r ON p.p_id = r.p_id
        WHERE 1=1
    '''
    args = []

    if q:
        base_query += ' AND (p.p_name LIKE ? OR p.p_description LIKE ?)'
        args += [f'%{q}%', f'%{q}%']

    if category_id:
        base_query += ' AND p.c_id = ?'
        args.append(category_id)

    if seller_id:
        base_query += ' AND p.seller_id = ?'
        args.append(seller_id)

    if min_price is not None:
        base_query += ' AND p.p_price >= ?'
        args.append(min_price)

    if max_price is not None:
        base_query += ' AND p.p_price <= ?'
        args.append(max_price)

    base_query += ' GROUP BY p.p_id'

    if sort == 'price_asc':
        base_query += ' ORDER BY p.p_price ASC'
    elif sort == 'price_desc':
        base_query += ' ORDER BY p.p_price DESC'
    elif sort == 'rating':
        base_query += ' ORDER BY avg_rating DESC'
    else:
        base_query += ' ORDER BY p.created_at DESC'

    products = query_db(base_query, args)
    
    categories = query_db('''
        SELECT c.c_id, c.c_name as category_name, COUNT(p.p_id) as product_count
        FROM categories c
        LEFT JOIN products p ON c.c_id = p.c_id
        GROUP BY c.c_id
        ORDER BY c.c_name
    ''')

    return render_template('product/shop.html',
                           products=products,
                           categories=categories,
                           current_q=q,
                           current_category=category_id,
                           current_seller=seller_id,
                           current_min_price=min_price,
                           current_max_price=max_price,
                           current_sort=sort)


@product_bp.route('/product/<int:product_id>')
def product_detail(product_id):
    product = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, p.p_description as description,
               p.p_stock as stock_qty, p.p_old_price, p.p_material, p.p_filling, 
               p.p_dimensions, p.p_weight, p.p_care, p.p_perfect_for,
               sp.shop_name, sp.u_id as seller_id,
               c.c_name as category_name
        FROM products p
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        LEFT JOIN categories c ON p.c_id = c.c_id
        WHERE p.p_id = ?
    ''', [product_id], one=True)

    if not product:
        flash('Product not found.', 'error')
        return redirect(url_for('product.shop'))

    images_raw = query_db('SELECT image_url FROM product_images WHERE p_id = ?', [product_id])
    images = []
    for img in images_raw:
        url = img['image_url']
        if not url.startswith('http'):
            url = url_for('static', filename='uploads/products/' + url.split('/')[-1])
        images.append({'image_url': url})

    reviews = query_db('''
        SELECT r.rating, r.comment as review_text, r.created_at,
               u.u_name
        FROM reviews r
        JOIN users u ON r.u_id = u.u_id
        WHERE r.p_id = ?
        ORDER BY r.created_at DESC
    ''', [product_id])

    # Calculate average rating
    rating_data = query_db('SELECT AVG(rating) as avg, COUNT(*) as count FROM reviews WHERE p_id = ?', [product_id], one=True)
    avg_rating = rating_data['avg'] if rating_data['avg'] else 0
    review_count = rating_data['count']

    # Related products (same category)
    related = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, pi.image_url, sp.u_id as seller_id
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        WHERE p.c_id = (SELECT c_id FROM products WHERE p_id = ?)
          AND p.p_id != ?
        GROUP BY p.p_id
        LIMIT 4
    ''', [product_id, product_id])

    # Fetch artisan details
    artisan = query_db('''
        SELECT sp.*, u.u_name, u.created_at as member_since
        FROM seller_profiles sp
        JOIN users u ON sp.u_id = u.u_id
        WHERE sp.u_id = ?
    ''', [product['seller_id']], one=True)

    # Fetch more from this artisan
    more_from_artisan = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, pi.image_url, sp.u_id as seller_id
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        WHERE p.seller_id = ? AND p.p_id != ?
        GROUP BY p.p_id
        LIMIT 4
    ''', [product['seller_id'], product_id])

    return render_template('product/product_detail.html',
                           product=product,
                           images=images,
                           reviews=reviews,
                           avg_rating=round(avg_rating, 1),
                           review_count=review_count,
                           related=related,
                           artisan=artisan,
                           more_from_artisan=more_from_artisan)


@product_bp.route('/about')
def about():
    return render_template('product/about.html')





@product_bp.route('/gallery')
def gallery():
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category', type=int)
    min_price = request.args.get('min_price', type=float)
    max_price = request.args.get('max_price', type=float)
    occasion = request.args.get('occasion', '').strip()
    sort = request.args.get('sort', 'newest')

    # Build query
    base_query = '''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price,
               pi.image_url, sp.shop_name, sp.u_id as seller_id, c.c_name as category_name,
               AVG(r.rating) AS avg_rating,
               COUNT(r.r_id) as review_count, p.p_occasion
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN seller_profiles sp ON p.seller_id = sp.u_id
        LEFT JOIN categories c ON p.c_id = c.c_id
        LEFT JOIN reviews r ON p.p_id = r.p_id
        WHERE 1=1
    '''
    args = []

    if q:
        base_query += ' AND (p.p_name LIKE ? OR p.p_description LIKE ?)'
        args += [f'%{q}%', f'%{q}%']

    if category_id:
        base_query += ' AND p.c_id = ?'
        args.append(category_id)

    if min_price is not None:
        base_query += ' AND p.p_price >= ?'
        args.append(min_price)

    if max_price is not None:
        base_query += ' AND p.p_price <= ?'
        args.append(max_price)

    if occasion:
        base_query += ' AND p.p_occasion = ?'
        args.append(occasion)

    base_query += ' GROUP BY p.p_id'

    if sort == 'price_asc':
        base_query += ' ORDER BY p.p_price ASC'
    elif sort == 'price_desc':
        base_query += ' ORDER BY p.p_price DESC'
    elif sort == 'rating':
        base_query += ' ORDER BY avg_rating DESC'
    else:
        base_query += ' ORDER BY p.created_at DESC'

    images = query_db(base_query, args)
    
    categories = query_db('''
        SELECT c.c_id, c.c_name as category_name, COUNT(p.p_id) as product_count
        FROM categories c
        LEFT JOIN products p ON c.c_id = p.c_id
        GROUP BY c.c_id
        ORDER BY c.c_name
    ''')

    return render_template('product/gallery.html', 
                           images=images, 
                           categories=categories,
                           current_q=q,
                           current_category=category_id,
                           current_min_price=min_price,
                           current_max_price=max_price,
                           current_sort=sort,
                           current_occasion=occasion)


@product_bp.route('/artisan/<int:seller_id>')
def artisan_profile(seller_id):
    # Fetch seller profile and user details
    artisan = query_db('''
        SELECT sp.*, u.u_name, u.created_at as member_since
        FROM seller_profiles sp
        JOIN users u ON sp.u_id = u.u_id
        WHERE sp.u_id = ?
    ''', [seller_id], one=True)

    if not artisan:
        flash('Artisan not found.', 'error')
        return redirect(url_for('product.home'))

    # Performance Snapshot stats
    stats = {}
    
    # 1. Total Products
    res = query_db('SELECT COUNT(*) as count FROM products WHERE seller_id = ?', [seller_id], one=True)
    stats['total_products'] = res['count'] if res else 0
    
    # 2. Orders Completed (Distinct order IDs containing this seller's products)
    res = query_db('''
        SELECT COUNT(DISTINCT oi.order_id) as count 
        FROM order_items oi
        JOIN products p ON oi.p_id = p.p_id
        WHERE p.seller_id = ?
    ''', [seller_id], one=True)
    stats['orders_completed'] = res['count'] if res else 0
    
    # 3. Average Rating and Total Reviews
    res = query_db('''
        SELECT AVG(r.rating) as avg_rating, COUNT(r.r_id) as count
        FROM reviews r
        JOIN products p ON r.p_id = p.p_id
        WHERE p.seller_id = ?
    ''', [seller_id], one=True)
    stats['avg_rating'] = round(res['avg_rating'], 1) if res and res['avg_rating'] else 0.0
    stats['review_count'] = res['count'] if res else 0

    # 4. Custom Orders - check if they have any requests (indicating they accept them)
    res = query_db('SELECT COUNT(*) as count FROM custom_requests WHERE seller_id = ?', [seller_id], one=True)
    stats['accepts_custom'] = 'Yes' if res and res['count'] > 0 else 'Yes' # Defaulting to Yes as most do

    # Best Sellers (Top 4 rated products)
    bestsellers = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, pi.image_url,
               AVG(r.rating) as avg_rating, COUNT(r.r_id) as review_count
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN reviews r ON p.p_id = r.p_id
        WHERE p.seller_id = ?
        GROUP BY p.p_id
        ORDER BY avg_rating DESC, review_count DESC
        LIMIT 4
    ''', [seller_id])

    # All Products
    all_products = query_db('''
        SELECT p.p_id, p.p_name as product_name, p.p_price as price, pi.image_url,
               AVG(r.rating) as avg_rating, COUNT(r.r_id) as review_count
        FROM products p
        LEFT JOIN product_images pi ON p.p_id = pi.p_id
        LEFT JOIN reviews r ON p.p_id = r.p_id
        WHERE p.seller_id = ?
        GROUP BY p.p_id
        ORDER BY p.created_at DESC
    ''', [seller_id])

    # Latest Reviews
    reviews = query_db('''
        SELECT r.rating, r.comment as review_text, r.created_at, u.u_name, p.p_name as product_name
        FROM reviews r
        JOIN users u ON r.u_id = u.u_id
        JOIN products p ON r.p_id = p.p_id
        WHERE p.seller_id = ?
        ORDER BY r.created_at DESC
        LIMIT 4
    ''', [seller_id])

    return render_template('product/artisan_profile.html',
                           artisan=artisan,
                           stats=stats,
                           bestsellers=bestsellers,
                           all_products=all_products,
                           reviews=reviews)
@product_bp.route('/product/<int:product_id>/review', methods=['POST'])
@login_required
def add_review(product_id):
    rating = request.form.get('rating', type=int)
    comment = request.form.get('comment', '').strip()

    if not rating or rating < 1 or rating > 5:
        flash('Invalid rating. Please select 1-5 stars.', 'error')
        return redirect(url_for('product.product_detail', product_id=product_id))

    if not comment:
        flash('Please provide a comment for your review.', 'error')
        return redirect(url_for('product.product_detail', product_id=product_id))

    # Check if user has already reviewed this product
    existing_review = query_db('SELECT r_id FROM reviews WHERE p_id = ? AND u_id = ?', [product_id, current_user.u_id], one=True)
    
    if existing_review:
        # Update existing review
        execute_db('UPDATE reviews SET rating = ?, comment = ? WHERE r_id = ?', [rating, comment, existing_review['r_id']])
        flash('Your review has been updated.', 'success')
    else:
        # Insert new review
        execute_db('INSERT INTO reviews (p_id, u_id, rating, comment) VALUES (?, ?, ?, ?)', 
                   [product_id, current_user.u_id, rating, comment])
        flash('Thank you for your review!', 'success')

    return redirect(url_for('product.product_detail', product_id=product_id))
