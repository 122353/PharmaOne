import csv
import io
from datetime import date

REQUIRED = {"medicine_name", "manufacturer", "batch_number", "strength", "expiry_date", "quantity"}
MAX_BYTES = 2 * 1024 * 1024
MAX_ROWS = 5000


def parse_csv(raw: bytes) -> tuple[list[dict], list[dict]]:
    if len(raw) > MAX_BYTES:
        raise ValueError("CSV exceeds 2 MB")
    try:
        decoded = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8") from exc
    reader = csv.DictReader(io.StringIO(decoded, newline=""))
    if not reader.fieldnames or not REQUIRED.issubset(set(reader.fieldnames)):
        raise ValueError("CSV columns must be medicine_name, manufacturer, batch_number, strength, expiry_date, quantity")
    rows, errors = [], []
    for number, row in enumerate(reader, start=2):
        if number > MAX_ROWS + 1:
            raise ValueError("CSV exceeds 5000 rows")
        try:
            data = {key: (row[key] or "").strip() for key in REQUIRED}
            if any(len(value) > 255 for value in data.values()):
                raise ValueError("Field exceeds 255 characters")
            if any(value.lstrip().startswith(("=", "+", "-", "@")) for value in data.values() if value):
                raise ValueError("Spreadsheet formula is not accepted")
            if not data["medicine_name"]:
                raise ValueError("Medicine name is required")
            quantity = int(data["quantity"])
            if quantity < 0 or quantity > 10_000_000:
                raise ValueError("Quantity out of range")
            if data["expiry_date"]:
                date.fromisoformat(data["expiry_date"])
            data["quantity"] = quantity
            data["quality_state"] = "ready" if data["manufacturer"] and data["batch_number"] else "needs_verification"
            rows.append(data)
        except (ValueError, TypeError, KeyError) as exc:
            errors.append({"row": number, "message": str(exc)})
    return rows, errors
