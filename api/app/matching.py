"""Conservative pharmaceutical product matching with explainable evidence.

Batch identity and product attributes stay deterministic. Optional language
models can surface a candidate for pharmacist verification, but cannot promote
one to a potential match.
"""

from __future__ import annotations

import os
import re
import unicodedata
from decimal import Decimal, InvalidOperation

from .ml import pharma_match


_MASS_AMOUNT = re.compile(
    r"(?P<value>-?\d+(?:\.\d+)?)\s*(?P<unit>mcg|ug|mg|g)\b",
    flags=re.IGNORECASE,
)
_BASIS_AFTER_AMOUNT = re.compile(
    r"\s*/\s*(?:(?P<count>-?\d+(?:\.\d+)?)\s*)?"
    r"(?P<unit>ml|l|tablet|tablets|tab|capsule|capsules|dose|unit|vial|ampoule|amp)\b",
    flags=re.IGNORECASE,
)
_FORM_SYNONYMS = {
    "tabs": "tablet", "tab": "tablet", "tablets": "tablet",
    "caps": "capsule", "cap": "capsule", "capsules": "capsule",
    "susp": "suspension", "syr": "syrup", "inj": "injection",
}
_DOSAGE_FORMS = {
    "tablet", "capsule", "caplet", "syrup", "suspension", "solution",
    "injection", "injectable", "infusion", "drops", "spray", "cream",
    "ointment", "gel", "lotion", "powder", "granules", "suppository",
    "pessary", "patch", "inhaler", "inhalation", "lozenge", "chewable",
    "oral", "ophthalmic", "otic", "nasal", "topical", "parenteral",
}
_RELEASE_PHRASES = {
    ("extended", "release"): "extended_release",
    ("prolonged", "release"): "prolonged_release",
    ("sustained", "release"): "sustained_release",
    ("controlled", "release"): "controlled_release",
    ("modified", "release"): "modified_release",
    ("delayed", "release"): "delayed_release",
    ("immediate", "release"): "immediate_release",
    ("enteric", "coated"): "enteric_coated",
}
_RELEASE_ALIASES = {
    "xr": "extended_release", "er": "extended_release",
    "sr": "sustained_release", "cr": "controlled_release",
    "mr": "modified_release", "dr": "delayed_release",
}
_IGNORED_PRODUCT_WORDS = {"ip", "the"}
_IGNORED_MANUFACTURER_WORDS = {
    "pvt", "private", "ltd", "limited", "llp", "llc", "inc",
    "incorporated", "co", "company", "pharma", "pharmaceutical",
    "pharmaceuticals", "healthcare", "laboratory", "laboratories", "lab",
    "labs", "industries",
}
def _normalized(value: str | None) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    # Greek mu is often used in place of the Latin micro prefix.
    return value.replace("μ", "u").replace("µ", "u")


def _tokens(value: str | None) -> list[str]:
    return re.findall(r"[^\W_]+", value or "", flags=re.UNICODE)


def _decimal_text(value: Decimal) -> str:
    rendered = format(value.normalize(), "f")
    return rendered.rstrip("0").rstrip(".") if "." in rendered else rendered


def _mass_in_mg(value: str, unit: str) -> Decimal:
    number = Decimal(value)
    factors = {"mg": Decimal("1"), "mcg": Decimal("0.001"), "ug": Decimal("0.001"), "g": Decimal("1000")}
    return number * factors[unit.casefold()]


def _extract_strengths(value: str | None) -> list[tuple[str, str]]:
    """Return ordered, canonical strengths as (value-in-mg, basis) pairs.

    Concentrations are normalized to a per-mL rate. Amounts per tablet/capsule
    remain distinct from an unqualified dose. Unsupported units are left out
    instead of guessed.
    """
    text = _normalized(value)
    strengths: list[tuple[str, str]] = []
    for found in _MASS_AMOUNT.finditer(text):
        try:
            amount = _mass_in_mg(found.group("value"), found.group("unit"))
        except (InvalidOperation, KeyError):
            continue
        if amount <= 0:
            continue

        basis = "dose"
        denominator = _BASIS_AFTER_AMOUNT.match(text, found.end())
        if denominator:
            unit = denominator.group("unit").casefold()
            count = Decimal(denominator.group("count") or "1")
            if count <= 0:
                continue
            if unit in {"ml", "l"}:
                millilitres = count * (Decimal("1000") if unit == "l" else Decimal("1"))
                if millilitres <= 0:
                    continue
                amount /= millilitres
                basis = "per_ml"
            else:
                basis = f"per_{'tablet' if unit in {'tab', 'tablet', 'tablets'} else 'capsule' if unit in {'capsule', 'capsules'} else unit}"
                amount /= count

        strengths.append((_decimal_text(amount), basis))
    return strengths


def _invalid_strength(value: str, parsed: list[tuple[str, str]], *, field=False) -> bool:
    """Do not let missing parse results erase explicit invalid evidence."""
    text = _normalized(value)
    if not text.strip():
        return False
    matches = list(_MASS_AMOUNT.finditer(text))
    if len(parsed) != len(matches):
        return True
    remainder, cursor = [], 0
    for found in matches:
        remainder.append(text[cursor:found.start()])
        denominator = _BASIS_AFTER_AMOUNT.match(text, found.end())
        cursor = denominator.end() if denominator else found.end()
        following = text[cursor:].lstrip()
        if not denominator and following.startswith("/"):
            # A slash may also separate combination component strengths.
            if not _MASS_AMOUNT.match(following[1:].lstrip()):
                return True
    remainder.append(text[cursor:])
    if field:
        # A dedicated strength field must be wholly understood, including
        # partially parsed combinations such as "600mg + 300 milligrams".
        return not matches or bool(re.sub(r"[\s+/,;&()]", "", "".join(remainder)))
    return False


def extract_strengths(value: str | None) -> list[dict[str, str]]:
    """Public, JSON-safe strength parser used by tests and explanations."""
    return [
        {"value_mg": amount, "basis": basis}
        for amount, basis in _extract_strengths(value)
    ]


def batch(value: str | None) -> str:
    """Normalize Unicode and whitespace only; punctuation remains significant."""
    return re.sub(r"\s+", "", _normalized(value)).upper()


def _manufacturer_identity(value: str | None) -> set[str]:
    normalized = _normalized(value)
    # Source records often append a site address after the company name.
    normalized = re.split(r",|;|\.\s+(?=\d)|\b(?:plot|village|vill|road|rd|industrial\s+area|sector|distt|district|address)\b", normalized, maxsplit=1)[0]
    return set(_tokens(normalized)) - _IGNORED_MANUFACTURER_WORDS


def manufacturer_words(value: str | None) -> set[str]:
    """Compatibility helper exposing conservatively normalized maker tokens."""
    return _manufacturer_identity(value)


def _product_attributes(value: str | None) -> dict:
    normalized = _normalized(value)
    # Parse strengths before tokenization so dosage format does not affect name
    # identity. The original strings remain in evidence.
    pieces: list[str] = []
    cursor = 0
    for found in _MASS_AMOUNT.finditer(normalized):
        pieces.append(normalized[cursor:found.start()])
        end = found.end()
        denominator = _BASIS_AFTER_AMOUNT.match(normalized, end)
        if denominator:
            end = denominator.end()
        pieces.append(" ")
        cursor = end
    pieces.append(normalized[cursor:])
    without_strength = "".join(pieces)
    tokens = _tokens(without_strength)
    canonical = [_FORM_SYNONYMS.get(token, token) for token in tokens]

    forms = set(canonical) & _DOSAGE_FORMS
    release: set[str] = set()
    core: list[str] = []
    index = 0
    while index < len(canonical):
        token = canonical[index]
        if index + 1 < len(canonical) and (token, canonical[index + 1]) in _RELEASE_PHRASES:
            release.add(_RELEASE_PHRASES[(token, canonical[index + 1])])
            index += 2
            continue
        if token in _RELEASE_ALIASES:
            release.add(_RELEASE_ALIASES[token])
        elif token not in forms and token not in _IGNORED_PRODUCT_WORDS:
            core.append(token)
        index += 1

    return {"core": core, "forms": sorted(forms), "release": sorted(release)}


def _pharma_score(left: str, right: str) -> dict:
    try:
        return pharma_match(left, right)
    except Exception as exc:
        return {
            "model": "PharmaMatch",
            "available": False,
            "error_type": type(exc).__name__,
            "advisory_only": True,
        }


def compare(item: dict, alert: dict) -> tuple[str, dict]:
    inventory_name = str(item.get("medicine_name") or "")
    source_name = str(alert.get("product_name") or "")
    inventory_product = _product_attributes(inventory_name)
    source_product = _product_attributes(source_name)
    product_equal = bool(inventory_product["core"] and source_product["core"] and inventory_product["core"] == source_product["core"])
    batch_a, batch_b = batch(item.get("batch_number")), batch(alert.get("batch_number"))
    maker_a = _manufacturer_identity(item.get("manufacturer"))
    maker_b = _manufacturer_identity(alert.get("manufacturer"))
    maker_equal = bool(maker_a and maker_b and maker_a == maker_b)

    inventory_name_strengths = _extract_strengths(inventory_name)
    inventory_field_text = str(item.get("strength") or "")
    inventory_field_strengths = _extract_strengths(inventory_field_text)
    source_strengths = _extract_strengths(source_name)
    inventory_name_invalid = _invalid_strength(inventory_name, inventory_name_strengths)
    inventory_field_invalid = _invalid_strength(inventory_field_text, inventory_field_strengths, field=True)
    source_invalid = _invalid_strength(source_name, source_strengths)
    strength_invalid = inventory_name_invalid or inventory_field_invalid or source_invalid
    inventory_strength_conflict = bool(
        inventory_name_strengths
        and inventory_field_strengths
        and inventory_name_strengths != inventory_field_strengths
    )
    if inventory_name_strengths and inventory_field_strengths and not inventory_strength_conflict:
        inventory_strengths = inventory_name_strengths
        strength_sources_duplicate = True
    else:
        inventory_strengths = inventory_name_strengths or inventory_field_strengths
        strength_sources_duplicate = False
    strength_equal = (
        inventory_strengths == source_strengths
        if inventory_strengths and source_strengths
        else None
    )

    form_equal = (
        inventory_product["forms"] == source_product["forms"]
        if inventory_product["forms"] and source_product["forms"]
        else None
    )
    release_equal = (
        inventory_product["release"] == source_product["release"]
        if inventory_product["release"] and source_product["release"]
        else True if not inventory_product["release"] and not source_product["release"] else None
    )

    evidence = {
        "product": {
            "inventory": inventory_name,
            "source": source_name,
            "aligned": product_equal,
            "inventory_ingredients": inventory_product["core"],
            "source_ingredients": source_product["core"],
            "inventory_form": inventory_product["forms"],
            "source_form": source_product["forms"],
            "form_aligned": form_equal,
            "inventory_release": inventory_product["release"],
            "source_release": source_product["release"],
            "release_aligned": release_equal,
        },
        "batch": {
            "inventory": item.get("batch_number"),
            "source": alert.get("batch_number"),
            "exact": bool(batch_a and batch_b and batch_a == batch_b),
        },
        "manufacturer": {
            "inventory": item.get("manufacturer"),
            "source": alert.get("manufacturer"),
            "aligned": maker_equal,
        },
        "strength": {
            "inventory": [{"value_mg": amount, "basis": basis} for amount, basis in inventory_strengths],
            "inventory_name": [{"value_mg": amount, "basis": basis} for amount, basis in inventory_name_strengths],
            "inventory_field": [{"value_mg": amount, "basis": basis} for amount, basis in inventory_field_strengths],
            "inventory_field_text": inventory_field_text,
            "inventory_field_invalid": inventory_field_invalid,
            "inventory_name_invalid": inventory_name_invalid,
            "source_invalid": source_invalid,
            "source": [{"value_mg": amount, "basis": basis} for amount, basis in source_strengths],
            "aligned": strength_equal,
            "inventory_conflict": inventory_strength_conflict,
            "duplicate_sources": strength_sources_duplicate,
        },
        "pharma_match": _pharma_score(inventory_name, source_name),
    }

    if batch_a and batch_b and batch_a != batch_b:
        return "no_identified_match", evidence
    if not inventory_name.strip() or not source_name.strip():
        return "needs_verification", evidence
    if not product_equal:
        # MiniLM can only retrieve an additional candidate when exact batch and
        # manufacturer evidence already agree. Its result is always review-only.
        if (
            os.getenv("PHARMAONE_ENABLE_MINILM", "false").casefold() == "true"
            and batch_a and batch_a == batch_b
            and maker_equal
            and not inventory_strength_conflict
            and not strength_invalid
            and strength_equal is not False
            and form_equal is not False
            and release_equal is not False
        ):
            try:
                from .semantic_matching import semantic_evidence

                semantic = semantic_evidence(inventory_name, source_name)
                evidence["semantic_match"] = semantic
                # This preliminary threshold only retrieves candidates for
                # review. It is not a calibrated probability or match cutoff.
                threshold = float(os.getenv("PHARMAONE_MINILM_THRESHOLD", "0.70"))
                if semantic.get("semantic_similarity", 0.0) >= threshold:
                    evidence["semantic_match"]["candidate_retrieved"] = True
                    return "needs_verification", evidence
            except Exception as exc:
                evidence["semantic_match"] = {
                    "available": False,
                    "error_type": type(exc).__name__,
                    "advisory_only": True,
                }
        return "no_identified_match", evidence

    # Clear formulation or release conflicts mean the product is different.
    if form_equal is False or release_equal is False:
        return "no_identified_match", evidence

    if (
        not batch_a or not batch_b
        or not maker_a or not maker_b or not maker_equal
        or strength_equal is not True
        or inventory_strength_conflict
        or strength_invalid
        or form_equal is None
        or release_equal is None
    ):
        return "needs_verification", evidence

    return "potential_match", evidence
