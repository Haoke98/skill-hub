# Hermes Skills

个人 Hermes Agent 自定义技能集合。这些技能扩展了 Hermes Agent 的能力。

## 技能列表

| 技能 | 分类 | 说明 |
|------|------|------|
| [web-access](research/web-access/) | research | 从 DNS 劫持/Geo-blocked 环境访问 Web 内容（DoH + curl --resolve + Playwright） |
| [enterprise-chain-matching](mlops/enterprise-chain-matching/) | mlops | 企业产业链匹配 — 两级分类器（链级 + 节点级） |
| [new-media-tensor](new-media-tensor/) | - | 新媒体内容处理流水线（音频转录、内容提取等） |
| [audio-transcription](audio-transcription/) | - | 音频转录 / 语音转文字 |
| [lm-evaluation-harness](mlops/evaluation/lm-evaluation-harness/) | mlops/evaluation | LLM 基准评估（MMLU, GSM8K 等） |
| [vllm](mlops/inference/vllm/) | mlops/inference | vLLM 高吞吐推理服务 |
| [audiocraft](mlops/models/audiocraft/) | mlops/models | AudioCraft 音频生成（MusicGen, AudioGen） |
| [segment-anything](mlops/models/segment-anything/) | mlops/models | SAM 零样本图像分割 |

## 安装

将技能目录复制到 Hermes 的 skills 目录：

```bash
cp -r research/web-access ~/.hermes/skills/research/
cp -r mlops/* ~/.hermes/skills/mlops/
cp -r new-media-tensor ~/.hermes/skills/
cp -r audio-transcription ~/.hermes/skills/
```

## 目录结构

```
hermes-skills/
├── research/
│   └── web-access/           # Web 访问（DoH + Playwright）
│       ├── SKILL.md
│       ├── scripts/
│       └── references/
├── mlops/
│   ├── enterprise-chain-matching/  # 企业产业链匹配
│   ├── evaluation/
│   │   └── lm-evaluation-harness/  # LLM 评估
│   ├── inference/
│   │   └── vllm/                   # vLLM 推理
│   └── models/
│       ├── audiocraft/             # 音频生成
│       └── segment-anything/       # 图像分割
├── new-media-tensor/         # 新媒体处理
└── audio-transcription/      # 音频转录
```

## 维护

这些技能会随使用不断迭代优化。每次修改后 commit + push 保持同步。
