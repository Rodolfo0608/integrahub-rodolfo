from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class CanonicalModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Address(CanonicalModel):
    street: str
    city: str
    country: str


class Customer(CanonicalModel):
    id: int
    fullName: str
    email: str
    phone: str
    address: Address


class Product(CanonicalModel):
    id: int
    name: str
    quantity: int = Field(gt=0)
    unitPriceUsd: Decimal
    grossTotalUsd: Decimal
    discountPercent: Decimal
    netTotalUsd: Decimal


class Products(CanonicalModel):
    cartCount: int
    itemCount: int
    units: int
    items: list[Product]
    grossTotalUsd: Decimal
    discountTotalUsd: Decimal
    netTotalUsd: Decimal


class Conversion(CanonicalModel):
    rate: Decimal
    amount: Decimal


class ForeignExchange(CanonicalModel):
    base: Literal["USD"] = "USD"
    date: str
    convertedTotals: dict[str, Conversion]


class Warning(CanonicalModel):
    provider: Literal["CORE", "PRODUCTS", "FX", "UNSTABLE"]
    code: str
    message: str


class Profile(CanonicalModel):
    customerId: int
    customer: Customer | None
    products: Products | None
    fx: ForeignExchange | None
    partial: bool
    warnings: list[Warning]
    requestId: str
