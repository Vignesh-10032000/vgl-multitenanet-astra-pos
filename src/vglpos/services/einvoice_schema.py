"""Local Pydantic contracts for GST e-invoice schema 1.1 and e-way bills."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

Gstin = Annotated[str, Field(pattern=r"^[0-9]{2}[0-9A-Z]{13}$")]
MoneyValue = Annotated[Decimal, Field(ge=0, max_digits=16, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=13, decimal_places=3)]
TaxRate = Annotated[Decimal, Field(ge=0, le=100, max_digits=5, decimal_places=2)]


class IRPSchemaModel(BaseModel):
    """Reject unknown keys so local validation cannot silently drift from the IRP contract."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True, str_strip_whitespace=True)


class TransactionDetails(IRPSchemaModel):
    tax_scheme: Literal["GST"] = Field(alias="TaxSch", default="GST")
    supply_type: Literal["B2B"] = Field(alias="SupTyp", default="B2B")
    reverse_charge: Literal["Y", "N"] = Field(alias="RegRev", default="N")
    igst_on_intra: Literal["Y", "N"] = Field(alias="IgstOnIntra", default="N")


class DocumentDetails(IRPSchemaModel):
    document_type: Literal["INV"] = Field(alias="Typ", default="INV")
    number: str = Field(alias="No", min_length=1, max_length=16, pattern=r"^[A-Za-z0-9/-]+$")
    document_date: str = Field(alias="Dt", pattern=r"^[0-3][0-9]/[0-1][0-9]/[0-9]{4}$")


class SellerDetails(IRPSchemaModel):
    gstin: Gstin = Field(alias="Gstin")
    legal_name: str = Field(alias="LglNm", min_length=1, max_length=100)
    trade_name: str | None = Field(alias="TrdNm", default=None, max_length=100)
    address_line1: str = Field(alias="Addr1", min_length=1, max_length=100)
    address_line2: str | None = Field(alias="Addr2", default=None, max_length=100)
    location: str = Field(alias="Loc", min_length=1, max_length=50)
    postal_code: int = Field(alias="Pin", ge=100000, le=999999)
    state_code: str = Field(alias="Stcd", pattern=r"^[0-9]{2}$")
    phone: str | None = Field(alias="Ph", default=None, max_length=12)
    email: str | None = Field(alias="Em", default=None, max_length=100)


class BuyerDetails(IRPSchemaModel):
    gstin: Gstin | Literal["URP"] = Field(alias="Gstin")
    legal_name: str = Field(alias="LglNm", min_length=1, max_length=100)
    trade_name: str | None = Field(alias="TrdNm", default=None, max_length=100)
    place_of_supply: str = Field(alias="Pos", pattern=r"^[0-9]{2}$")
    address_line1: str = Field(alias="Addr1", min_length=1, max_length=100)
    address_line2: str | None = Field(alias="Addr2", default=None, max_length=100)
    location: str = Field(alias="Loc", min_length=1, max_length=50)
    postal_code: int = Field(alias="Pin", ge=100000, le=999999)
    state_code: str = Field(alias="Stcd", pattern=r"^[0-9]{2}$")
    phone: str | None = Field(alias="Ph", default=None, max_length=12)
    email: str | None = Field(alias="Em", default=None, max_length=100)


class ItemDetails(IRPSchemaModel):
    serial_number: str = Field(alias="SlNo", min_length=1, max_length=6)
    description: str = Field(alias="PrdDesc", min_length=1, max_length=300)
    is_service: Literal["Y", "N"] = Field(alias="IsServc", default="N")
    hsn_code: str = Field(alias="HsnCd", min_length=4, max_length=8, pattern=r"^[0-9]+$")
    quantity: Quantity = Field(alias="Qty")
    unit: str = Field(alias="Unit", min_length=3, max_length=8)
    unit_price: MoneyValue = Field(alias="UnitPrice")
    total_amount: MoneyValue = Field(alias="TotAmt")
    discount: MoneyValue = Field(alias="Discount")
    assessable_amount: MoneyValue = Field(alias="AssAmt")
    gst_rate: TaxRate = Field(alias="GstRt")
    igst_amount: MoneyValue = Field(alias="IgstAmt")
    cgst_amount: MoneyValue = Field(alias="CgstAmt")
    sgst_amount: MoneyValue = Field(alias="SgstAmt")
    cess_rate: TaxRate = Field(alias="CesRt")
    cess_amount: MoneyValue = Field(alias="CesAmt")
    total_item_value: MoneyValue = Field(alias="TotItemVal")


class ValueDetails(IRPSchemaModel):
    assessable_value: MoneyValue = Field(alias="AssVal")
    cgst_value: MoneyValue = Field(alias="CgstVal")
    sgst_value: MoneyValue = Field(alias="SgstVal")
    igst_value: MoneyValue = Field(alias="IgstVal")
    cess_value: MoneyValue = Field(alias="CesVal")
    discount: MoneyValue = Field(alias="Discount")
    other_charges: Decimal = Field(alias="OthChrg", max_digits=14, decimal_places=2)
    total_invoice_value: MoneyValue = Field(alias="TotInvVal")


class EInvoicePayload(IRPSchemaModel):
    version: Literal["1.1"] = Field(alias="Version", default="1.1")
    transaction: TransactionDetails = Field(alias="TranDtls")
    document: DocumentDetails = Field(alias="DocDtls")
    seller: SellerDetails = Field(alias="SellerDtls")
    buyer: BuyerDetails = Field(alias="BuyerDtls")
    items: list[ItemDetails] = Field(alias="ItemList", min_length=1, max_length=1000)
    values: ValueDetails = Field(alias="ValDtls")


class EWayItem(IRPSchemaModel):
    product_name: str = Field(alias="productName", min_length=1, max_length=100)
    product_description: str = Field(alias="productDesc", min_length=1, max_length=100)
    hsn_code: int = Field(alias="hsnCode", gt=0)
    quantity: Quantity = Field(alias="quantity")
    quantity_unit: str = Field(alias="qtyUnit", min_length=3, max_length=8)
    cgst_rate: TaxRate = Field(alias="cgstRate")
    sgst_rate: TaxRate = Field(alias="sgstRate")
    igst_rate: TaxRate = Field(alias="igstRate")
    cess_rate: TaxRate = Field(alias="cessRate")
    taxable_amount: MoneyValue = Field(alias="taxableAmount")


class EWayBillPayload(IRPSchemaModel):
    supply_type: Literal["O"] = Field(alias="supplyType", default="O")
    sub_supply_type: Literal["1"] = Field(alias="subSupplyType", default="1")
    document_type: Literal["INV"] = Field(alias="docType", default="INV")
    document_number: str = Field(alias="docNo", min_length=1, max_length=16)
    document_date: str = Field(alias="docDate", pattern=r"^[0-3][0-9]/[0-1][0-9]/[0-9]{4}$")
    from_gstin: Gstin = Field(alias="fromGstin")
    from_trade_name: str = Field(alias="fromTrdName", min_length=1, max_length=100)
    from_address1: str = Field(alias="fromAddr1", min_length=1, max_length=120)
    from_address2: str | None = Field(alias="fromAddr2", default=None, max_length=120)
    from_place: str = Field(alias="fromPlace", min_length=1, max_length=50)
    from_pincode: int = Field(alias="fromPincode", ge=100000, le=999999)
    actual_from_state_code: int = Field(alias="actFromStateCode", ge=1, le=99)
    from_state_code: int = Field(alias="fromStateCode", ge=1, le=99)
    to_gstin: Gstin | Literal["URP"] = Field(alias="toGstin")
    to_trade_name: str = Field(alias="toTrdName", min_length=1, max_length=100)
    to_address1: str = Field(alias="toAddr1", min_length=1, max_length=120)
    to_place: str = Field(alias="toPlace", min_length=1, max_length=50)
    to_pincode: int = Field(alias="toPincode", ge=100000, le=999999)
    actual_to_state_code: int = Field(alias="actToStateCode", ge=1, le=99)
    to_state_code: int = Field(alias="toStateCode", ge=1, le=99)
    transaction_type: Literal[1] = Field(alias="transactionType", default=1)
    total_value: MoneyValue = Field(alias="totalValue")
    cgst_value: MoneyValue = Field(alias="cgstValue")
    sgst_value: MoneyValue = Field(alias="sgstValue")
    igst_value: MoneyValue = Field(alias="igstValue")
    cess_value: MoneyValue = Field(alias="cessValue")
    other_value: Decimal = Field(alias="otherValue", max_digits=14, decimal_places=2)
    total_invoice_value: MoneyValue = Field(alias="totInvValue")
    transporter_id: str | None = Field(alias="transporterId", default=None, max_length=15)
    transporter_name: str | None = Field(alias="transporterName", default=None, max_length=100)
    transport_document_number: str | None = Field(alias="transDocNo", default=None, max_length=15)
    transport_mode: Literal["1", "2", "3", "4"] = Field(alias="transMode")
    transport_distance: str = Field(alias="transDistance", pattern=r"^[0-9]{1,4}$")
    transport_document_date: str | None = Field(
        alias="transDocDate", default=None, pattern=r"^[0-3][0-9]/[0-1][0-9]/[0-9]{4}$"
    )
    vehicle_number: str | None = Field(alias="vehicleNo", default=None, max_length=20)
    vehicle_type: Literal["R", "O"] | None = Field(alias="vehicleType", default=None)
    items: list[EWayItem] = Field(alias="itemList", min_length=1, max_length=1000)
