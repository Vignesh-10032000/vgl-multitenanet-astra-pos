import unittest
import json
from app import create_app
from extensions import db
from models import Product, Category, Customer, Sale, SaleItem, SaleReturn, SaleReturnItem

class POSTestCase(unittest.TestCase):
    def setUp(self):
        # Set up a test client with an in-memory SQLite database
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///:memory:'
        self.client = self.app.test_client()
        
        self.app_context = self.app.app_context()
        self.app_context.push()
        
        db.create_all()
        self.seed_test_data()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.app_context.pop()

    def seed_test_data(self):
        # Create Category
        cat = Category(name="Test F&B", icon="🍛")
        db.session.add(cat)
        db.session.commit()

        # Create Products
        self.prod1 = Product(name="Coffee", sku="C001", price=20.0, stock=50, category_id=cat.id, gst_rate=5)
        self.prod2 = Product(name="Tea", sku="C002", price=15.0, stock=30, category_id=cat.id, gst_rate=5)
        db.session.add_all([self.prod1, self.prod2])
        
        # Create Customers
        self.cust_walkin = Customer(name="Walk-in Customer", phone="0000000000")
        self.cust_regular = Customer(name="Kavitha", phone="9841002002")
        db.session.add_all([self.cust_walkin, self.cust_regular])
        db.session.commit()

        # Create a Sale
        self.sale = Sale(
            customer_id=self.cust_regular.id,
            payment_method="cash",
            subtotal=33.33,
            total_cgst=0.83,
            total_sgst=0.83,
            total=35.0,
            discount=0,
            amount_paid=35.0,
            change_given=0
        )
        db.session.add(self.sale)
        db.session.flush()

        # Create SaleItem
        self.sale_item1 = SaleItem(
            sale_id=self.sale.id,
            product_id=self.prod1.id,
            quantity=1,
            price=20.0,
            gst_rate=5,
            subtotal=20.0
        )
        self.sale_item2 = SaleItem(
            sale_id=self.sale.id,
            product_id=self.prod2.id,
            quantity=1,
            price=15.0,
            gst_rate=5,
            subtotal=15.0
        )
        db.session.add_all([self.sale_item1, self.sale_item2])
        db.session.commit()

    def test_get_customers_walkin_exists(self):
        # Verify customer list API has Walk-in Customer
        response = self.client.get('/api/customers')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        names = [c['name'] for c in data]
        self.assertIn("Walk-in Customer", names)

    def test_product_stock_adjustment(self):
        # Verify stock increment/decrement PATCH endpoint
        response = self.client.patch(f'/api/products/{self.prod1.id}/stock', json={
            'adjustment': 10
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['new_stock'], 60)

    def test_product_soft_delete(self):
        # Verify product soft delete (active=False)
        response = self.client.delete(f'/api/products/{self.prod1.id}')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        
        # Verify is active=False
        prod = Product.query.get(self.prod1.id)
        self.assertFalse(prod.active)

    def test_day_close(self):
        # Verify Day Close report returns accurate payment aggregates
        response = self.client.get('/api/reports/day-close')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['total_transactions'], 1)
        self.assertEqual(data['grand_total'], 35.0)
        self.assertEqual(data['cash'], 35.0)

    def test_sale_return_processing(self):
        # Verify returns REST endpoint and active stock restoration
        response = self.client.post(f'/api/sales/{self.sale.id}/return', json={
            'items': [
                {'product_id': self.prod1.id, 'quantity': 1}
            ],
            'payment_method': 'cash',
            'reason': 'Customer requested return'
        })
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data['success'])
        self.assertEqual(data['refund_amount'], 20.0)

        # Check stock of prod1 went back up from 50 to 51
        prod = Product.query.get(self.prod1.id)
        self.assertEqual(prod.stock, 51)

        # Check duplicated return locks out
        response_dup = self.client.post(f'/api/sales/{self.sale.id}/return', json={
            'items': [
                {'product_id': self.prod1.id, 'quantity': 1}
            ],
            'payment_method': 'cash',
            'reason': 'Double return attempt'
        })
        self.assertEqual(response_dup.status_code, 400)

if __name__ == '__main__':
    unittest.main()
