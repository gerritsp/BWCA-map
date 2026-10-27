"""Canonical Minnesota DOW identifiers shared by data and application builds."""
from decimal import Decimal, InvalidOperation


def normalize_dow(value):
    """Return eight digits, or None for absent/invalid IDs.

    A 0.000001 absolute tolerance accommodates floating point storage noise;
    this is deliberately not a relative tolerance at million-sized lake IDs.
    """
    if value is None or isinstance(value, bool):
        return None
    try:
        number = Decimal(str(value).strip())
        if not number.is_finite():
            return None
        integer = number.to_integral_value()
        if abs(number - integer) > Decimal("0.000001"):
            return None
        if integer < 0 or integer > 99999999:
            return None
        return str(int(integer)).zfill(8)
    except (InvalidOperation, ValueError, TypeError):
        return None
