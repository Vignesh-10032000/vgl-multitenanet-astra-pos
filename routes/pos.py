from flask import Blueprint, render_template, request, jsonify
from models import Product, Sale, SaleItem, Customer
from extensions import db
from datetime import datetime

pos_bp = Blueprint('pos', __name__)

@pos_bp.route('/pos')
def pos():
    return render_template('pos.html', page='pos')

@pos_bp.route('/api/products/search')
def search_products():
    q = request.args.get('q', '').strip()
    category_id = request.args.get('category_id', type=int)
    query = Product.query.filter_by(active=True)
    if q:
        query = query.filter(
            (Product.name.ilike(f'%{q}%')) |
            (Product.sku.ilike(f'%{q}%')) |
            (Product.barcode.ilike(f'%{q}%')) |
            (Product.hsn_code.ilike(f'%{q}%'))
        )
    if category_id:
        query = query.filter_by(category_id=category_id)
    products = query.order_by(Product.name).limit(60).all()
    return jsonify([p.to_dict() for p in products])

@pos_bp.route('/api/checkout', methods=['POST'])
def checkout():
    data = request.get_json()
    items = data.get('items', [])
    customer_id = data.get('customer_id', 1)
    payment_method = data.get('payment_method', 'cash')
    amount_paid = float(data.get('amount_paid', 0))
    discount = float(data.get('discount', 0))
    notes = data.get('notes', '')

    if not items:
        return jsonify({'error': 'Cart is empty / கார்ட் காலியாக உள்ளது'}), 400

    total_cgst = 0; total_sgst = 0; grand_total = 0; sub_total = 0
    sale_items = []
    for item in items:
        product = Product.query.get(item['product_id'])
        if not product:
            return jsonify({'error': f'Product not found'}), 404
        qty = int(item['quantity'])
        if product.stock < qty:
            return jsonify({'error': f'Stock insufficient: {product.name} — only {product.stock} left'}), 400
        subtotal = round(product.price * qty, 2)
        taxable = round(subtotal / (1 + product.gst_rate / 100), 2)
        gst_amt = round(subtotal - taxable, 2)
        total_cgst += gst_amt / 2
        total_sgst += gst_amt / 2
        grand_total += subtotal
        sub_total += taxable
        sale_items.append((product, qty, product.price, product.gst_rate, subtotal))

    total_after_discount = round(grand_total - discount, 2)
    change = round(amount_paid - total_after_discount, 2)

    sale = Sale(
        customer_id=customer_id,
        subtotal=round(sub_total, 2),
        total_cgst=round(total_cgst, 2),
        total_sgst=round(total_sgst, 2),
        total=total_after_discount,
        discount=discount,
        amount_paid=amount_paid,
        change_given=max(0, change),
        payment_method=payment_method,
        notes=notes,
        created_at=datetime.utcnow()
    )
    db.session.add(sale)
    db.session.flush()

    for product, qty, price, gst_rate, subtotal in sale_items:
        si = SaleItem(sale_id=sale.id, product_id=product.id, quantity=qty,
                      price=price, gst_rate=gst_rate, subtotal=subtotal)
        db.session.add(si)
        product.stock -= qty

    # Loyalty points: 1 point per ₹10 spent
    customer = Customer.query.get(customer_id)
    if customer:
        customer.points += int(total_after_discount // 10)

    db.session.commit()
    return jsonify({'success': True, 'sale': sale.to_dict(), 'receipt_id': sale.id})
