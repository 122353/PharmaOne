import httpx
import pytest

from app.sarvam import SarvamClient, SarvamError


def test_chat_and_translation_use_server_header_and_validate_response():
    requests = []

    def handler(request):
        requests.append(request)
        if request.url.path == "/v1/chat/completions":
            return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "Verified evidence only."}}]})
        return httpx.Response(200, json={"translated_text": "प्रमाण देखें"})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sarvam.ai") as http:
        client = SarvamClient("test-secret", http=http)
        assert client.chat([{"role": "user", "content": "Explain"}]) == "Verified evidence only."
        assert client.translate("Review evidence", "hi-IN") == "प्रमाण देखें"
    assert len(requests) == 2
    assert all(request.headers["api-subscription-key"] == "test-secret" for request in requests)
    assert b"test-secret" not in requests[0].content


def test_ocr_preserves_structured_result_and_annotations():
    paths = []

    def handler(request):
        paths.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(201, json={"job_id": "job-1", "status": "pending"})
        if request.url.path.endswith("/status"):
            return httpx.Response(200, json={"status": "completed"})
        return httpx.Response(200, json={"result": {"medicine_name": "Drug A", "batch_number": "B12"}, "annotations": {"batch_number": {"confidence": 0.8}}})

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sarvam.ai") as http:
        result = SarvamClient("test-secret", http=http).ocr(b"\x89PNG\r\n\x1a\nabc", "pack.png", "image/png", poll_interval=0)
    assert result["fields"]["batch_number"] == "B12"
    assert result["original"]["annotations"]["batch_number"]["confidence"] == 0.8
    assert paths == ["/doc-ai/v1/job/extract", "/doc-ai/v1/job/job-1/status", "/doc-ai/v1/job/job-1/results"]


def test_provider_errors_hide_secret():
    def handler(request):
        return httpx.Response(403, text="rejected test-secret")

    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sarvam.ai") as http:
        with pytest.raises(SarvamError) as error:
            SarvamClient("test-secret", http=http).chat([{"role": "user", "content": "Hi"}])
    assert "test-secret" not in str(error.value)


def test_ambiguous_provider_failure_is_not_retried():
    calls=[]
    def handler(request):
        calls.append(request)
        return httpx.Response(503, json={"detail":"unavailable"})
    with httpx.Client(transport=httpx.MockTransport(handler),base_url="https://api.sarvam.ai") as http:
        with pytest.raises(SarvamError):
            SarvamClient("test-secret",http=http).chat([{"role":"user","content":"Hi"}])
    assert len(calls)==1


def test_chat_disables_reasoning_and_reads_completion_metadata():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"choices": [{"finish_reason": "stop", "message": {"content": "Batch VRNT-933 requires verification."}}],
                                         "usage": {"completion_tokens": 38}})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sarvam.ai") as http:
        result = SarvamClient("test-secret", http=http).chat_with_metadata([{"role": "user", "content": "Explain"}])
    assert result.text == "Batch VRNT-933 requires verification."
    assert result.finish_reason == "stop"
    assert result.completion_tokens == 38
    body = __import__("json").loads(requests[0].content)
    assert body["model"] == "sarvam-105b"
    assert body["max_tokens"] == 400
    assert body["reasoning_effort"] is None


@pytest.mark.parametrize("response,code", [
    (httpx.Response(200, json={"choices": [{"finish_reason": "length", "message": {"content": "Batch VRNT-933"}}]}), "truncated"),
    (httpx.Response(200, content=b"not json"), "invalid_response"),
    (httpx.Response(200, json={"choices": []}), "invalid_response"),
    (httpx.Response(200, json={"choices": [{"message": {"content": "Batch VRNT-933"}}]}), "invalid_response"),
    (httpx.Response(403, text="test-secret"), "provider_http_error"),
])
def test_chat_failure_is_classified_without_leaking_provider_body(response, code):
    with httpx.Client(transport=httpx.MockTransport(lambda _: response), base_url="https://api.sarvam.ai") as http:
        with pytest.raises(SarvamError) as error:
            SarvamClient("test-secret", http=http).chat_with_metadata([{"role": "user", "content": "Explain"}])
    assert error.value.code == code
    assert "test-secret" not in str(error.value)


def test_chat_timeout_is_classified():
    def timeout(_):
        raise httpx.ReadTimeout("timed out")
    with httpx.Client(transport=httpx.MockTransport(timeout), base_url="https://api.sarvam.ai") as http:
        with pytest.raises(SarvamError) as error:
            SarvamClient("test-secret", http=http).chat_with_metadata([{"role": "user", "content": "Explain"}])
    assert error.value.code == "timeout"


def test_rate_limited_paid_chat_is_not_retried():
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(429, text="slow down")
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sarvam.ai") as http:
        with pytest.raises(SarvamError) as error:
            SarvamClient("test-secret", http=http).chat_with_metadata([{"role": "user", "content": "Explain"}])
    assert error.value.code == "rate_limited"
    assert len(calls) == 1


def test_translation_supports_hindi_to_english_without_identifier_changes():
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json={"translated_text": "Dissolution finding"})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sarvam.ai") as http:
        translated = SarvamClient("test-secret", http=http).translate("घुलनशीलता निष्कर्ष", "en-IN", "hi-IN")
    assert translated == "Dissolution finding"
    body = __import__("json").loads(requests[0].content)
    assert body["source_language_code"] == "hi-IN"
    assert body["target_language_code"] == "en-IN"
    assert body["model"] == "sarvam-translate:v1"


def test_ocr_fails_after_bounded_polling_without_inventing_fields():
    calls = []
    def handler(request):
        calls.append(request.url.path)
        if request.method == "POST":
            return httpx.Response(201, json={"job_id": "synthetic-job"})
        return httpx.Response(200, json={"status": "pending"})
    with httpx.Client(transport=httpx.MockTransport(handler), base_url="https://api.sarvam.ai") as http:
        with pytest.raises(SarvamError, match="processing limit"):
            SarvamClient("test-secret", http=http).ocr(b"synthetic", "test.png", "image/png", poll_interval=0)
    assert len(calls) == 13
