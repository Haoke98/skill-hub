# Training Results Log

## Run 1: 2026-06-30 — Initial 5K sample

**Data**: 5,000 docs from ent-mdsi-v5, filtered to 4,435 usable after preprocessing
**Classes**: 19 chains (filtered by min 3 occurrences)
**Split**: train=3,549 / val=443 / test=443

**Hardware**: RTX 4090, 24GB VRAM, PyTorch 2.12.1+cu130
**Model**: BAAI/bge-small-zh-v1.5, 24M params
**Hyperparams**: batch_size=32, lr=2e-5, epochs=10, max_length=256, dropout=0.1, threshold=0.5

### Validation (best epoch 8)
| Metric | Value |
|--------|-------|
| Micro F1 | 0.4382 |
| Macro F1 | 0.4588 |
| Samples F1 | 0.3132 |
| Hamming Loss | 0.0475 |
| Subset Accuracy | 0.2596 |

### Test Set
| Metric | Value |
|--------|-------|
| Micro F1 | 0.4435 |
| Macro F1 | 0.4833 |
| Samples F1 | 0.3111 |
| Hamming Loss | 0.0480 |

### Per-Class Test F1 (sorted)
| Class | F1 | Support |
|-------|-----|---------|
| 印刷 | 0.800 | 17 |
| 纺织工业 | 0.780 | 25 |
| 造纸 | 0.788 | 18 |
| 医疗服务 | 0.750 | 24 |
| 高效节能 | 0.750 | 3 |
| 轴承 | 0.727 | 9 |
| 食品饮料 | 0.574 | 86 |
| 工业互联网 | 0.533 | 6 |
| 智能医疗 | 0.500 | 6 |
| 物联网 | 0.500 | 4 |
| 酒 | 0.455 | 17 |
| 软件服务 | 0.444 | 24 |
| 现代服务业 | 0.435 | 15 |
| 生命健康 | 0.431 | 89 |
| 超硬材料 | 0.429 | 8 |
| 科技服务 | 0.286 | 10 |
| **数字经济** | **0.000** | 31 |
| **文化体育** | **0.000** | 21 |
| **文化旅游** | **0.000** | 113 |

### Analysis
- **High-frequency classes (文化旅游, 数字经济, 文化体育) get F1=0** because the model's sigmoid outputs stay below 0.5 threshold. The model learned to predict zeros for these — likely due to:
  1. Insufficient training data (only 3.5K samples across 19 classes)
  2. Default threshold too high for imbalanced data
  3. Class weights not aggressive enough for dominant classes
- **Medium-frequency classes (15-25 support) perform well** — the model can distinguish 纺织工业 vs 造纸 vs 印刷 from business scope text
- **Next steps**: (a) export 100K+ samples, (b) try threshold=0.3, (c) per-class threshold tuning

### Label mapping issues
- "大健康" (587 occurrences in 5K sample) not mapped to any MySQL chain — needs manual addition
- Only 19/90 unique ES labels mapped to MySQL standard names (21% coverage)
