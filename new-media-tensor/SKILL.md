---
name: new-media-tensor
description: Working on the new-media-tensor project — architecture, naming conventions, common pitfalls, and workflows.
---

# new-media-tensor 项目

## 路径

`/mnt/f/projects/new-media-tensor/`

README 位于项目根目录，是权威参考文档。架构图和流程图使用 Mermaid。

## 五核心组件

飞书多维表格「新媒体运动」作为数据中枢，状态字段驱动，无需消息队列：

0. **Collector** (`collector_<来源>.py`) 🚧 — 主动发现：AI 扫描热点/流量特征 → 自动录入
1. **Ingestor** (`ingestor_<渠道>.py`) — 被动收录：人发现线索 → 投递到渠道 → 脚本定期拉取入库
2. **Processor** (`processor_<平台>_<类型>.py`) — 线索处理：下载、提取、转写、解析 → 丰富记录
3. **Generator** (`generator_<类型>.py`) — 内容生成：LLM 生成文章/视频 → 保存本地 + 回填状态
4. **Publisher** (`publisher_<平台>_<类型>.py`) — 内容发布：上传封面 → 创建草稿 → 回填 ID

> **Ingestor vs Collector 的关键区别**：Ingestor 被动等人工投递，Collector 主动找热点。两者共存互补。

## 命名规范

```
[角色]_[平台/内容类型]_[变体].py

角色：     collector | ingestor | processor | generator | publisher
平台：     douyin    | bilibili | weibo     | wechat    | xiaohongshu
内容类型： video     | article  | post      | link
变体：     small     | medium   | large      （可选，模型/配置差异）
```

## 目录结构

- `lib/feishu_api.py` — 飞书 API 共享库（load_credentials, get_tenant_token, get_all_records, update_record, ensure_field_exists）
- `tools/` — 工具脚本（Whisper 模型下载、抖音路由数据提取）
- `collector/` — 🚧 线索发现（抖音热点、微博热搜自动抓取）
- `ingestor/` — 线索收录（邮箱 IMAP 拉取）
- `processor/` — 线索处理（短链解析、视频下载+转写）
- `generator_article.py` — 内容生成（LLM → HTML 文章）
- `publisher/` — 内容发布（微信公众号草稿创建）

## 输出目录

Generator 和 Publisher 共用 `~/tmp/content_output/`（可通过 .env 的 `OUTPUT_DIR` 自定义）：

```
~/tmp/content_output/
├── {record_id}/
│   ├── article.html   ← generator_article.py 生成
│   └── cover.jpg      ← publisher_wx_article.py 下载
├── {record_id}/
│   ├── article.html
│   └── cover.png
└── ...
```

每条飞书记录一个独立文件夹，内含 HTML 文章和封面图片。未来扩展插图、视频等衍生文件时直接往对应 `{record_id}/` 目录添加。

## 状态流转（文章链路）

```
飞书记录（有标题+摘要+封面）
  → [generator_article.py] → ✅ 文章已生成
    → [publisher_wx_article.py] → ✅ 草稿创建成功
```

失败状态标记：`[FAILED_AI_GEN]`, `[FAILED_COVER_DL]`, `[FAILED_COVER_UP]`, `[FAILED_DRAFT_CREATE]`。

生成与发布通过飞书状态字段解耦，各自独立 cron 触发。

## 飞书多维表格

| 项目 | 值 |
|------|-----|
| App Token | `Tureb4scXaJ7uAsHvkJcu9PGnlc` |
| Table ID | `tblLfCt8CoN0KvNm` |
| 表格名称 | 新媒体运动 |

## 常见陷阱

### 1. `openai-whisper` ≠ `whisper`

PyPI 上 `whisper` 包（v1.1.10）不是 OpenAI 官方的。正确安装：

```bash
# 错误：pip install whisper
# 正确：
pip install openai-whisper
```

在 `requirements.txt` 中必须写 `openai-whisper`。若已装错：

```bash
pip uninstall whisper -y && pip install openai-whisper
```

### 2. ffmpeg 路径

脚本硬编码 `os.path.expanduser("~/bin/ffmpeg")`。若系统 ffmpeg 在其他位置，创建软链接：

```bash
mkdir -p ~/bin && ln -s /usr/bin/ffmpeg ~/bin/ffmpeg
```

### 3. `datetime` 导入

脚本中若用到 `datetime.now()`，需要用 `from datetime import datetime`，而非 `import datetime`（后者需要 `datetime.datetime.now()`）。

### 4. 中文引号与 Python 字符串

在 Python 字符串中直接嵌入中文双引号 `\u201c` `\u201d`（`"` `"`）可能导致语法错误（被误当作字符串定界符）。用方角引号 `「简体中文」` 替代。

## 依赖

核心：`requests`, `openai`, `python-dotenv`, `openai-whisper`, `torch`, `ffmpeg`。
