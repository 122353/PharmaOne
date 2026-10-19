
import re
import pandas as pd


def normalize_text(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", " ", str(value)).strip().casefold()


def normalize_manufacturer(value):
    name = normalize_text(value)
    name = re.sub(r"[^a-z0-9 ]", " ", name)
    name = re.sub(r"\b(pvt|private|ltd|limited)\b", " ", name)
    return re.sub(r"\s+", " ", name).strip()


def extract_strength(text):
    return sorted(
        float(value)
        for value in re.findall(
            r"(\d+(?:\.\d+)?)\s*mg\b",
            str(text).lower()
        )
    )


def run_pharmaone_matching(stock, reports, model, threshold=0.70):
    stock = stock.reset_index(drop=True)
    reports = reports.reset_index(drop=True)

    if stock.empty or reports.empty:
        return pd.DataFrame()

    inventory_embeddings = model.encode(
        stock["medicine_name"].fillna("").tolist(),
        normalize_embeddings=True
    )

    regulatory_embeddings = model.encode(
        reports["product_name"].fillna("").tolist(),
        normalize_embeddings=True
    )

    similarities = inventory_embeddings @ regulatory_embeddings.T
    results = []

    for i, item in stock.iterrows():
        for j, report in reports.iterrows():
            score = float(similarities[i, j])

            inventory_batch = normalize_text(item.get("batch_number", ""))
            regulatory_batch = normalize_text(report.get("batch_number", ""))

            item_strength = extract_strength(item["medicine_name"])

            if not item_strength:
                item_strength = extract_strength(item.get("strength", ""))

            report_strength = extract_strength(report["product_name"])

            item_mfr = normalize_manufacturer(item.get("manufacturer", ""))
            report_mfr = normalize_manufacturer(report.get("manufacturer", ""))

            manufacturer_match = (
                bool(item_mfr)
                and bool(report_mfr)
                and (
                    item_mfr == report_mfr
                    or report_mfr.startswith(item_mfr + " ")
                )
            )

            if not inventory_batch or not regulatory_batch:
                status = "BATCH_UNVERIFIED"
            elif inventory_batch != regulatory_batch:
                status = "BATCH_MISMATCH"
            elif item_strength and report_strength and item_strength != report_strength:
                status = "STRENGTH_MISMATCH"
            elif not manufacturer_match:
                status = "MANUFACTURER_UNVERIFIED"
            elif not item_strength or not report_strength:
                status = "STRENGTH_UNVERIFIED"
            elif score < threshold:
                status = "NAME_REVIEW_REQUIRED"
            else:
                status = "POTENTIAL_MATCH"

            results.append({
                "inventory_id": i,
                "cdsco_id": j,
                "medicine": item["medicine_name"],
                "regulatory_medicine": report["product_name"],
                "batch": inventory_batch,
                "semantic_similarity": round(score, 4),
                "status": status,
                "quality_issue": report.get("quality_issue", "")
            })

    return pd.DataFrame(results)
