"""Evaluate matcher variants on the disclosed synthetic dataset only.

Run from api/: python scripts/evaluate_matching.py
MiniLM is loaded from local cache only; this script never downloads a model.
"""

from __future__ import annotations

import ctypes
import json
import math
import os
import platform
import sys
import time
import tracemalloc
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app import matching, ml  # noqa: E402


DATASET_PATH = ROOT / "evaluation" / "matching_cases.json"
REPORT_PATH = ROOT.parent / "docs" / "matching-evaluation.md"
RESULTS_PATH = ROOT / "evaluation" / "latest_results.json"
PHARMAMATCH_THRESHOLD = 0.5


def working_set_mib() -> float | None:
    """Return current process working set where the platform exposes it."""
    if os.name == "nt":
        from ctypes import wintypes

        class MemoryCounters(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("PageFaultCount", wintypes.DWORD),
                ("PeakWorkingSetSize", ctypes.c_size_t),
                ("WorkingSetSize", ctypes.c_size_t),
                ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPagedPoolUsage", ctypes.c_size_t),
                ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                ("PagefileUsage", ctypes.c_size_t),
                ("PeakPagefileUsage", ctypes.c_size_t),
            ]

        counters = MemoryCounters()
        counters.cb = ctypes.sizeof(counters)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.argtypes = []
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(MemoryCounters),
            wintypes.DWORD,
        ]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        if not psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb):
            return None
        return round(counters.WorkingSetSize / (1024 * 1024), 2)

    try:
        import resource

        value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return round(value / (1024 if platform.system() != "Darwin" else 1024 * 1024), 2)
    except (ImportError, AttributeError):
        return None


def binary_metrics(cases: list[dict], predictions: dict, *, label_field="label", prediction_field="potential") -> dict:
    determinate = [case for case in cases if case[label_field] in {"positive", "negative"}]
    def predicts(case: dict) -> bool:
        result = predictions[case["id"]]
        return result[prediction_field] if isinstance(result, dict) else bool(result)

    true_positive = sum(predicts(case) for case in determinate if case[label_field] == "positive")
    false_positive = sum(predicts(case) for case in determinate if case[label_field] == "negative")
    false_negative = sum(not predicts(case) for case in determinate if case[label_field] == "positive")
    precision = true_positive / (true_positive + false_positive) if true_positive + false_positive else 0.0
    recall = true_positive / (true_positive + false_negative) if true_positive + false_negative else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    ambiguous_promoted = sum(
        predicts(case) for case in cases if case[label_field] == "ambiguous"
    )
    return {
        "determinate_count": len(determinate),
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "ambiguous_predicted_positive": ambiguous_promoted,
    }


def percentile95(values: list[float]) -> float:
    return sorted(values)[math.ceil(len(values) * 0.95) - 1] if values else 0.0


def measure(cases: list[dict], evaluate):
    before_rss = working_set_mib()
    latencies_ms = []
    results = []
    tracemalloc.start()
    started_all = time.perf_counter()
    try:
        for case in cases:
            started = time.perf_counter()
            results.append(evaluate(case))
            latencies_ms.append((time.perf_counter() - started) * 1000)
    finally:
        elapsed = time.perf_counter() - started_all
        _, peak_bytes = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    return results, {
        "cases": len(cases),
        "total_seconds": elapsed,
        "mean_latency_ms": sum(latencies_ms) / len(latencies_ms) if latencies_ms else 0.0,
        "p95_latency_ms": percentile95(latencies_ms),
        "python_heap_peak_kib": peak_bytes / 1024,
        "rss_before_mib": before_rss,
        "rss_after_mib": working_set_mib(),
    }


def compare_outcome(case: dict) -> dict:
    status, evidence = matching.compare(case["item"], case["alert"])
    return {
        "status": status,
        "potential": status == "potential_match",
        "retrieved": status in {"potential_match", "needs_verification"},
        "semantic": evidence.get("semantic_match"),
    }


def pipeline_result(cases: list[dict], outcomes: list[dict], runtime: dict) -> dict:
    predictions = {case["id"]: outcome for case, outcome in zip(cases, outcomes)}
    return {
        "runtime": runtime,
        "classification_metrics": binary_metrics(cases, predictions),
        "retrieval_metrics": binary_metrics(cases, predictions, label_field="retrieval_label", prediction_field="retrieved"),
        "predictions": predictions,
    }


def metric_lines(results: dict, metric_name: str) -> list[str]:
    lines = [
        "| Pipeline | Precision | Recall | F1 | TP | FP | FN | Ambiguous predicted positive |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for name, result in results.items():
        m = result[metric_name]
        lines.append(
            f"| {name} | {m['precision']:.3f} | {m['recall']:.3f} | {m['f1']:.3f} | "
            f"{m['true_positive']} | {m['false_positive']} | {m['false_negative']} | {m['ambiguous_predicted_positive']} |"
        )
    return lines


def render_report(dataset: dict, report: dict) -> str:
    cases, results = dataset["cases"], report["pipelines"]
    counts = lambda field: ", ".join(f"{sum(c[field] == label for c in cases)} {label}" for label in ("positive", "negative", "ambiguous"))
    minilm = results["minilm_enhanced"]
    lines = [
        "# PharmaOne matcher evaluation", "",
        f"Dataset: **{dataset['dataset_name']}**, {len(cases)} pairs. Final classification labels: {counts('label')}. Retrieval labels: {counts('retrieval_label')}.",
        f"Data status: {dataset['data_status']}.", "",
        f"Measured at {report['measured_at_utc']} on {report['platform']}, Python {report['python_version']}. Machine-readable measurements and individual predictions: `api/evaluation/latest_results.json`.", "",
        "## Label policy", "",
        "Final classification positive means `potential_match`, which still requires pharmacist review. Known synthetic transcription variants have final label ambiguous and retrieval label positive: their spelling is deliberately altered from a known fixture, and retrieval is useful even though deterministic identity is unproven. Missing fields, conflicting strengths/manufacturers, and unknown brand aliases remain ambiguous. Incompatible batch, ingredient, combination, dosage form or release are negative. Each pair includes a rationale and separate `label`/`retrieval_label` in the dataset.", "",
        "Candidate retrieval positive means the pipeline surfaces a pair for review (`potential_match` or `needs_verification`). The PharmaMatch-only comparison uses its raw name score for both tasks and deliberately bypasses safety gates. Ambiguous labels are excluded from binary precision/recall/F1 and counted separately. These are small synthetic checks, with no independent holdout, threshold tuning, clinical validation or claim of generalization.", "",
        "## Final potential-match classification", "",
    ]
    lines.extend(metric_lines(results, "classification_metrics"))
    lines.extend(["", "## Candidate retrieval", ""])
    lines.extend(metric_lines(results, "retrieval_metrics"))
    lines.extend([
        "", "## Runtime and memory", "",
        "| Measured path | Mean ms/pair | P95 ms/pair | Python heap peak KiB | RSS before / after MiB |",
        "|---|---:|---:|---:|---|",
    ])
    runtime_rows = {name: result["runtime"] for name, result in results.items()}
    if minilm["available"]:
        runtime_rows.update({
            "minilm_matching_cold_embeddings": minilm["cold_matching_runtime"],
            "minilm_encoding_cold_embeddings": minilm["cold_encoding_runtime"],
            "minilm_encoding_warm_cache": minilm["warm_encoding_runtime"],
        })
    for name, runtime in runtime_rows.items():
        lines.append(f"| {name} | {runtime['mean_latency_ms']:.3f} | {runtime['p95_latency_ms']:.3f} | {runtime['python_heap_peak_kib']:.1f} | {runtime['rss_before_mib']} / {runtime['rss_after_mib']} |")
    lines.extend([
        "",
        f"MiniLM availability: `{json.dumps(minilm['availability'], sort_keys=True)}`.",
        f"Cold process model load (includes optional framework imports): **{minilm['model_load_seconds']:.3f} s**. Representative process RSS before / after load: **{minilm['rss_before_load_mib']} / {minilm['rss_after_load_mib']} MiB**.",
        f"Additional semantic candidates requiring verification: **{minilm['candidate_retrievals_needing_verification']}**. Cache after direct encoding benchmark: `{json.dumps(minilm.get('embedding_cache', {}), sort_keys=True)}`.", "",
        "The enhanced pipeline row measures a second pass with cached embeddings. The cold matching pass includes only names that reach semantic retrieval after the deterministic gates; direct encoding separately measures every pair, including pairs the safe matcher excludes. First direct encoding pass starts with an empty embedding cache; repeated names within that pass already benefit from caching. P95 uses nearest rank. Timing includes Python tracing overhead. RSS on Windows is a current working-set sample, not a guaranteed peak; Python heap excludes native framework/model allocations. On non-Windows fallback platforms, `ru_maxrss` is process high-water memory. No inference result is substituted when MiniLM is unavailable: availability is recorded and the enhanced pipeline runs the rules fallback.", "",
        "## Safety and deployment decision", "",
        "Exact batch punctuation remains significant. Manufacturer, explicit strength and dosage form must align deterministically before potential status. Missing strength on both sides, absent formulation or absent name requires verification. Known formulation/release/batch conflicts are excluded; strength/manufacturer conflicts remain review-only. The release must agree whenever stated. MiniLM cannot override any known hard conflict and can only add a review candidate. Unknown similarity is not evidence of ingredient equivalence.", "",
        "The local model is loaded once with `local_files_only=True` on CPU. Embeddings are cached by Unicode-normalized, case-folded, whitespace-normalized names in a 1,024-entry LRU; each cached name is capped at 2,048 characters, vectors are immutable and finite, and failed encodes are retried on later requests. This cache is per process, retains normalized medicine names in memory, and adds bounded memory on top of the native model runtime.", "",
        "Keep the existing lightweight JSON PharmaMatch/PharmaClassify runtime in production. Its logistic/name and Naive Bayes/finding scores remain advisory and require no scikit-learn runtime. MiniLM remains an opt-in local experiment, disabled by default; the optional packages are absent from production requirements. Its measured working set must fit a verified service budget before any deployment decision. The 0.70 semantic and 0.50 PharmaMatch thresholds are preliminary fixed benchmark cutoffs, not calibrated probabilities.", "",
        "The saved SQLite demo was not rematched or rewritten. A future recheck can conservatively downgrade an existing potential match whose source lacks explicit strength/formulation; retained saved statuses are historical results, not proof that the new policy has been applied.", "",
        "## Reproduction", "",
        "From `api/`, run `.\\.venv\\Scripts\\python.exe scripts/evaluate_matching.py`. This script never imports the database, sets the semantic cutoff to 0.70 for reproducibility, forces Hugging Face offline mode, uses only cached model weights, and restores those environment settings afterward. Ordinary matcher tests replace the encoder and never need model weights or network. Optional MiniLM packages must already exist locally to reproduce the semantic rows.", "",
    ])
    return "\n".join(lines)


def main() -> None:
    dataset = json.loads(DATASET_PATH.read_text(encoding="utf-8"))
    cases = dataset["cases"]
    original_pharma_match = matching.pharma_match
    names = ("PHARMAONE_ENABLE_MINILM", "PHARMAONE_MINILM_THRESHOLD", "HF_HUB_OFFLINE", "TRANSFORMERS_OFFLINE")
    original_environment = {name: os.environ.get(name) for name in names}
    os.environ.update(PHARMAONE_ENABLE_MINILM="false", PHARMAONE_MINILM_THRESHOLD="0.70", HF_HUB_OFFLINE="1", TRANSFORMERS_OFFLINE="1")
    matching.pharma_match = lambda *_: {"model": "disabled-for-rules-benchmark", "advisory_only": True}
    results = {}
    try:
        outcomes, runtime = measure(cases, compare_outcome)
        results["rules"] = pipeline_result(cases, outcomes, runtime)

        def name_only(case):
            score = ml.pharma_match(case["item"].get("medicine_name", ""), case["alert"].get("product_name", ""))["product_similarity"]
            return {"score": score, "potential": score >= PHARMAMATCH_THRESHOLD, "retrieved": score >= PHARMAMATCH_THRESHOLD}

        outcomes, runtime = measure(cases, name_only)
        results["pharmamatch_only"] = pipeline_result(cases, outcomes, runtime)
        results["pharmamatch_only"]["threshold"] = PHARMAMATCH_THRESHOLD

        rss_before_load = working_set_mib()
        load_started = time.perf_counter()
        try:
            from app import semantic_matching as semantic

            semantic.get_model()
            availability = {"available": True, "model": "sentence-transformers/all-MiniLM-L6-v2", "local_files_only": True}
        except Exception as exc:
            availability = {"available": False, "reason": type(exc).__name__, "local_files_only": True}
        load_seconds = time.perf_counter() - load_started
        rss_after_load = working_set_mib()
        os.environ["PHARMAONE_ENABLE_MINILM"] = "true" if availability["available"] else "false"
        if availability["available"]:
            semantic._embedding.cache_clear()
        cold_outcomes, cold_runtime = measure(cases, compare_outcome)
        outcomes, runtime = measure(cases, compare_outcome)
        minilm = pipeline_result(cases, outcomes, runtime)
        minilm.update(
            available=availability["available"], availability=availability,
            model_load_seconds=load_seconds, rss_before_load_mib=rss_before_load,
            rss_after_load_mib=rss_after_load, cold_matching_runtime=cold_runtime,
            candidate_retrievals_needing_verification=sum(bool((row.get("semantic") or {}).get("candidate_retrieved")) for row in outcomes),
        )
        if availability["available"]:
            semantic._embedding.cache_clear()
            encode = lambda case: semantic.semantic_similarity(case["item"].get("medicine_name", ""), case["alert"].get("product_name", ""))
            _, minilm["cold_encoding_runtime"] = measure(cases, encode)
            _, minilm["warm_encoding_runtime"] = measure(cases, encode)
            minilm["embedding_cache"] = semantic._embedding.cache_info()._asdict()
        results["minilm_enhanced"] = minilm
    finally:
        matching.pharma_match = original_pharma_match
        for name, value in original_environment.items():
            if value is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = value

    report = {
        "dataset": dataset["dataset_name"], "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(), "python_version": platform.python_version(), "pipelines": results,
    }
    RESULTS_PATH.write_text(json.dumps(report, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    REPORT_PATH.write_text(render_report(dataset, report), encoding="utf-8")
    print(f"Wrote {REPORT_PATH} and {RESULTS_PATH}")
    for name, result in results.items():
        for task in ("classification_metrics", "retrieval_metrics"):
            m = result[task]
            print(f"{name} {task}: precision={m['precision']:.3f} recall={m['recall']:.3f} f1={m['f1']:.3f} fp={m['false_positive']} fn={m['false_negative']}")
    print(f"minilm_available={results['minilm_enhanced']['available']}")


if __name__ == "__main__":
    main()


