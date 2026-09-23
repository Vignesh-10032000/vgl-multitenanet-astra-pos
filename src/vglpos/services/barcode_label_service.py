"""Printable Code128 and EAN13 SVG label generation."""

from __future__ import annotations

from decimal import Decimal
from html import escape

from sqlalchemy import select
from sqlalchemy.orm import Session

from vglpos.domain.models import Product
from vglpos.services.exceptions import EntityNotFoundError, ValidationError

_CODE128_PATTERNS = (
    "212222",
    "222122",
    "222221",
    "121223",
    "121322",
    "131222",
    "122213",
    "122312",
    "132212",
    "221213",
    "221312",
    "231212",
    "112232",
    "122132",
    "122231",
    "113222",
    "123122",
    "123221",
    "223211",
    "221132",
    "221231",
    "213212",
    "223112",
    "312131",
    "311222",
    "321122",
    "321221",
    "312212",
    "322112",
    "322211",
    "212123",
    "212321",
    "232121",
    "111323",
    "131123",
    "131321",
    "112313",
    "132113",
    "132311",
    "211313",
    "231113",
    "231311",
    "112133",
    "112331",
    "132131",
    "113123",
    "113321",
    "133121",
    "313121",
    "211331",
    "231131",
    "213113",
    "213311",
    "213131",
    "311123",
    "311321",
    "331121",
    "312113",
    "312311",
    "332111",
    "314111",
    "221411",
    "431111",
    "111224",
    "111422",
    "121124",
    "121421",
    "141122",
    "141221",
    "112214",
    "112412",
    "122114",
    "122411",
    "142112",
    "142211",
    "241211",
    "221114",
    "413111",
    "241112",
    "134111",
    "111242",
    "121142",
    "121241",
    "114212",
    "124112",
    "124211",
    "411212",
    "421112",
    "421211",
    "212141",
    "214121",
    "412121",
    "111143",
    "111341",
    "131141",
    "114113",
    "114311",
    "411113",
    "411311",
    "113141",
    "114131",
    "311141",
    "411131",
    "211412",
    "211214",
    "211232",
    "2331112",
)
_EAN_L = (
    "0001101",
    "0011001",
    "0010011",
    "0111101",
    "0100011",
    "0110001",
    "0101111",
    "0111011",
    "0110111",
    "0001011",
)
_EAN_G = (
    "0100111",
    "0110011",
    "0011011",
    "0100001",
    "0011101",
    "0111001",
    "0000101",
    "0010001",
    "0001001",
    "0010111",
)
_EAN_R = (
    "1110010",
    "1100110",
    "1101100",
    "1000010",
    "1011100",
    "1001110",
    "1010000",
    "1000100",
    "1001000",
    "1110100",
)
_EAN_PARITY = (
    "LLLLLL",
    "LLGLGG",
    "LLGGLG",
    "LLGGGL",
    "LGLLGG",
    "LGGLLG",
    "LGGGLL",
    "LGLGLG",
    "LGLGGL",
    "LGGLGL",
)


class BarcodeLabelService:
    """Render tenant-owned products into one browser-printable SVG sheet."""

    def __init__(self, session: Session, company_id: int) -> None:
        if not company_id:
            raise ValueError("company_id is required.")
        self.session = session
        self.company_id = company_id

    def render(
        self,
        product_ids: list[int],
        *,
        symbology: str,
        width_mm: Decimal,
        height_mm: Decimal,
    ) -> str:
        """Generate exact bars and escaped captions for up to one hundred labels."""
        if not product_ids or len(product_ids) > 100 or len(product_ids) != len(set(product_ids)):
            raise ValidationError("Barcode labels require 1 to 100 unique products.")
        products = {
            product.id: product
            for product in self.session.scalars(
                select(Product).where(
                    Product.company_id == self.company_id,
                    Product.id.in_(product_ids),
                    Product.is_active.is_(True),
                    Product.deleted_at.is_(None),
                )
            )
        }
        if set(product_ids) != products.keys():
            raise EntityNotFoundError("A barcode-label product was not found.")
        normalized = symbology.strip().upper()
        if normalized not in {"AUTO", "CODE128", "EAN13"}:
            raise ValidationError("Unsupported barcode symbology.")
        labels = [
            self._label_svg(
                products[product_id],
                index=index,
                symbology=normalized,
                width_mm=width_mm,
                height_mm=height_mm,
            )
            for index, product_id in enumerate(product_ids)
        ]
        total_height = height_mm * len(labels)
        return (
            '<?xml version="1.0" encoding="UTF-8"?>'
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width_mm}mm" '
            f'height="{total_height}mm" viewBox="0 0 {width_mm} {total_height}">'
            '<rect width="100%" height="100%" fill="white"/>' + "".join(labels) + "</svg>"
        )

    def _label_svg(
        self,
        product: Product,
        *,
        index: int,
        symbology: str,
        width_mm: Decimal,
        height_mm: Decimal,
    ) -> str:
        code = (product.barcode or product.sku).strip()
        selected = symbology
        if selected == "AUTO":
            selected = "EAN13" if code.isdigit() and len(code) in {12, 13} else "CODE128"
        if selected == "EAN13":
            code, modules = self._ean13(code)
        else:
            modules = self._code128(code)
        quiet = 4
        usable_width = width_mm - Decimal("4.00")
        module_width = usable_width / Decimal(len(modules) + quiet * 2)
        bar_y = Decimal("6.00")
        bar_height = max(Decimal("5.00"), height_mm - Decimal("13.00"))
        rectangles: list[str] = []
        for position, value in enumerate(modules):
            if value != "1":
                continue
            x = Decimal("2.00") + module_width * Decimal(position + quiet)
            rectangles.append(
                f'<rect x="{x:.4f}" y="{bar_y}" width="{module_width:.4f}" '
                f'height="{bar_height}" fill="black"/>'
            )
        offset = height_mm * index
        name = escape(product.name)
        visible_code = escape(code)
        price = escape(f"INR {product.selling_price:.2f}")
        return (
            f'<g transform="translate(0 {offset})">'
            f'<rect x="0.2" y="0.2" width="{width_mm - Decimal("0.4")}" '
            f'height="{height_mm - Decimal("0.4")}" fill="none" stroke="#bbb" stroke-width="0.2"/>'
            f'<text x="2" y="4" font-family="sans-serif" font-size="2.8">{name}</text>'
            + "".join(rectangles)
            + f'<text x="2" y="{height_mm - Decimal("4.0")}" font-family="monospace" '
            f'font-size="2.6">{visible_code}</text>'
            f'<text x="{width_mm - Decimal("2.0")}" y="{height_mm - Decimal("4.0")}" '
            f'text-anchor="end" font-family="sans-serif" font-size="2.8">{price}</text>'
            "</g>"
        )

    @staticmethod
    def _code128(value: str) -> str:
        if (
            not value
            or len(value) > 80
            or any(ord(character) < 32 or ord(character) > 126 for character in value)
        ):
            raise ValidationError("Code128 values must contain 1 to 80 printable ASCII characters.")
        data = [ord(character) - 32 for character in value]
        checksum = (104 + sum(position * code for position, code in enumerate(data, start=1))) % 103
        patterns = (
            _CODE128_PATTERNS[104],
            *(_CODE128_PATTERNS[code] for code in data),
            _CODE128_PATTERNS[checksum],
            _CODE128_PATTERNS[106],
        )
        modules: list[str] = []
        for pattern in patterns:
            is_bar = True
            for width in pattern:
                modules.append(("1" if is_bar else "0") * int(width))
                is_bar = not is_bar
        return "".join(modules)

    @staticmethod
    def _ean13(value: str) -> tuple[str, str]:
        if not value.isdigit() or len(value) not in {12, 13}:
            raise ValidationError("EAN13 requires exactly 12 or 13 digits.")
        digits = [int(character) for character in value[:12]]
        check = (10 - (sum(digits[::2]) + 3 * sum(digits[1::2])) % 10) % 10
        if len(value) == 13 and int(value[-1]) != check:
            raise ValidationError("EAN13 check digit is invalid.")
        normalized = value[:12] + str(check)
        parity = _EAN_PARITY[int(normalized[0])]
        left = "".join(
            (_EAN_L if encoding == "L" else _EAN_G)[int(digit)]
            for digit, encoding in zip(normalized[1:7], parity, strict=True)
        )
        right = "".join(_EAN_R[int(digit)] for digit in normalized[7:])
        return normalized, f"101{left}01010{right}101"
