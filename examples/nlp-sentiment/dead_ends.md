# Dead Ends

From GPT-5.4 Pro research tree design + referenced 2025-2026 papers.

## Architecture
- **Online CoT / ToT / GoT as default serving**: TextReasoningBench finds modest gains from CoT/SC-CoT with frequent degradation from complex reasoning at 10-100x token cost. A 2026 experiment found a small direct-prompt model beat verbose/CoT once cost was counted.
- **LLM-only hot path for fixed-label sentiment**: Production comparisons show encoders are lower-latency (98-147ms vs 326-1394ms) and cheaper while competitive on macro-F1. Violates the <100ms constraint.
- **Embedding + clustering as main classifier**: IT-ticket work reports weak generalization and poor alignment between discovered clusters and operational categories.

## Data
- **Aggressive LLM text cleaning before classification**: W-NUT 2025 found normalization improved cleaning metrics but slightly hurt downstream sequence labeling.
- **Naive minority oversampling**: Causes calibration collapse (Park & Kim 2025).
- **Augmenting before noise audit**: Risks amplifying mislabeled patterns.

## Modeling
- **LSTM/CNN baselines**: Transformers dominate by 3-5% as of 2024.
- **TF-IDF + SVM**: Accuracy ceiling ~78% on multi-class sentiment.
- **Naive post-hoc unknown detection on closed-world classifier**: Remains overconfident on truly novel inputs (UnLLM).
- **Naive label verbalizers for LLM fallback**: Multi-token label-length bias can move F1 substantially and distort confidences.

## Scale
- **GPT-scale models as serving path**: Latency constraint (100ms) kills them immediately.
- **Embedding-only approaches without fine-tuning**: ~72% accuracy on this task class (too generic).
