"""Server-only Sarvam adapter. Provider responses and credentials never enter logs."""
import json
import re
import time
from dataclasses import dataclass

import httpx


SUPPORTED_TRANSLATION_LANGUAGES = {
    "as-IN", "bn-IN", "brx-IN", "doi-IN", "en-IN", "gu-IN", "hi-IN", "kn-IN",
    "ks-IN", "kok-IN", "mai-IN", "ml-IN", "mni-IN", "mr-IN", "ne-IN", "od-IN",
    "pa-IN", "sa-IN", "sat-IN", "sd-IN", "ta-IN", "te-IN", "ur-IN",
}


class SarvamError(RuntimeError):
    def __init__(self, message: str, *, code: str = "provider_error"):
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class ChatCompletion:
    text: str
    finish_reason: str | None
    completion_tokens: int | None


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        name: {"type": "string", "description": description}
        for name, description in {
            "medicine_name": "Medicine name printed on the package, exactly as written; blank if absent",
            "manufacturer": "Manufacturer name printed on the package, exactly as written; blank if absent",
            "batch_number": "Batch or lot number printed on the package, exactly as written; blank if absent",
            "strength": "Medicine strength printed on the package; blank if absent",
            "manufacturing_date": "Manufacturing date as printed; blank if absent",
            "expiry_date": "Expiry date as printed; blank if absent",
            "original_text": "Exact visible text containing the medicine, manufacturer and batch identifiers, preserving the original script",
        }.items()
    },
}


class SarvamClient:
    def __init__(self, key: str, *, http: httpx.Client | None = None):
        if not key:
            raise SarvamError("Sarvam is not configured")
        self.key = key
        self.http = http

    def _request(self, method: str, path: str, **kwargs) -> dict:
        owned = self.http is None
        client = self.http or httpx.Client(base_url="https://api.sarvam.ai", timeout=httpx.Timeout(30, connect=10))
        try:
            for attempt in range(2):
                try:
                    response = client.request(method, path, headers={"api-subscription-key": self.key}, **kwargs)
                    # Retry throttled reads only. A paid POST has one submission;
                    # retrying an ambiguous accepted job could duplicate charges.
                    if response.status_code == 429 and attempt == 0 and method.upper() == "GET":
                        time.sleep(0.5)
                        continue
                    if response.status_code >= 400:
                        code = "rate_limited" if response.status_code == 429 else "provider_http_error"
                        raise SarvamError(f"Sarvam request failed (HTTP {response.status_code})", code=code)
                    try:
                        payload = response.json()
                    except ValueError:
                        raise SarvamError("Sarvam returned invalid JSON", code="invalid_response") from None
                    if not isinstance(payload, dict):
                        raise SarvamError("Sarvam returned an invalid response", code="invalid_response")
                    return payload
                except httpx.TimeoutException:
                    raise SarvamError("Sarvam timed out", code="timeout") from None
                except httpx.TransportError:
                    raise SarvamError("Sarvam is temporarily unavailable", code="transport_error") from None
        finally:
            if owned:
                client.close()
        raise SarvamError("Sarvam is temporarily unavailable")

    def chat(self, messages: list[dict]) -> str:
        return self.chat_with_metadata(messages).text

    def chat_with_metadata(self, messages: list[dict]) -> ChatCompletion:
        payload = self._request("POST", "/v1/chat/completions", json={
            "model": "sarvam-105b", "messages": messages[-6:], "temperature": 0,
            "reasoning_effort": None, "max_tokens": 400,
        })
        try:
            choice = payload["choices"][0]
            finish_reason = choice.get("finish_reason")
            if finish_reason == "length":
                raise SarvamError("Sarvam response reached its token limit", code="truncated")
            if finish_reason != "stop":
                raise SarvamError("Sarvam did not complete a text answer", code="invalid_response")
            answer = choice["message"]["content"]
            if not isinstance(answer, str) or not answer.strip():
                raise ValueError()
            usage = payload.get("usage") or {}
            tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
            return ChatCompletion(answer[:6000].strip(), finish_reason, tokens if isinstance(tokens, int) else None)
        except (KeyError, IndexError, TypeError, ValueError):
            raise SarvamError("Sarvam returned an invalid chat response", code="invalid_response") from None

    def translate(self, value: str, target_language: str, source_language: str = "en-IN") -> str:
        if target_language not in SUPPORTED_TRANSLATION_LANGUAGES or source_language not in SUPPORTED_TRANSLATION_LANGUAGES:
            raise ValueError("Unsupported language")
        payload = self._request("POST", "/translate", json={
            "input": value[:2000], "source_language_code": source_language,
            "target_language_code": target_language, "model": "sarvam-translate:v1",
        })
        result = payload.get("translated_text")
        if not isinstance(result, str) or not result.strip():
            raise SarvamError("Sarvam returned an invalid translation")
        return result

    def ocr(self, raw: bytes, filename: str, content_type: str, *, poll_interval: float = 1.5) -> dict:
        created = self._request("POST", "/doc-ai/v1/job/extract", files={
            "file": (filename, raw, content_type),
        }, data={"schema": json.dumps(EXTRACTION_SCHEMA), "output_format": "json"})
        job_id = created.get("job_id")
        if not isinstance(job_id, str) or not re.fullmatch(r"[a-zA-Z0-9_-]{1,100}", job_id):
            raise SarvamError("Sarvam returned an invalid OCR job")
        for _ in range(12):
            status = self._request("GET", f"/doc-ai/v1/job/{job_id}/status").get("status")
            if status in ("completed", "partially_completed"):
                result = self._request("GET", f"/doc-ai/v1/job/{job_id}/results")
                fields = result.get("result")
                if not isinstance(fields, dict):
                    raise SarvamError("Sarvam returned an invalid OCR result")
                return {"fields": {key: str(fields.get(key) or "")[:700] for key in EXTRACTION_SCHEMA["properties"]},
                        "original": {"result": fields, "annotations": result.get("annotations", {})}, "status": status}
            if status in ("failed", "rejected"):
                raise SarvamError("Sarvam OCR could not process this image")
            time.sleep(poll_interval)
        raise SarvamError("Sarvam OCR did not finish within the processing limit")
