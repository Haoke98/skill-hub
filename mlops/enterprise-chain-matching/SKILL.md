---
name: enterprise-chain-matching
description: Build and train ML models that classify enterprises into industry chains and chain-node positions, using business scope text (经营范围) and national economic industry classification codes (国民经济行业分类).
trigger:
  - User asks about classifying enterprises into industry chains / supply chain positions
  - User mentions 产业链匹配, 产业链环节, 经营范围 classification, or 国民经济行业分类 in an ML context
  - Working with the chain-matching data stack (MySQL dc_space_chain + ES ent-mdsi-v5 / MarketSubjects)
  - Designing text classifiers for Chinese business scope descriptions
---

## Data Stack

This project uses a three-tier data stack:

| Tier | Source | What It Holds |
|------|--------|---------------|
| Chain definitions | MySQL `dev_data_zstzpt` | `dc_space_chain` (289 chains), `dc_space_chain_tree` (19,346 nodes, tree-structured) |
| Labeled training data | ES `ent-mdsi-v5` | 29M docs with `affirmChainStr` / `affirmChainNodeStr` (human-verified multi-labels), `businessScopeStr`, `firmIndustryId` |
| Prediction target | ES `MarketSubjects` | 276M docs with `businessScope`, `industry1-4` / `industryCode1-4`, but empty `chainTag` / `chainNodeTag` |

Labels in ES are free-text, semicolon-separated, and multi-valued (e.g. `affirmChainStr: "建工建材;绿色矿业"`). Roughly 40% of docs have >1 chain label. ~15M docs in ent-mdsi-v5 have non-empty chain AND node labels — these are the effective training set.

## ES Connection Pattern

ES 8.3.3 running on HTTPS with self-signed certs. The elasticsearch-py client must be version 7.x or 8.x — **version 9.x is incompatible** and returns:
```
BadRequestError: Accept version must be either version 8 or 7, but found 9
```

**Install the right client:**
```bash
pip install 'elasticsearch>=7.0,<9.0'
```

**Connect with cert verification disabled (internal IP):**
```python
from elasticsearch import Elasticsearch

es = Elasticsearch(
    'https://<host>:9800',
    basic_auth=('<user>', '<password>'),
    verify_certs=False,
    request_timeout=30
)
```

**Pitfall**: ES cluster may be in `red` status with unassigned shards. Cardinality aggregations and heavy scripted aggregations will time out. Prefer `terms` aggregations on `.keyword` fields and simple `count` queries. Scroll/scan for bulk extraction.

## Model Architecture: Two-Tier Classifier

For classifying an enterprise into `(chain, node)` pairs, a flat classifier over thousands of classes is too sparse. Use a two-tier design:

```
经营范围 text + industry codes
          │
          ▼
  ┌───────────────────┐
  │ Tier 1: Chain     │  Multi-label classifier
  │  ~290 classes     │  Base: bge-small-zh-v1.5 (24M)
  │  Loss: Binary CE  │  Input: businessScope + industry codes as text
  └───────┬───────────┘
          │ predicted chains: ["光伏", "新能源"]
          ▼
  ┌───────────────────┐
  │ Tier 2: Node      │  Per-chain classifier OR single model with chain-as-feature
  │  10–380 per chain │  Input: businessScope + industry codes + chain prediction
  │  Loss: Binary CE  │  Output: node(s) within each predicted chain
  └───────┬───────────┘
          │
          ▼
   {"chains": [...], "nodes": {"chain_A": ["node_x"], ...}}
```

**Why two-tier:**
- 290 × 70 avg nodes ≈ 20,000 flat classes — too sparse
- Chain prediction provides a strong prior for node classification
- The industry classification code hierarchy already encodes coarse chain-level signal

**Model choice**: `BAAI/bge-small-zh-v1.5` (24M params). Good Chinese embedding performance, can run on CPU (<10ms inference). Alternatives: `shibing624/text2vec-base-chinese` (110M) for more accuracy at the cost of size.

**Multi-label handling**: Binary cross-entropy loss (not softmax). Semicolon-separated labels in ES become multi-hot vectors.

**Industry codes as features**: Concatenate the codes (industryCode1-4) and their text names (industry1-4) into the input text, not as separate model inputs. The codes' hierarchical semantics (A→B→C→D) are learned from the text representation.

## Data Preprocessing Pipeline

1. **Extract from ent-mdsi-v5**: Pull `businessScopeStr`, `affirmChainStr`, `affirmChainNodeStr`, `firmIndustryId` for docs where both chain and node are non-empty
2. **Split multi-labels**: Parse `;` delimiters into lists
3. **Normalize labels**: Map free-text chain/node names to MySQL dc_space_chain / dc_space_chain_tree canonical names
4. **Filter low-frequency classes**: Drop classes with < N examples (e.g., N=50)
5. **Train/val/test split**: Stratified by chain to handle class imbalance

## Reference Files

- `references/data-landscape.md` — Full field-level inventory of MySQL tables (dc_space_chain, dc_space_chain_tree), ES indices (ent-mdsi-v5, MarketSubjects), connection patterns, and label distributions. Load this before any data exploration or preprocessing work.
- `references/training-results.md` — Log of training runs with metrics, per-class F1 scores, and analysis. Update after each training run to track progress and regressions.
- `templates/train.py` — Ready-to-use Tier 1 multi-label training script. Copy to a project, adjust paths, and run.

## Training Implementation

**Project location**: `/mnt/f/projects/industry-chain-matcher/` — standalone project, NOT part of new-media-tensor.

**Code structure**:
```
industry-chain-matcher/
├── src/
│   ├── data_prep/
│   │   ├── export_labels.py     # MySQL → chain_labels.json
│   │   ├── export_training.py   # ES scroll → training_data.jsonl
│   │   └── preprocess.py        # Clean + split → train/val/test.jsonl
│   ├── train.py                 # Tier 1 chain classifier training
│   └── inference.py             # Inference script
├── data/
│   ├── raw/                     # chain_labels.json, training_data.jsonl
│   └── processed/               # train/val/test.jsonl, label_encoder.json
└── models/                      # best_model.pt, final_model/
```

**NOTE**: `export_labels.py` and `preprocess.py` write data under `src/data/` (relative to their location in `src/data_prep/`). All scripts consuming processed data must resolve to the same directory. Keep paths consistent — prefer `os.path.dirname(os.path.dirname(__file__))` to locate the project root from any script in `src/`.

### Tier 1 Training Pattern

**Model**: `BAAI/bge-small-zh-v1.5` (24M params), pooled via `[CLS]` token → dropout → linear classifier.

**Loss**: `BCEWithLogitsLoss` with `pos_weight` computed per class:
```python
pos_weight[i] = total_label_occurrences / (num_classes * count_of_class_i)
```
This handles class imbalance naturally — rare classes get higher weight.

**Metrics for multi-label** (from `sklearn.metrics`):
- `f1_score(..., average='micro')` — global accuracy weighted by class frequency
- `f1_score(..., average='macro')` — unweighted average across classes  
- `f1_score(..., average='samples')` — per-sample F1 averaged (best for imbalanced multi-label)
- `hamming_loss` — fraction of wrong label predictions (lower is better)
- `subset_accuracy` — exact-match ratio (stringent; often near zero)

**Default hyperparameters** (validation-tuned on RTX 4090 / 24GB):
- `batch_size=32`, `lr=2e-5`, `epochs=10`, `warmup_ratio=0.1`, `weight_decay=0.01`
- `gradient_accumulation_steps=2`, `max_length=256`, `dropout=0.1`, `threshold=0.5`
- Cosine schedule with warmup, `clip_grad_norm=1.0`

**First-run benchmark** (5K samples, 19 classes): sample F1=0.31, hamming loss=0.048. Per-class F1 varies from 0.00 (high-frequency classes like 文化旅游 — model too conservative) to 0.80 (well-represented classes like 纺织工业). Classifier predicts all zeros for dominant classes above threshold=0.5. Fixes: lower threshold, more data, or per-class thresholds.

### GPU Setup (WSL + RTX 4090)

`nvidia-smi` lives at `/usr/lib/wsl/lib/nvidia-smi` on WSL. PyTorch detects CUDA automatically. The RTX 4090 (24GB VRAM) handles 24M-parameter models comfortably with batch_size=32.

## Pitfalls

- **ES version mismatch**: elasticsearch-py 9.x returns `Accept version must be either version 8 or 7, but found 9` against ES 8.3.3. Always use `pip install 'elasticsearch>=7.0,<9.0'`.
- **ES cluster status**: The SLRC cluster may be `red` with unassigned shards. Heavy aggregations (cardinality, scripted) will time out. Use simple `terms` aggregations on `.keyword` fields or scroll-based extraction for bulk data pulls. **Also**: count queries on red clusters may return inaccurate totals — don't rely on `es.count()` for datasets with empty-string filtering; validate with actual scroll output.
- **ES empty-string filtering**: `must_not: [{"term": {"affirmChainStr": ""}}]` may not correctly filter empty strings on `text` fields (vs `keyword`). Use a post-scroll check (`if not affirm_chain.strip(): continue`) as a safety net.
- **Multi-label format**: Labels in ES are semicolon-separated free text, not structured arrays. Split on `;` and trim whitespace before training.
- **Empty labels**: ~75% of ent-mdsi-v5 docs may have empty `affirmChainStr` despite the field existing. Filter these in the export loop, not in the ES query. Budget for high skip rates when exporting.
- **Label normalization**: ES free-text chain/node names may not exactly match MySQL canonical names. Build a mapping table or use fuzzy matching before training. Notable gap: "大健康" appears frequently in ES but may not exist in MySQL — either add it to the mapping or treat as a custom label.
- **PyTorch 2.12 API**: `torch.cuda.get_device_properties(0).total_mem` was renamed to `.total_memory` in PyTorch 2.12. Use `total_memory` for forward compatibility.
- **Path consistency**: `preprocess.py` (in `src/data_prep/`) writes to `src/data/` by default. `train.py` (in `src/`) must resolve to the same directory. Use a single `DATA_DIR` resolution approach or explicitly set paths with `--data-dir`.
- **Label cardinality**: Most samples have 1-2 chain labels. 5+ labels per sample is rare. Set `max_labels_per_sample=5` in preprocessing to avoid multi-label explosion.
