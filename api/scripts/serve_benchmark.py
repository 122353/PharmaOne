"""Start one API worker with both JSON model artifacts loaded for local measurement."""

from app.ml import pharma_classify, pharma_match

pharma_match("Linezolid Tablets 600mg", "Linezolid Tablets IP 600mg")
pharma_classify("Dissolution")

import uvicorn  # noqa: E402

uvicorn.run("app.main:app", host="127.0.0.1", port=8001, log_level="error", access_log=False)
