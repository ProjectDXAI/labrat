# Research Sources

## Source Index

| source_id | title | year | url | why_it_matters | linked_branches |
| --- | --- | --- | --- | --- | --- |
| src_sst5_dataset | SetFit SST-5 dataset card | 2024 | https://huggingface.co/datasets/SetFit/sst5 | Defines the runnable dataset and class structure for the example lab. | features, preprocessing, assumption_audit |
| src_sst_original | Recursive Deep Models for Semantic Compositionality Over a Sentiment Treebank | 2013 | https://aclanthology.org/D13-1170/ | Canonical SST benchmark reference and baseline context. | features, model |
| src_kim_cnn | Convolutional Neural Networks for Sentence Classification | 2014 | https://arxiv.org/abs/1408.5882 | Useful historic ceiling reference for non-CPU transformer-free sentiment work. | model |
| src_bow_baselines | Practical linear text classification baselines with TF-IDF and linear margins | 2024 | https://scikit-learn.org/stable/tutorial/text_analytics/working_with_text_data.html | Supports the reduced-lab focus on sparse features, linear classifiers, and fast iteration. | features, model, preprocessing |
| src_class_imbalance | Focal Loss for Dense Object Detection | 2017 | https://arxiv.org/abs/1708.02002 | Motivates imbalance-aware objectives and class weighting ideas, even outside CV. | objectives |
| src_small_data_nlp | SetFit: Efficient Few-Shot Learning Without Prompts | 2022 | https://arxiv.org/abs/2209.11055 | Supports the broader point that small-data sentiment tasks often benefit from representation changes more than brute-force sweeps. | expansion, negative_space |

## Negative Space

- Transformer fine-tuning is intentionally excluded from the runnable lab because the example is meant to be laptop-fast and CPU-only, not because transformers are irrelevant to sentiment classification.
- Retrieval-augmented or embedding-heavy approaches are left out of the runnable loop because they break the “seconds per experiment” constraint, but they remain valid expansion targets in a real lab.
- Richer label redesign and distillation ideas belong to the full production-scale tree, not this reduced example.

## Branch-To-Source Map

- `features`: src_sst_dataset, src_sst_original, src_bow_baselines
- `model`: src_sst_original, src_kim_cnn, src_bow_baselines
- `preprocessing`: src_sst_dataset, src_bow_baselines
- `objectives`: src_class_imbalance
- `ensemble`: src_bow_baselines
- `assumption_audit`: src_sst_dataset, src_sst_original

## Search Notes

- The runnable example is intentionally conservative on compute. The source trail preserves the broader research context so the lab does not mistake “fast to demo” for “best possible sentiment system.”
- Expansion passes should look first at CPU-friendly representation changes, distillation, and stronger sentiment-specific supervision signals before they consider heavy neural retraining.
