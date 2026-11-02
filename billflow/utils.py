import re

def validate_phone(phone: str) -> str | None:
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('91') and len(digits) == 12:
        digits = digits[-10:]
    elif digits.startswith('0') and len(digits) == 11:
        digits = digits[-10:]
    if len(digits) < 10:
        return f"Phone too short ({len(digits)} digits). Must be 10 digits."
    if len(digits) > 10:
        return f"Phone too long ({len(digits)} digits). Must be 10 digits."
    return None

def validate_email(email: str) -> str | None:
    if email and re.fullmatch(r'[\w.+-]+@[\w-]+\.[\w.-]+', email) is None:
        return "Invalid email address format."
    return None

def safe_float(s) -> float:
    try:
        return max(0.0, float(s))
    except (ValueError, TypeError):
        return 0.0

def clamp_discount(val) -> float:
    return min(max(safe_float(val), 0.0), 100.0)

def clamp_tax(val) -> float:
    return max(safe_float(val), 0.0)

def rnd(val: float, digits: int = 2) -> float:
    return float(f"{float(val):.{digits}f}")
