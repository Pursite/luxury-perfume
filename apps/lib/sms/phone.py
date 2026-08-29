import re


_IRANIAN_MOBILE = re.compile(r"^09[0-9]{9}$", flags=re.ASCII)


def normalize_iranian_mobile(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    candidate = value.strip()
    return candidate if _IRANIAN_MOBILE.fullmatch(candidate) else None


def mask_iranian_mobile(value: object) -> str:
    normalized = normalize_iranian_mobile(value)
    if normalized is None:
        return ""
    return f"{normalized[:4]}*****{normalized[-2:]}"
