from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models import Address, Conversion, Customer, ForeignExchange, Product, Products


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class SourceModel(BaseModel):
    # Accept new provider fields, but never serialize the upstream model publicly.
    model_config = ConfigDict(extra="ignore", allow_inf_nan=False)


class CoreAddress(SourceModel):
    address: str = Field(min_length=1)
    city: str = Field(min_length=1)
    country: str = Field(min_length=1)


class CoreUser(SourceModel):
    id: int = Field(gt=0)
    firstName: str = Field(min_length=1)
    lastName: str = Field(min_length=1)
    email: str = Field(min_length=1)
    phone: str = Field(min_length=1)
    address: CoreAddress


class CartItem(SourceModel):
    id: int = Field(gt=0)
    title: str = Field(min_length=1)
    price: Decimal = Field(ge=0)
    quantity: int = Field(gt=0)
    discountPercentage: Decimal = Field(ge=0, le=100)


class Cart(SourceModel):
    userId: int = Field(gt=0)
    products: list[CartItem]


class CartResponse(SourceModel):
    carts: list[Cart]
    total: int = Field(ge=0)


class Rates(SourceModel):
    base: str
    date: date
    rates: dict[str, Decimal]

    @field_validator("rates")
    @classmethod
    def validate_rates(cls, value):
        if not {"EUR", "GBP"}.issubset(value) or any(value[c] <= 0 for c in ("EUR", "GBP")):
            raise ValueError("Missing or nonpositive FX rates")
        return value


def map_customer(payload: dict, customer_id: int) -> Customer:
    user = CoreUser.model_validate(payload)
    if user.id != customer_id:
        raise ValueError("Mismatched customer identity")
    return Customer(id=user.id, fullName=f"{user.firstName} {user.lastName}",
                    email=user.email, phone=user.phone,
                    address=Address(street=user.address.address, city=user.address.city,
                                    country=user.address.country))


def map_products(payload: dict, customer_id: int) -> Products:
    source = CartResponse.model_validate(payload)
    if source.total != len(source.carts):
        raise ValueError("Incomplete carts page")
    items = []
    for cart in source.carts:
        if cart.userId != customer_id:
            raise ValueError("Mismatched cart owner")
        for item in cart.products:
            gross = money(item.price * item.quantity)
            net = money(gross * (1 - item.discountPercentage / Decimal(100)))
            items.append(Product(id=item.id, name=item.title, quantity=item.quantity,
                                 unitPriceUsd=money(item.price), grossTotalUsd=gross,
                                 discountPercent=item.discountPercentage, netTotalUsd=net))
    gross_total = sum((p.grossTotalUsd for p in items), Decimal("0.00"))
    net_total = sum((p.netTotalUsd for p in items), Decimal("0.00"))
    return Products(cartCount=len(source.carts), itemCount=len(items),
                    units=sum(p.quantity for p in items), items=items,
                    grossTotalUsd=gross_total, discountTotalUsd=gross_total-net_total,
                    netTotalUsd=net_total)


def map_fx(payload: dict, total: Decimal) -> ForeignExchange:
    rates = Rates.model_validate(payload)
    if rates.base != "USD":
        raise ValueError("Unexpected FX base")
    return ForeignExchange(date=rates.date.isoformat(), convertedTotals={
        currency: Conversion(rate=rates.rates[currency], amount=money(total * rates.rates[currency]))
        for currency in ("EUR", "GBP")
    })
