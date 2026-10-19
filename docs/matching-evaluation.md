# PharmaOne matcher evaluation

Dataset: **PharmaOne synthetic matcher v2**, 24 pairs. Final classification labels: 6 positive, 5 negative, 13 ambiguous. Retrieval labels: 9 positive, 5 negative, 10 ambiguous.
Data status: synthetic evaluation cases; not CDSCO evidence and not clinical validation.

Measured at 2026-10-19T09:39:22.324001+00:00 on Windows-10-10.0.26200-SP0, Python 3.11.9. Machine-readable measurements and individual predictions: `api/evaluation/latest_results.json`.

## Label policy

Final classification positive means `potential_match`, which still requires pharmacist review. Known synthetic transcription variants have final label ambiguous and retrieval label positive: their spelling is deliberately altered from a known fixture, and retrieval is useful even though deterministic identity is unproven. Missing fields, conflicting strengths/manufacturers, and unknown brand aliases remain ambiguous. Incompatible batch, ingredient, combination, dosage form or release are negative. Each pair includes a rationale and separate `label`/`retrieval_label` in the dataset.

Candidate retrieval positive means the pipeline surfaces a pair for review (`potential_match` or `needs_verification`). The PharmaMatch-only comparison uses its raw name score for both tasks and deliberately bypasses safety gates. Ambiguous labels are excluded from binary precision/recall/F1 and counted separately. These are small synthetic checks, with no independent holdout, threshold tuning, clinical validation or claim of generalization.

## Final potential-match classification

| Pipeline | Precision | Recall | F1 | TP | FP | FN | Ambiguous predicted positive |
|---|---:|---:|---:|---:|---:|---:|---:|
| rules | 1.000 | 1.000 | 1.000 | 6 | 0 | 0 | 0 |
| pharmamatch_only | 0.667 | 0.333 | 0.444 | 2 | 1 | 4 | 5 |
| minilm_enhanced | 1.000 | 1.000 | 1.000 | 6 | 0 | 0 | 0 |

## Candidate retrieval

| Pipeline | Precision | Recall | F1 | TP | FP | FN | Ambiguous predicted positive |
|---|---:|---:|---:|---:|---:|---:|---:|
| rules | 1.000 | 0.667 | 0.800 | 6 | 0 | 3 | 9 |
| pharmamatch_only | 0.667 | 0.222 | 0.333 | 2 | 1 | 7 | 5 |
| minilm_enhanced | 1.000 | 1.000 | 1.000 | 9 | 0 | 0 | 10 |

## Runtime and memory

| Measured path | Mean ms/pair | P95 ms/pair | Python heap peak KiB | RSS before / after MiB |
|---|---:|---:|---:|---|
| rules | 0.597 | 0.655 | 23.6 | 17.1 / 17.25 |
| pharmamatch_only | 0.396 | 0.498 | 10.8 | 17.26 / 17.35 |
| minilm_enhanced | 0.464 | 0.770 | 7.9 | 527.57 / 527.57 |
| minilm_matching_cold_embeddings | 15.834 | 80.782 | 141.6 | 519.75 / 527.57 |
| minilm_encoding_cold_embeddings | 29.737 | 69.585 | 294.7 | 527.57 / 528.59 |
| minilm_encoding_warm_cache | 0.116 | 0.179 | 1.6 | 528.59 / 528.59 |

MiniLM availability: `{"available": true, "local_files_only": true, "model": "sentence-transformers/all-MiniLM-L6-v2"}`.
Cold process model load (includes optional framework imports): **24.833 s**. Representative process RSS before / after load: **17.35 / 519.75 MiB**.
Additional semantic candidates requiring verification: **4**. Cache after direct encoding benchmark: `{"currsize": 21, "hits": 71, "maxsize": 1024, "misses": 21}`.

The enhanced pipeline row measures a second pass with cached embeddings. The cold matching pass includes only names that reach semantic retrieval after the deterministic gates; direct encoding separately measures every pair, including pairs the safe matcher excludes. First direct encoding pass starts with an empty embedding cache; repeated names within that pass already benefit from caching. P95 uses nearest rank. Timing includes Python tracing overhead. RSS on Windows is a current working-set sample, not a guaranteed peak; Python heap excludes native framework/model allocations. On non-Windows fallback platforms, `ru_maxrss` is process high-water memory. No inference result is substituted when MiniLM is unavailable: availability is recorded and the enhanced pipeline runs the rules fallback.

## Safety and deployment decision

Exact batch punctuation remains significant. Manufacturer, explicit strength and dosage form must align deterministically before potential status. Missing strength on both sides, absent formulation or absent name requires verification. Known formulation/release/batch conflicts are excluded; strength/manufacturer conflicts remain review-only. The release must agree whenever stated. MiniLM cannot override any known hard conflict and can only add a review candidate. Unknown similarity is not evidence of ingredient equivalence.

The local model is loaded once with `local_files_only=True` on CPU. Embeddings are cached by Unicode-normalized, case-folded, whitespace-normalized names in a 1,024-entry LRU; each cached name is capped at 2,048 characters, vectors are immutable and finite, and failed encodes are retried on later requests. This cache is per process, retains normalized medicine names in memory, and adds bounded memory on top of the native model runtime.

Keep the existing lightweight JSON PharmaMatch/PharmaClassify runtime in production. Its logistic/name and Naive Bayes/finding scores remain advisory and require no scikit-learn runtime. MiniLM remains an opt-in local experiment, disabled by default; the optional packages are absent from production requirements. Its measured working set must fit a verified service budget before any deployment decision. The 0.70 semantic and 0.50 PharmaMatch thresholds are preliminary fixed benchmark cutoffs, not calibrated probabilities.

The saved SQLite demo was not rematched or rewritten. A future recheck can conservatively downgrade an existing potential match whose source lacks explicit strength/formulation; retained saved statuses are historical results, not proof that the new policy has been applied.

## Reproduction

From `api/`, run `.\.venv\Scripts\python.exe scripts/evaluate_matching.py`. This script never imports the database, sets the semantic cutoff to 0.70 for reproducibility, forces Hugging Face offline mode, uses only cached model weights, and restores those environment settings afterward. Ordinary matcher tests replace the encoder and never need model weights or network. Optional MiniLM packages must already exist locally to reproduce the semantic rows.
