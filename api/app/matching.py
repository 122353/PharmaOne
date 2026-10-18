"""Conservative candidate selection; never fuzzy-match a batch identifier."""
import re
import unicodedata
from .ml import pharma_match


def words(value: str | None) -> set[str]:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    return set(re.findall(r"[a-z0-9]+", value)) - {"pvt", "private", "ltd", "limited", "ip", "the"}


def batch(value: str | None) -> str:
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", value or "")).upper()


def manufacturer_words(value: str | None) -> set[str]:
    return words(value) - {"pharma", "pharmaceuticals", "healthcare", "laboratories", "labs", "industries", "company", "co", "inc"}


def compare(item: dict, alert: dict) -> tuple[str, dict]:
    product_a, product_b = words(item.get("medicine_name")), words(alert.get("product_name"))
    batch_a, batch_b = batch(item.get("batch_number")), batch(alert.get("batch_number"))
    maker_a, maker_b = manufacturer_words(item.get("manufacturer")), manufacturer_words(alert.get("manufacturer"))
    product_overlap = bool(product_a and product_b and (product_a == product_b or len(product_a & product_b) / max(len(product_a), len(product_b)) >= .75))
    evidence = {
        "product": {"inventory": item.get("medicine_name"), "source": alert.get("product_name"), "aligned": product_overlap},
        "batch": {"inventory": item.get("batch_number"), "source": alert.get("batch_number"), "exact": bool(batch_a and batch_b and batch_a == batch_b)},
        "manufacturer": {"inventory": item.get("manufacturer"), "source": alert.get("manufacturer"), "aligned": bool(maker_a and maker_b and (maker_a == maker_b or maker_a.issubset(maker_b) or maker_b.issubset(maker_a)))},
        "pharma_match": pharma_match(item.get("medicine_name") or "", alert.get("product_name") or ""),
    }
    if not product_overlap or (batch_a and batch_b and batch_a != batch_b):
        return "no_identified_match", evidence
    if not batch_a or not batch_b or not maker_a or not maker_b or not evidence["manufacturer"]["aligned"]:
        return "needs_verification", evidence
    return "potential_match", evidence
