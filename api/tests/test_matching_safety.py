import pytest

from app.matching import compare, extract_strengths


def product_pair(item_name="Linezolid Tablets IP 600mg", alert_name="Linezolid Tablets IP 600mg", **changes):
    item = {
        "medicine_name": item_name,
        "manufacturer": "Symbiosis Pharmaceuticals Pvt Ltd",
        "batch_number": "TG261185",
        "strength": "",
    }
    alert = {
        "product_name": alert_name,
        "manufacturer": "Symbiosis Pharmaceuticals Pvt. Ltd., Suketi Road, Kala Amb",
        "batch_number": "TG261185",
    }
    item.update(changes.pop("item", {}))
    alert.update(changes.pop("alert", {}))
    assert not changes
    return item, alert


def test_exact_product_batch_manufacturer_and_strength_can_be_potential_match():
    item, alert = product_pair()
    status, evidence = compare(item, alert)
    assert status == "potential_match"
    assert evidence["batch"]["exact"]
    assert evidence["manufacturer"]["aligned"]
    assert evidence["strength"]["aligned"] is True


def test_correct_batch_but_wrong_strength_requires_verification():
    item, alert = product_pair(item_name="Linezolid Tablets IP 300mg", alert_name="Linezolid Tablets IP 600mg")
    assert compare(item, alert)[0] == "needs_verification"


def test_one_sided_missing_strength_requires_verification():
    item, alert = product_pair(
        item_name="Linezolid Tablets IP",
        alert_name="Linezolid Tablets IP 600mg",
    )
    assert compare(item, alert)[0] == "needs_verification"


def test_when_neither_record_states_strength_review_is_required():
    item, alert = product_pair(item_name="Linezolid Tablets IP", alert_name="Linezolid Tablets IP")
    assert compare(item, alert)[0] == "needs_verification"


def test_correct_product_but_wrong_batch_is_not_a_match():
    item, alert = product_pair(item={"batch_number": "TG261186"})
    assert compare(item, alert)[0] == "no_identified_match"


@pytest.mark.parametrize("missing", ["batch_number", "manufacturer"])
def test_missing_batch_or_manufacturer_requires_verification(missing):
    item, alert = product_pair(item={missing: ""})
    assert compare(item, alert)[0] == "needs_verification"


def test_missing_source_batch_requires_verification():
    item, alert = product_pair(alert={"batch_number": ""})
    assert compare(item, alert)[0] == "needs_verification"


def test_name_and_strength_field_duplicate_is_counted_once():
    item, alert = product_pair(item={"strength": "600 mg"})
    status, evidence = compare(item, alert)
    assert status == "potential_match"
    assert evidence["strength"]["duplicate_sources"] is True
    assert evidence["strength"]["inventory"] == [{"value_mg": "600", "basis": "dose"}]


def test_name_and_strength_field_conflict_requires_verification():
    item, alert = product_pair(item={"medicine_name": "Linezolid Tablets IP 300mg", "strength": "600mg"})
    status, evidence = compare(item, alert)
    assert status == "needs_verification"
    assert evidence["strength"]["inventory_conflict"] is True


@pytest.mark.parametrize("strength", [
    "300 milligrams", "0mg/0ml", "600mg/0tablet", "600mg/-1tablet",
    "-600mg", "600mg + 300 milligrams",
])
def test_nonempty_invalid_strength_field_cannot_be_ignored(strength):
    item, alert = product_pair(item={"strength": strength})
    status, evidence = compare(item, alert)
    assert status == "needs_verification"
    assert evidence["strength"]["inventory_field_invalid"] is True


@pytest.mark.parametrize("name", [
    "Linezolid Tablet 100mg/0tablet", "Linezolid Tablet 100mg/-1tablet",
    "Linezolid Tablet 0mg/0ml", "Linezolid Tablet -600mg",
])
def test_invalid_product_strength_does_not_crash_or_promote(name):
    item, alert = product_pair(item_name=name, alert_name=name)
    status, evidence = compare(item, alert)
    assert status == "needs_verification"
    assert evidence["strength"]["inventory_name_invalid"] is True
    assert evidence["strength"]["source_invalid"] is True


def test_zero_denominator_is_safe_even_for_wrong_batch():
    item, alert = product_pair(item_name="Linezolid Tablet 100mg/0tablet", item={"batch_number": "OTHER"})
    assert compare(item, alert)[0] == "no_identified_match"


@pytest.mark.parametrize(
    "item_name,alert_name",
    [
        ("Linezolid Capsule 600mg", "Linezolid Tablet 600mg"),
        ("Linezolid Extended Release Tablet 600mg", "Linezolid Immediate Release Tablet 600mg"),
    ],
)
def test_formulation_or_release_conflict_is_not_a_match(item_name, alert_name):
    item, alert = product_pair(item_name=item_name, alert_name=alert_name)
    assert compare(item, alert)[0] == "no_identified_match"


@pytest.mark.parametrize(
    "item_name,alert_name",
    [
        ("Amoxicillin Tablets 500mg", "Ampicillin Tablets 500mg"),
        ("Amoxicillin Clavulanate Tablets 500mg 125mg", "Amoxicillin Tablets 500mg"),
        ("Amoxicillin Clavulanate Tablets 500mg 125mg", "Amoxicillin Sulbactam Tablets 500mg 125mg"),
    ],
)
def test_similar_active_ingredients_and_combinations_are_not_conflated(item_name, alert_name):
    item, alert = product_pair(item_name=item_name, alert_name=alert_name)
    assert compare(item, alert)[0] == "no_identified_match"


def test_same_combination_with_ordered_component_strengths_can_match():
    item, alert = product_pair(
        item_name="Amoxicillin Clavulanate Tablets 500mg 125mg",
        alert_name="Amoxicillin Clavulanate Tablets 500 mg + 125 mg",
        item={"strength": "500mg + 125mg"},
    )
    assert compare(item, alert)[0] == "potential_match"


@pytest.mark.parametrize(
    "item_name,alert_name",
    [
        ("Linezolid Tablets IP 600mg", "Linezolid Tablets IP 0.6g"),
        ("Vitamin B12 Tablet 600mcg", "Vitamin B12 Tablet 0.6mg"),
        ("Paracetamol Oral Suspension 100mg/5ml", "Paracetamol Oral Suspension 20mg/ml"),
    ],
)
def test_unambiguous_mass_unit_conversions(item_name, alert_name):
    item, alert = product_pair(item_name=item_name, alert_name=alert_name)
    assert compare(item, alert)[0] == "potential_match"


def test_concentration_is_not_conflated_with_a_plain_dose():
    item, alert = product_pair(
        item_name="Paracetamol Oral Suspension 20mg/ml",
        alert_name="Paracetamol Oral Suspension 20mg",
    )
    assert compare(item, alert)[0] == "needs_verification"


def test_strength_parser_preserves_order_and_basis():
    assert extract_strengths("Drug 100mg/5ml + 250mcg") == [
        {"value_mg": "20", "basis": "per_ml"},
        {"value_mg": "0.25", "basis": "dose"},
    ]


@pytest.mark.parametrize(
    "item,alert",
    [
        ({"medicine_name": "", "manufacturer": "M", "batch_number": "B", "strength": "1mg"},
         {"product_name": "Drug 1mg", "manufacturer": "M", "batch_number": "B"}),
        ({"medicine_name": "Drug 1mg", "manufacturer": "M", "batch_number": "B", "strength": "1mg"},
         {"product_name": "", "manufacturer": "M", "batch_number": "B"}),
    ],
)
def test_missing_product_names_require_verification(item, alert):
    assert compare(item, alert)[0] == "needs_verification"


def test_missing_formulation_on_both_records_requires_verification():
    item, alert = product_pair(item_name="Linezolid 600mg", alert_name="Linezolid 600mg")
    assert compare(item, alert)[0] == "needs_verification"


@pytest.mark.parametrize("changes", [
    {"item": {"manufacturer": "Unrelated Labs"}},
    {"item": {"batch_number": "OTHER"}},
    {"item": {"strength": "300mg"}},
    {"item": {"medicine_name": "Linezolld Capsule 600mg"}},
])
def test_semantic_similarity_never_overrides_hard_conflicts(monkeypatch, changes):
    import app.semantic_matching as semantic

    monkeypatch.setenv("PHARMAONE_ENABLE_MINILM", "true")
    def forbidden(*_):
        pytest.fail("semantic encoder must not run across a hard conflict")
    monkeypatch.setattr(semantic, "semantic_evidence", forbidden)
    item, alert = product_pair(item_name="Linezolld Tablet 600mg", **changes)
    assert compare(item, alert)[0] != "potential_match"


def test_semantic_candidate_with_missing_strength_still_requires_review(monkeypatch):
    import app.semantic_matching as semantic

    monkeypatch.setenv("PHARMAONE_ENABLE_MINILM", "true")
    monkeypatch.setattr(semantic, "semantic_evidence", lambda *_: {
        "semantic_similarity": 0.99, "advisory_only": True,
    })
    item, alert = product_pair(item_name="Linezolld Tablet", alert_name="Linezolid Tablet")
    assert compare(item, alert)[0] == "needs_verification"


def test_unicode_whitespace_and_compatibility_forms_normalize():
    item, alert = product_pair(
        item_name="Linezolid\u00a0Tablets IP 600ｍｇ",
        alert_name="Linezolid Tablets IP 600 mg",
        item={"batch_number": "TG\u00a0261185"},
    )
    assert compare(item, alert)[0] == "potential_match"


def test_manufacturer_identity_conflict_requires_verification():
    item, alert = product_pair(item={"manufacturer": "Unrelated Laboratories Pvt Ltd"})
    status, evidence = compare(item, alert)
    assert status == "needs_verification"
    assert evidence["manufacturer"]["aligned"] is False


def test_semantic_candidate_is_verification_only_and_needs_hard_identifiers(monkeypatch):
    import app.semantic_matching as semantic

    monkeypatch.setenv("PHARMAONE_ENABLE_MINILM", "true")
    monkeypatch.setattr(semantic, "semantic_evidence", lambda *_: {
        "model": "test", "semantic_similarity": 0.99, "advisory_only": True,
    })
    item, alert = product_pair(
        item_name="Linezolld Tablets IP 600mg",
        alert_name="Linezolid Tablets IP 600mg",
    )
    status, evidence = compare(item, alert)
    assert status == "needs_verification"
    assert evidence["semantic_match"]["candidate_retrieved"] is True

    item["batch_number"] = "different"
    assert compare(item, alert)[0] == "no_identified_match"


def test_semantic_model_failure_falls_back_without_promoting_a_candidate(monkeypatch):
    import app.semantic_matching as semantic

    monkeypatch.setenv("PHARMAONE_ENABLE_MINILM", "true")

    def unavailable(*_):
        raise RuntimeError("model unavailable")

    monkeypatch.setattr(semantic, "semantic_evidence", unavailable)
    item, alert = product_pair(
        item_name="Ampicillin Tablets IP 600mg",
        alert_name="Linezolid Tablets IP 600mg",
    )

    status, evidence = compare(item, alert)

    assert status == "no_identified_match"
    assert evidence["semantic_match"]["available"] is False
    assert evidence["semantic_match"]["error_type"] == "RuntimeError"
