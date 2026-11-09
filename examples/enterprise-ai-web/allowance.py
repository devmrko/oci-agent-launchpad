"""Shared travel allowance rules, independent of delivery interface and OCI."""


def estimate(nights):
    if type(nights) is not int or not 1 <= nights <= 10:
        raise ValueError("숙박 일수는 1~10 사이의 정수여야 합니다.")
    return {"nights": nights, "nightly_limit": 100000, "amount": nights * 100000,
            "formula": f"100,000원 × {nights}박 = {nights * 100000:,}원", "model_used": False}
