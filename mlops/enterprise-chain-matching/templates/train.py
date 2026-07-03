"""
Tier 1: 链级多标签分类器训练
基座模型: BAAI/bge-small-zh-v1.5 (24M params)
任务: 给定经营范围文本，预测企业属于哪些产业链（多标签分类）

Usage:
    python train.py --epochs 10 --batch-size 32 --lr 2e-5

Requirements:
    pip install torch transformers scikit-learn
"""
import json
import os
import argparse
import numpy as np
from collections import Counter

import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from transformers import (
    AutoTokenizer,
    AutoModel,
    get_cosine_schedule_with_warmup,
)
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    hamming_loss,
    classification_report,
)

# === CONFIGURATION ===
PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# NOTE: preprocess.py writes to src/data/. Keep paths consistent.
DATA_DIR = os.path.join(PROJECT_DIR, "src", "data")
PROCESSED_DIR = os.path.join(DATA_DIR, "processed")
MODELS_DIR = os.path.join(PROJECT_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

MODEL_NAME = "BAAI/bge-small-zh-v1.5"
MAX_LENGTH = 256
BATCH_SIZE = 64
LEARNING_RATE = 2e-5
NUM_EPOCHS = 10
WARMUP_RATIO = 0.1
WEIGHT_DECAY = 0.01
GRADIENT_ACCUMULATION_STEPS = 2
THRESHOLD = 0.5


class MultiLabelDataset(Dataset):
    def __init__(self, data, tokenizer, max_length, num_labels):
        self.texts = [item["text"] for item in data]
        self.labels = [item["labels"] for item in data]
        self.tokenizer = tokenizer
        self.max_length = max_length
        self.num_labels = num_labels

    def __len__(self):
        return len(self.texts)

    def __getitem__(self, idx):
        text = self.texts[idx]
        if len(text) > 500:
            text = text[:500]

        encoding = self.tokenizer(
            text,
            max_length=self.max_length,
            padding="max_length",
            truncation=True,
            return_tensors="pt",
        )

        label_ids = self.labels[idx]
        multi_hot = torch.zeros(self.num_labels, dtype=torch.float)
        for lid in label_ids:
            if lid < self.num_labels:
                multi_hot[lid] = 1.0

        return {
            "input_ids": encoding["input_ids"].squeeze(0),
            "attention_mask": encoding["attention_mask"].squeeze(0),
            "labels": multi_hot,
        }


class ChainClassifier(nn.Module):
    def __init__(self, model_name, num_labels, dropout=0.1):
        super().__init__()
        self.encoder = AutoModel.from_pretrained(model_name)
        self.dropout = nn.Dropout(dropout)
        hidden_size = self.encoder.config.hidden_size
        self.classifier = nn.Linear(hidden_size, num_labels)

    def forward(self, input_ids, attention_mask):
        outputs = self.encoder(input_ids=input_ids, attention_mask=attention_mask)
        pooled = outputs.last_hidden_state[:, 0, :]  # [CLS] token
        pooled = self.dropout(pooled)
        logits = self.classifier(pooled)
        return logits


def load_data(filename):
    path = os.path.join(PROCESSED_DIR, filename)
    data = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            data.append(json.loads(line))
    return data


def load_label_encoder():
    path = os.path.join(PROCESSED_DIR, "label_encoder.json")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def train(args):
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"Device: {device}")
    if torch.cuda.is_available():
        print(f"GPU: {torch.cuda.get_device_name(0)}")
        print(f"VRAM: {torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f} GB")

    label_encoder = load_label_encoder()
    num_labels = label_encoder["num_labels"]
    label_list = label_encoder["label_list"]
    print(f"类别数: {num_labels}")

    train_data = load_data("train.jsonl")
    val_data = load_data("val.jsonl")
    print(f"训练集: {len(train_data):,} | 验证集: {len(val_data):,}")

    tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)

    train_dataset = MultiLabelDataset(train_data, tokenizer, args.max_length, num_labels)
    val_dataset = MultiLabelDataset(val_data, tokenizer, args.max_length, num_labels)

    train_loader = DataLoader(
        train_dataset, batch_size=args.batch_size, shuffle=True,
        num_workers=2, pin_memory=True
    )
    val_loader = DataLoader(
        val_dataset, batch_size=args.batch_size, shuffle=False,
        num_workers=2, pin_memory=True
    )

    model = ChainClassifier(MODEL_NAME, num_labels, dropout=args.dropout)
    model.to(device)

    # Class weights for imbalance
    all_labels = []
    for item in train_data:
        all_labels.extend(item["labels"])
    label_counts = Counter(all_labels)
    total_label_occurrences = sum(label_counts.values())
    pos_weights = []
    for i in range(num_labels):
        count = label_counts.get(i, 1)
        weight = total_label_occurrences / (num_labels * count)
        pos_weights.append(weight)
    pos_weights = torch.tensor(pos_weights, device=device)

    optimizer = torch.optim.AdamW(
        model.parameters(), lr=args.lr, weight_decay=args.weight_decay,
    )
    total_steps = len(train_loader) * args.epochs // args.gradient_accumulation_steps
    warmup_steps = int(total_steps * args.warmup_ratio)
    scheduler = get_cosine_schedule_with_warmup(
        optimizer, num_warmup_steps=warmup_steps, num_training_steps=total_steps
    )

    criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weights)
    best_f1 = 0.0

    for epoch in range(args.epochs):
        model.train()
        train_loss = 0.0
        optimizer.zero_grad()

        for step, batch in enumerate(train_loader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            logits = model(input_ids, attention_mask)
            loss = criterion(logits, labels) / args.gradient_accumulation_steps
            loss.backward()
            train_loss += loss.item() * args.gradient_accumulation_steps

            if (step + 1) % args.gradient_accumulation_steps == 0:
                torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()

        avg_train_loss = train_loss / len(train_loader)

        # Validation
        model.eval()
        val_loss = 0.0
        all_preds, all_labels_arr = [], []

        with torch.no_grad():
            for batch in val_loader:
                input_ids = batch["input_ids"].to(device)
                attention_mask = batch["attention_mask"].to(device)
                labels = batch["labels"].to(device)

                logits = model(input_ids, attention_mask)
                loss = criterion(logits, labels)
                val_loss += loss.item()

                preds = (torch.sigmoid(logits) > args.threshold).float()
                all_preds.append(preds.cpu().numpy())
                all_labels_arr.append(labels.cpu().numpy())

        avg_val_loss = val_loss / len(val_loader)
        all_preds = np.vstack(all_preds)
        all_labels_arr = np.vstack(all_labels_arr)

        micro_f1 = f1_score(all_labels_arr, all_preds, average="micro", zero_division=0)
        macro_f1 = f1_score(all_labels_arr, all_preds, average="macro", zero_division=0)
        sample_f1 = f1_score(all_labels_arr, all_preds, average="samples", zero_division=0)
        hamming = hamming_loss(all_labels_arr, all_preds)

        print(f"Epoch {epoch+1}/{args.epochs} | "
              f"train_loss={avg_train_loss:.4f} | val_loss={avg_val_loss:.4f} | "
              f"micro_f1={micro_f1:.4f} | macro_f1={macro_f1:.4f} | "
              f"sample_f1={sample_f1:.4f} | hamming={hamming:.4f}")

        if sample_f1 > best_f1:
            best_f1 = sample_f1
            torch.save({
                "epoch": epoch,
                "model_state_dict": model.state_dict(),
                "val_f1": best_f1,
                "num_labels": num_labels,
                "label_list": label_list,
            }, os.path.join(MODELS_DIR, "best_model.pt"))

    print(f"\n最佳验证 F1 (samples): {best_f1:.4f}")

    # Test set evaluation
    test_data = load_data("test.jsonl")
    test_dataset = MultiLabelDataset(test_data, tokenizer, args.max_length, num_labels)
    test_loader = DataLoader(test_dataset, batch_size=args.batch_size, shuffle=False)

    model.eval()
    all_preds, all_labels_arr = [], []
    with torch.no_grad():
        for batch in test_loader:
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)
            logits = model(input_ids, attention_mask)
            preds = (torch.sigmoid(logits) > args.threshold).float()
            all_preds.append(preds.cpu().numpy())
            all_labels_arr.append(labels.cpu().numpy())

    all_preds = np.vstack(all_preds)
    all_labels_arr = np.vstack(all_labels_arr)

    print(f"\n=== 测试集评估 ===")
    print(f"Micro F1:  {f1_score(all_labels_arr, all_preds, average='micro', zero_division=0):.4f}")
    print(f"Macro F1:  {f1_score(all_labels_arr, all_preds, average='macro', zero_division=0):.4f}")
    print(f"Samples F1: {f1_score(all_labels_arr, all_preds, average='samples', zero_division=0):.4f}")
    print(f"Hamming Loss: {hamming_loss(all_labels_arr, all_preds):.4f}")

    report = classification_report(
        all_labels_arr, all_preds, target_names=label_list,
        zero_division=0, output_dict=True
    )
    for label in label_list:
        if label in report:
            r = report[label]
            print(f"  {label:20s} | P={r['precision']:.3f} R={r['recall']:.3f} F1={r['f1-score']:.3f} (support={r['support']})")

    # Save final model
    final_path = os.path.join(MODELS_DIR, "final_model")
    os.makedirs(final_path, exist_ok=True)
    torch.save(model.state_dict(), os.path.join(final_path, "pytorch_model.bin"))
    tokenizer.save_pretrained(final_path)
    with open(os.path.join(final_path, "config.json"), "w", encoding="utf-8") as f:
        json.dump({
            "num_labels": num_labels, "label_list": label_list,
            "threshold": args.threshold, "model_name": MODEL_NAME,
            "max_length": args.max_length,
        }, f, ensure_ascii=False, indent=2)
    print(f"\n最终模型保存到: {final_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--epochs", type=int, default=NUM_EPOCHS)
    parser.add_argument("--batch-size", type=int, default=BATCH_SIZE)
    parser.add_argument("--lr", type=float, default=LEARNING_RATE)
    parser.add_argument("--max-length", type=int, default=MAX_LENGTH)
    parser.add_argument("--dropout", type=float, default=0.1)
    parser.add_argument("--threshold", type=float, default=THRESHOLD)
    parser.add_argument("--weight-decay", type=float, default=WEIGHT_DECAY)
    parser.add_argument("--warmup-ratio", type=float, default=WARMUP_RATIO)
    parser.add_argument("--gradient-accumulation-steps", type=int, default=GRADIENT_ACCUMULATION_STEPS)
    args = parser.parse_args()
    train(args)
