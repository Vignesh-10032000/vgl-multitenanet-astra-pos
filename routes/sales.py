from flask import Blueprint, render_template, request, jsonify
from models import Sale, SaleItem
from extensions import db

sales_bp = Blueprint('sales', __name__)

@sales_bp.route('/sales')
def sales():
    return render_template('sales.html', page='sales')

@sales_bp.route('/api/sales')
def get_sales():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 20, type=int)
    q = request.args.get('q', '')
    payment = request.args.get('payment', '')

    query = Sale.query
    if q:
        query = query.filter(Sale.id == int(q) if q.isdigit() else Sale.id == -1)
    if payment:
        query = query.filter_by(payment_method=payment)

    paginated = query.order_by(Sale.created_at.desc()).paginate(page=page, per_page=per_page, error_out=False)
    return jsonify({
        'sales': [s.to_dict() for s in paginated.items],
        'total': paginated.total,
        'pages': paginated.pages,
        'current_page': page,
    })

@sales_bp.route('/api/sales/<int:sid>')
def get_sale(sid):
    s = Sale.query.get_or_404(sid)
    return jsonify(s.to_dict())

@sales_bp.route('/api/sales/<int:sid>', methods=['DELETE'])
def delete_sale(sid):
    s = Sale.query.get_or_404(sid)
    # Restore stock
    for item in s.items:
        item.product.stock += item.quantity
    db.session.delete(s)
    db.session.commit()
    return jsonify({'success': True})
