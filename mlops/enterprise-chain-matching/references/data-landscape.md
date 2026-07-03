# Data Landscape: Enterprise Chain Matching

## MySQL: dev_data_zstzpt

### dc_space_chain (产业链名单)
- **Rows**: 298
- **Key fields**:
  - `id` (varchar): chain ID, PK — e.g. `'1'` for 信创
  - `cate_name` (varchar): top-level category — e.g. '信息技术', '绿色矿业', '新能源'
  - `chain_name` (varchar): chain display name — e.g. '信创', '软件服务', '轴承'
  - `space_type` (int): 1=自治区, 2=兵团, 3=第三方
  - `statistics_data` (text): JSON with `totalFirmNum` and `firmTopStatistic`
- **Chains with tree nodes**: 289 (cross-referenced via dc_space_chain_tree.main_chain_id)

### dc_space_chain_tree (产业链节点)
- **Rows**: 19,346
- **Tree structure**: `parents_node_id` links to parent, `'0'` = root
- **Key fields**:
  - `id` (varchar): node ID
  - `main_chain_id` (varchar): FK → dc_space_chain.id
  - `chain_node_name` (varchar): human-readable node name — e.g. '基础软件', '笔记本'
  - `chain_node` (varchar): INB code — e.g. 'INB000901', 'INB0009020103'
  - `parents_chain_node` (varchar): parent INB code
  - `chain_type` (tinyint): mostly NULL; values 1 or 5 when set
  - `chain_stream` (tinyint): mostly NULL; values 1/2/3 when set — likely upstream/downstream
- **Nodes per chain**: ranges from ~170 to ~383 (top chains)
- **Depth**: 3-4 levels deep (e.g., 基础软件 → 信息安全 → 物联网安全 → 具体产品)

### Notable chains (by node count)
- 绿色矿业: 383 nodes
- 新能源和电力: 297 nodes
- 绿色化工产业: 296 nodes
- 化纤纺织一体化产业链: 285 nodes
- 工程机械: 284 nodes

---

## Elasticsearch: SLRC cluster (8.3.3)

**Cluster**: `SLRC`, 6 nodes, 4 data nodes. Status observed as `red` with 1,313 unassigned shards.

### Index: ent-mdsi-v5 (TRAINING DATA)
- **Docs**: ~29M (29,250,035 at time of inspection)
- **Label coverage**: 100% of docs have `affirmChainStr` and `affirmChainNodeStr` fields, but ~11.4M have empty `affirmChainStr` and ~13.7M have empty `affirmChainNodeStr`
- **Effective training set**: ~15M docs with BOTH non-empty chain AND node labels
- **Key fields for training**:
  - `businessScopeStr` (text): 经营范围 — the main text feature
  - `affirmChainStr` (text): human-verified chain label — e.g. `"建工建材;绿色矿业"` (semicolon-separated multi-label)
  - `affirmChainNodeStr` (text): human-verified node label — e.g. `"生铁;冶炼加工"`
  - `affirmChainCateStr` (text): category-level label — e.g. `"建工建材;绿色矿业"`
  - `firmIndustryId` (long): numeric industry code — e.g. `158`
  - `firmIndustryInfo` (keyword): often None, sometimes has text like `"金属制卫生器具制造"`
  - `chainNameStr` (text): another chain label field (sometimes differs from affirmChainStr)
  - `chainNodeTag` (text): node tag
  - `firmName` (text): company name
  - `businessAddress` (keyword): company address
  - `firmType` (text): enterprise type
  - `dimensionalityStr` (text): dimension tags — e.g. `"电子商务;实号;涉诉风险"`
- **Top chain categories (affirmChainCateStr)**:
  - (empty): 11.4M
  - 其他: 2.7M
  - 医疗健康: 1.3M
  - 信息技术: 1.2M
  - 服务业: 667K
- **Multi-label**: common to have semicolon-chained values — e.g. `"信息技术;服务业"` (636K docs)

### Index: MarketSubjects (PREDICTION TARGET)
- **Docs**: ~276M (across multiple shards/indices)
- **chainTag / chainNodeTag**: fields exist but are empty (0 tagged at inspection)
- **Key fields for prediction**:
  - `businessScope` (text): 经营范围
  - `industry1`, `industry2`, `industry3`, `industry4` (text): industry classification names
  - `industryCode1`, `industryCode2`, `industryCode3`, `industryCode4` (long): numeric codes
  - `companyName`, `address`, `city`, `district`, `enterpriseType`
  - `chainTag` (nested): empty — THIS IS THE PREDICTION TARGET
  - `chainNodeTag` (text): empty

### Related indices (for reference)
- `market-subjects-merged` (220M) — merged version
- `market-subjects-merged-v1` through `merged-v4`
- `market-subjects-saer` (217M), `market-subjects-saer-company` (71M)
- `ent-mdsi-v1` through `ent-mdsi-v8` (various sizes)
- `hzxy_global_firm`, `hzxy_nation_global_enterprise`
- `patents` (27.7M), `patents-v1`, `patents-v2`

---

## Connection Details

### MySQL
```python
import pymysql
conn = pymysql.connect(
    host='10.3.1.1', port=9184,
    user='dev_data_zstzpt', password='<password>',
    database='dev_data_zstzpt', charset='utf8mb4'
)
```

### Elasticsearch
```python
pip install 'elasticsearch>=7.0,<9.0'

es = Elasticsearch(
    'https://10.4.2.2:9800',
    basic_auth=('hermes-agent-001', '<password>'),
    verify_certs=False,
    request_timeout=30
)
```
