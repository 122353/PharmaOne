"""Synthetic model inference and non-negotiable identifier checks."""

from app.matching import compare
from app.ml import pharma_classify, pharma_match


def test_pharmamatch_inference_and_exact_batch_gate():
    item = {"medicine_name": "Linezolid Tablets 600mg", "manufacturer": "Example Labs", "batch_number": "ABC123"}
    alert = {"product_name": "Linezolid Tablets IP 600mg", "manufacturer": "Example Labs", "batch_number": "ABC123"}
    status, evidence = compare(item, alert)
    assert status == "potential_match"
    assert evidence["pharma_match"]["model"] == "PharmaMatch"
    assert evidence["pharma_match"]["product_similarity"] > .5
    assert compare({**item, "batch_number": "ABC124"}, alert)[0] == "no_identified_match"
    assert compare({**item, "manufacturer": ""}, alert)[0] == "needs_verification"
    assert pharma_match("Linezolid 300mg", "Linezolid 600mg")["product_similarity"] < evidence["pharma_match"]["product_similarity"]


def test_pharmaclassify_inference_and_unknown():
    assert pharma_classify("Dissolution")["category"] == "dissolution"
    assert pharma_classify("Assay value below specification")["category"] == "assay_or_content"
    assert pharma_classify("")["category"] == "unclassified"
    assert pharma_classify("Dissolution")["advisory_only"] is True
