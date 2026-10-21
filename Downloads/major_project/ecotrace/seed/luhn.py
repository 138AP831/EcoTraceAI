"""Luhn helpers for synthetic IMEI generation (TAC prefix '99', 15 digits)."""


def luhn_check_digit(payload: str) -> int:
    """Compute the Luhn check digit for a digit string that will precede it."""
    total = 0
    rev = payload[::-1]
    for i, ch in enumerate(rev):
        d = int(ch)
        if i % 2 == 0:  # positions doubled (rightmost of payload == pos 2 of full number)
            d2 = d * 2
            if d2 > 9:
                d2 -= 9
            total += d2
        else:
            total += d
    return (10 - (total % 10)) % 10


def make_imei(rng) -> str:
    """Return a Luhn-valid 15-digit IMEI starting with '99' (non-real TAC)."""
    body = "99" + "".join(str(rng.randint(0, 9)) for _ in range(12))  # 14 digits
    return body + str(luhn_check_digit(body))


def is_valid_imei(imei: str) -> bool:
    if not isinstance(imei, str) or len(imei) != 15 or not imei.isdigit():
        return False
    if not imei.startswith("99"):
        return False
    return luhn_check_digit(imei[:14]) == int(imei[14])
