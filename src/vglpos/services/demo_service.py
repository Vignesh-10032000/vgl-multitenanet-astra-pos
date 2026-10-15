"""Create the isolated public demo workspace on first use."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import (
    Branch,
    Category,
    Company,
    Customer,
    DocumentSeries,
    Permission,
    Product,
    Role,
    RolePermission,
    Sale,
    SaleItem,
    SalePayment,
    Shift,
    TaxRate,
    Terminal,
    User,
    UserRole,
)
from vglpos.security.password import hash_password, hash_pin
from vglpos.security.permissions import PERMISSION_DEFINITIONS
from vglpos.utils.gst import financial_year_code

DEMO_LOGIN_CODE = "VGL-DEMO"
DEMO_USERNAME = "explorer"
DEMO_PASSWORD = "VGL-public-demo-workspace-2026!"

_DEMO_PERMISSIONS = frozenset(
    {
        "sale.create",
        "sale.view",
        "sale.discount",
        "product.view",
        "stock.view",
        "customer.view",
        "customer.create",
        "return.create",
        "report.view",
        "report.gst",
        "shift.open",
        "shift.close",
        "cash.move",
        "purchase.view",
        "supplier.view",
        "einvoice.view",
    }
)


@dataclass(frozen=True, slots=True)
class DemoIdentity:
    company_id: int
    branch_id: int
    terminal_id: int
    user_id: int
    seeded: bool


class DemoWorkspaceService:
    """Provision one shared tenant containing realistic, non-sensitive sample data."""

    def __init__(self, session: Session) -> None:
        self.session = session

    def ensure(self) -> DemoIdentity:
        company = self.session.scalar(
            select(Company).where(
                Company.login_code == DEMO_LOGIN_CODE,
                Company.deleted_at.is_(None),
            )
        )
        if company is not None:
            return self._identity(company.id, seeded=False)
        return self._seed()

    def existing(self) -> DemoIdentity:
        company_id = self.session.scalar(
            select(Company.id).where(
                Company.login_code == DEMO_LOGIN_CODE,
                Company.deleted_at.is_(None),
            )
        )
        if company_id is None:
            raise RuntimeError("The demo workspace could not be initialized.")
        return self._identity(company_id, seeded=False)

    def _identity(self, company_id: int, *, seeded: bool) -> DemoIdentity:
        branch_id = self.session.scalar(
            select(Branch.id).where(
                Branch.company_id == company_id,
                Branch.code == "MAIN",
                Branch.deleted_at.is_(None),
            )
        )
        terminal_id = self.session.scalar(
            select(Terminal.id).where(
                Terminal.company_id == company_id,
                Terminal.code == "DEMO-01",
                Terminal.deleted_at.is_(None),
            )
        )
        user_id = self.session.scalar(
            select(User.id).where(
                User.company_id == company_id,
                User.username == DEMO_USERNAME,
                User.deleted_at.is_(None),
            )
        )
        if branch_id is None or terminal_id is None or user_id is None:
            raise RuntimeError("The demo workspace is incomplete.")
        return DemoIdentity(company_id, branch_id, terminal_id, user_id, seeded)

    def _seed(self) -> DemoIdentity:
        permissions = self._permissions()
        company = Company(
            name="VGL Demo Mart",
            legal_name="VGL Demo Mart Private Limited",
            login_code=DEMO_LOGIN_CODE,
            gstin="33AABCV1234A1Z5",
            pan="AABCV1234A",
            state_code="33",
            address_line1="42 Growth Avenue",
            address_line2="T Nagar",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600017",
            contact_email="demo@vigneshgrowthlab.com",
            contact_phone="9000000000",
        )
        self.session.add(company)
        self.session.flush()

        branch = Branch(
            company_id=company.id,
            code="MAIN",
            name="Chennai Experience Store",
            gstin=company.gstin,
            state_code="33",
            address_line1="42 Growth Avenue",
            address_line2="T Nagar",
            city="Chennai",
            state="Tamil Nadu",
            postal_code="600017",
            phone="9000000001",
            is_head_office=True,
        )
        self.session.add(branch)
        self.session.flush()

        terminal = Terminal(
            company_id=company.id,
            branch_id=branch.id,
            code="DEMO-01",
            name="Demo Checkout",
        )
        user = User(
            company_id=company.id,
            username=DEMO_USERNAME,
            email="explorer@demo.vigneshgrowthlab.com",
            password_hash=hash_password(DEMO_PASSWORD),
            pin_hash=hash_pin("2026"),
            full_name="VGL Demo Explorer",
        )
        role = Role(
            company_id=company.id,
            name="DEMO EXPLORER",
            description="Safe public access to the isolated VGL demonstration workspace",
            is_system=True,
            max_discount_percent=Decimal("10.00"),
        )
        self.session.add_all([terminal, user, role])
        self.session.flush()

        company.created_by = user.id
        branch.created_by = user.id
        terminal.created_by = user.id
        role.created_by = user.id
        self.session.add(
            UserRole(
                company_id=company.id,
                user_id=user.id,
                role_id=role.id,
                branch_id=branch.id,
                created_by=user.id,
            )
        )
        self.session.add_all(
            RolePermission(
                company_id=company.id,
                role_id=role.id,
                permission_id=permissions[code].id,
                created_by=user.id,
            )
            for code in sorted(_DEMO_PERMISSIONS)
        )

        rates = self._tax_rates(company.id, user.id)
        categories = self._categories(company.id, user.id)
        self.session.add_all([*rates.values(), *categories.values()])
        self.session.flush()

        products = self._products(company.id, user.id, rates, categories)
        customers = self._customers(company.id, user.id)
        self.session.add_all([*products, *customers])
        self.session.flush()

        shift = Shift(
            company_id=company.id,
            branch_id=branch.id,
            terminal_id=terminal.id,
            cashier_id=user.id,
            opening_cash=Decimal("2500.00"),
            status="OPEN",
            opening_denominations={"500": 3, "200": 3, "100": 4},
            notes="Demo counter ready for checkout",
            created_by=user.id,
        )
        self.session.add(shift)
        self.session.flush()

        sales = self._sales(
            company.id, branch.id, terminal.id, user.id, shift.id, products, customers
        )
        self.session.add_all(
            [
                DocumentSeries(
                    company_id=company.id,
                    branch_id=branch.id,
                    doc_type="SALE",
                    prefix="DEMO/",
                    current_number=len(sales),
                    financial_year=financial_year_code(date.today()),
                    created_by=user.id,
                ),
                DocumentSeries(
                    company_id=company.id,
                    branch_id=branch.id,
                    doc_type="CREDIT_NOTE",
                    prefix="DEMO-CN/",
                    current_number=0,
                    financial_year=financial_year_code(date.today()),
                    created_by=user.id,
                ),
            ]
        )
        self.session.flush()
        return DemoIdentity(company.id, branch.id, terminal.id, user.id, seeded=True)

    def _permissions(self) -> dict[str, Permission]:
        permissions = {item.code: item for item in self.session.scalars(select(Permission))}
        for definition in PERMISSION_DEFINITIONS:
            if definition.code in permissions:
                continue
            permission = Permission(
                code=definition.code,
                description=definition.description,
                category=definition.category,
            )
            self.session.add(permission)
            permissions[definition.code] = permission
        self.session.flush()
        return permissions

    @staticmethod
    def _tax_rates(company_id: int, user_id: int) -> dict[str, TaxRate]:
        return {
            "5": TaxRate(
                company_id=company_id,
                name="GST 5%",
                rate=Decimal("5.00"),
                cgst_rate=Decimal("2.50"),
                sgst_rate=Decimal("2.50"),
                igst_rate=Decimal("5.00"),
                cess_rate=Decimal("0.00"),
                effective_from=date(2017, 7, 1),
                created_by=user_id,
            ),
            "12": TaxRate(
                company_id=company_id,
                name="GST 12%",
                rate=Decimal("12.00"),
                cgst_rate=Decimal("6.00"),
                sgst_rate=Decimal("6.00"),
                igst_rate=Decimal("12.00"),
                cess_rate=Decimal("0.00"),
                effective_from=date(2017, 7, 1),
                created_by=user_id,
            ),
            "18": TaxRate(
                company_id=company_id,
                name="GST 18%",
                rate=Decimal("18.00"),
                cgst_rate=Decimal("9.00"),
                sgst_rate=Decimal("9.00"),
                igst_rate=Decimal("18.00"),
                cess_rate=Decimal("0.00"),
                effective_from=date(2017, 7, 1),
                created_by=user_id,
            ),
        }

    @staticmethod
    def _categories(company_id: int, user_id: int) -> dict[str, Category]:
        return {
            "essentials": Category(
                company_id=company_id,
                name="Daily Essentials",
                name_en="Daily Essentials",
                name_ta="அன்றாட தேவைகள்",
                code="ESSENTIALS",
                icon="shopping-basket",
                created_by=user_id,
            ),
            "beverages": Category(
                company_id=company_id,
                name="Beverages",
                name_en="Beverages",
                name_ta="பானங்கள்",
                code="BEVERAGES",
                icon="cup-soda",
                created_by=user_id,
            ),
            "care": Category(
                company_id=company_id,
                name="Personal Care",
                name_en="Personal Care",
                name_ta="தனிப்பட்ட பராமரிப்பு",
                code="PERSONAL-CARE",
                icon="sparkles",
                created_by=user_id,
            ),
        }

    @staticmethod
    def _products(
        company_id: int,
        user_id: int,
        rates: dict[str, TaxRate],
        categories: dict[str, Category],
    ) -> list[Product]:
        rows = (
            (
                "VGL-RICE-5KG",
                "8901000000011",
                "Ponni Rice 5 kg",
                "பொன்னி அரிசி 5 கிலோ",
                "essentials",
                "5",
                "255.00",
                "310.00",
                "325.00",
                "68.000",
            ),
            (
                "VGL-OIL-1L",
                "8901000000028",
                "Cold Pressed Groundnut Oil 1 L",
                "கடலை எண்ணெய் 1 லிட்டர்",
                "essentials",
                "5",
                "142.00",
                "185.00",
                "195.00",
                "42.000",
            ),
            (
                "VGL-DAL-1KG",
                "8901000000035",
                "Premium Toor Dal 1 kg",
                "துவரம் பருப்பு 1 கிலோ",
                "essentials",
                "5",
                "118.00",
                "149.00",
                "155.00",
                "76.000",
            ),
            (
                "VGL-COFFEE-200",
                "8901000000042",
                "Filter Coffee 200 g",
                "ஃபில்டர் காபி 200 கிராம்",
                "beverages",
                "5",
                "92.00",
                "125.00",
                "130.00",
                "54.000",
            ),
            (
                "VGL-JUICE-1L",
                "8901000000059",
                "Mango Juice 1 L",
                "மாம்பழ ஜூஸ் 1 லிட்டர்",
                "beverages",
                "12",
                "62.00",
                "85.00",
                "95.00",
                "38.000",
            ),
            (
                "VGL-BISCUIT-300",
                "8901000000066",
                "Millet Biscuits 300 g",
                "சிறுதானிய பிஸ்கட் 300 கிராம்",
                "essentials",
                "18",
                "48.00",
                "69.00",
                "75.00",
                "91.000",
            ),
            (
                "VGL-SOAP-4",
                "8901000000073",
                "Herbal Bath Soap Pack of 4",
                "மூலிகை குளியல் சோப்பு 4",
                "care",
                "18",
                "96.00",
                "132.00",
                "145.00",
                "47.000",
            ),
            (
                "VGL-SHAMPOO-340",
                "8901000000080",
                "Gentle Shampoo 340 ml",
                "மென்மையான ஷாம்பு 340 மி.லி",
                "care",
                "18",
                "138.00",
                "189.00",
                "210.00",
                "29.000",
            ),
        )
        return [
            Product(
                company_id=company_id,
                sku=sku,
                barcode=barcode,
                name=name,
                name_en=name,
                name_ta=name_ta,
                brand="VGL Demo Select",
                category_id=categories[category].id,
                tax_rate_id=rates[rate].id,
                cost_price=Decimal(cost),
                selling_price=Decimal(price),
                mrp=Decimal(mrp),
                on_hand=Decimal(stock),
                low_stock_threshold=Decimal("10.000"),
                created_by=user_id,
            )
            for sku, barcode, name, name_ta, category, rate, cost, price, mrp, stock in rows
        ]

    @staticmethod
    def _customers(company_id: int, user_id: int) -> list[Customer]:
        rows = (
            ("9000000011", "Ananya Raman", "ananya@example.invalid", "18420.00", 42, "720.000"),
            ("9000000022", "Karthik Selvan", "karthik@example.invalid", "12680.00", 31, "410.000"),
            ("9000000033", "Meena Stores", "meena@example.invalid", "28950.00", 58, "980.000"),
            ("9000000044", "Ravi Kumar", "ravi@example.invalid", "7640.00", 19, "255.000"),
            ("9000000055", "Priya Natarajan", "priya@example.invalid", "15875.00", 37, "530.000"),
        )
        return [
            Customer(
                company_id=company_id,
                phone=phone,
                name=name,
                email=email,
                state_code="33",
                city="Chennai",
                total_spent=Decimal(spent),
                total_orders=orders,
                loyalty_points=Decimal(points),
                created_by=user_id,
            )
            for phone, name, email, spent, orders, points in rows
        ]

    def _sales(
        self,
        company_id: int,
        branch_id: int,
        terminal_id: int,
        user_id: int,
        shift_id: int,
        products: list[Product],
        customers: list[Customer],
    ) -> list[Sale]:
        rows = (
            (0, 0, 0, "CASH", "310.00"),
            (0, 4, 1, "UPI", "255.00"),
            (0, 6, 2, "CARD", "396.00"),
            (0, 2, 3, "UPI", "298.00"),
            (1, 1, 4, "CARD", "370.00"),
            (1, 5, 0, "CASH", "207.00"),
            (2, 7, 1, "UPI", "378.00"),
            (3, 3, 2, "CASH", "250.00"),
            (4, 0, 3, "CARD", "620.00"),
            (5, 4, 4, "UPI", "170.00"),
            (6, 2, 0, "CASH", "447.00"),
            (6, 6, 1, "CARD", "264.00"),
        )
        now = datetime.now(UTC)
        sales: list[Sale] = []
        for index, (days_ago, product_index, customer_index, method, taxable_text) in enumerate(
            rows, 1
        ):
            product = products[product_index]
            customer = customers[customer_index]
            taxable = Decimal(taxable_text)
            rate = (
                Decimal("18.00")
                if product_index in {5, 6, 7}
                else Decimal("12.00")
                if product_index == 4
                else Decimal("5.00")
            )
            tax = (taxable * rate / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            cgst = (tax / 2).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            sgst = tax - cgst
            total = taxable + tax
            created_at = now - timedelta(days=days_ago, hours=index)
            sale = Sale(
                company_id=company_id,
                branch_id=branch_id,
                terminal_id=terminal_id,
                customer_id=customer.id,
                cashier_id=user_id,
                shift_id=shift_id,
                invoice_number=f"DEMO/{index:05d}",
                business_date=date.today() - timedelta(days=days_ago),
                sale_status="COMPLETED",
                supply_type="INTRASTATE",
                place_of_supply="33",
                customer_name_at_sale=customer.name,
                gross_amount=taxable,
                discount_amount=Decimal("0.00"),
                taxable_amount=taxable,
                cgst_amount=cgst,
                sgst_amount=sgst,
                igst_amount=Decimal("0.00"),
                cess_amount=Decimal("0.00"),
                round_off=Decimal("0.00"),
                net_amount=total,
                amount_paid=total,
                balance_due=Decimal("0.00"),
                payment_method=method,
                notes="Sample transaction created for the VGL demo workspace",
                created_by=user_id,
                created_at=created_at,
            )
            self.session.add(sale)
            self.session.flush()
            self.session.add_all(
                [
                    SaleItem(
                        company_id=company_id,
                        sale_id=sale.id,
                        product_id=product.id,
                        line_number=1,
                        quantity=Decimal("1.000"),
                        unit_price=taxable,
                        gross_amount=taxable,
                        discount_amount=Decimal("0.00"),
                        taxable_amount=taxable,
                        tax_rate=rate,
                        cgst_rate=rate / 2,
                        sgst_rate=rate / 2,
                        igst_rate=Decimal("0.00"),
                        cess_rate=Decimal("0.00"),
                        cgst_amount=cgst,
                        sgst_amount=sgst,
                        igst_amount=Decimal("0.00"),
                        cess_amount=Decimal("0.00"),
                        cost_at_sale=product.cost_price,
                        hsn_code_at_sale="9999",
                        total_amount=total,
                        created_by=user_id,
                        created_at=created_at,
                    ),
                    SalePayment(
                        company_id=company_id,
                        sale_id=sale.id,
                        payment_method=method,
                        amount=total,
                        reference_number=f"DEMO-{method}-{index:04d}",
                        created_by=user_id,
                        created_at=created_at,
                    ),
                ]
            )
            sales.append(sale)
        return sales
