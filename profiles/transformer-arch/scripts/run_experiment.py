#!/usr/bin/env python3
"""Transformer-arch experiment runner for labrat vNext.

Supports two modes selected by `candidate.resolved_config.training.mode`:

- "synthetic" (default in the shipped baseline): fast stdlib-only surrogate that
  produces realistic-shape metrics and a checkpoint series from the config.
  Lets the lab exercise the full runtime loop without a torch install.
- "real": pure-PyTorch character-level tiny transformer with manual training
  loop. Requires `torch` in the lab venv. Writes the same result contract.

Both modes emit:
- <output>                                  -> result.json
- <output>.parent / "checkpoints.jsonl"     -> per-step interim metrics

Both modes honour the labrat result contract: `valid`, `metrics`,
`proxy_metrics`, `finding`, `resource_floor`, and the new optional
`failure_class` field read by the evaluator.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import time
from pathlib import Path


def load_candidate(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)


def append_checkpoint(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        f.write(json.dumps(payload))
        f.write("\n")


def clear_checkpoint_log(path: Path) -> None:
    if path.exists():
        path.unlink()


def derive_checkpoints_path(output_path: Path) -> Path:
    return output_path.parent / "checkpoints.jsonl"


def _lognormal_score(value: float, center: float, sigma: float) -> float:
    if value <= 0 or center <= 0:
        return 0.0
    return math.exp(-((math.log(value) - math.log(center)) ** 2) / (2 * sigma * sigma))


def _gaussian_score(value: float, center: float, sigma: float) -> float:
    return math.exp(-((value - center) ** 2) / (2 * sigma * sigma))


def synthetic_trajectory(config: dict, rng: random.Random) -> list[dict]:
    """Return a list of interim checkpoint dicts with a realistic-looking curve."""
    model = config.get("model", {})
    training = config.get("training", {})

    steps = int(training.get("steps", 100))
    checkpoint_every = max(1, int(training.get("checkpoint_every", max(1, steps // 5))))
    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    dropout = float(model.get("dropout", 0.0))
    warmup_steps = int(training.get("warmup_steps", 0))
    lr = float(training.get("lr", 0.003))

    # Target final search_eval for this config. Reused by synthetic_final_metrics.
    final_score = config_target_score(config)

    # Shape: exponential approach to final_score, with noise.
    trajectory: list[dict] = []
    collapse_step: int | None = None
    if depth >= 6 and d_model <= 48:
        # Deep-narrow collapse pattern — fail late.
        collapse_step = int(steps * rng.uniform(0.6, 0.9))
    elif lr > 0.008 and warmup_steps < 5:
        # Aggressive LR without warmup — NaN early.
        collapse_step = int(steps * rng.uniform(0.05, 0.2))

    for step in range(checkpoint_every, steps + 1, checkpoint_every):
        progress = step / max(1, steps)
        warmup_penalty = max(0.0, 1 - (step / max(1, warmup_steps))) if warmup_steps > 0 else 0.0
        # exponential approach, capped.
        eased = 1 - math.exp(-3.0 * progress)
        interim = final_score * eased - 0.05 * warmup_penalty
        interim += rng.gauss(0, 0.01)
        interim = max(0.0, min(1.0, interim))

        loss = max(0.01, 2.5 * (1 - interim) + rng.gauss(0, 0.02))
        trajectory.append(
            {
                "step": step,
                "search_eval": round(interim, 6),
                "loss": round(loss, 6),
                "valid": True,
            }
        )

        if collapse_step is not None and step >= collapse_step:
            trajectory[-1]["valid"] = False
            trajectory[-1]["search_eval"] = 0.0
            trajectory[-1]["loss"] = None
            trajectory[-1]["note"] = "training collapsed"
            break

    # Apply dropout penalty to the entire trajectory after the fact.
    if dropout > 0.1:
        for checkpoint in trajectory:
            if checkpoint.get("valid"):
                checkpoint["search_eval"] = round(max(0.0, checkpoint["search_eval"] - dropout * 0.3), 6)

    return trajectory


def config_target_score(config: dict) -> float:
    """Target score this config would reach if training completed cleanly."""
    model = config.get("model", {})
    training = config.get("training", {})

    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    heads = int(model.get("heads", 2))
    lr = float(training.get("lr", 0.003))
    steps = int(training.get("steps", 100))
    warmup = int(training.get("warmup_steps", 10))
    dropout = float(model.get("dropout", 0.0))

    depth_score = _gaussian_score(depth, 4, 2)
    width_score = _gaussian_score(d_model, 64, 28)
    heads_score = _gaussian_score(heads, 4, 2)
    lr_score = _lognormal_score(lr, 0.003, 0.7)
    steps_score = _lognormal_score(steps, 120, 0.5)

    base = 0.35 * depth_score * width_score + 0.25 * heads_score + 0.2 * lr_score + 0.2 * steps_score

    if dropout > 0.1:
        base -= dropout * 0.4
    if warmup > 25:
        base -= 0.1

    return max(0.0, min(1.0, base))


def infer_failure_class(trajectory: list[dict]) -> tuple[bool, str | None, str | None]:
    """Walk the trajectory and classify whether this run failed and why."""
    if not trajectory:
        return False, "other", "empty trajectory"
    last = trajectory[-1]
    if not last.get("valid", True):
        loss = last.get("loss")
        if loss is None or (isinstance(loss, float) and math.isnan(loss)):
            return False, "nan", "training collapsed mid-run"
        return False, "unstable", "training instability mid-run"
    loss = last.get("loss")
    if isinstance(loss, (int, float)) and loss > 4.0:
        return True, None, "training failed to converge but did not crash"
    return True, None, "training ran to completion"


def summarise_trajectory(trajectory: list[dict]) -> dict:
    valid_scores = [c["search_eval"] for c in trajectory if c.get("valid")]
    if not valid_scores:
        return {"final_search_eval": 0.0, "peak_search_eval": 0.0, "late_stability": 0.0}
    final_score = valid_scores[-1]
    peak = max(valid_scores)
    # Late stability: how much did search_eval change in the last third of checkpoints?
    tail = valid_scores[max(0, 2 * len(valid_scores) // 3) :]
    late_stability = 1.0 - (max(tail) - min(tail)) if tail else 0.0
    return {
        "final_search_eval": round(final_score, 6),
        "peak_search_eval": round(peak, 6),
        "late_stability": round(max(0.0, late_stability), 6),
    }


def synthetic_payload(candidate: dict, config: dict, checkpoints_path: Path) -> dict:
    """Compose a labrat-compatible result.json using a synthetic trajectory."""
    started = time.perf_counter()
    rng = random.Random(int(config.get("training", {}).get("seed", 1337)) ^ hash(candidate["candidate_id"]) & 0xFFFF)
    clear_checkpoint_log(checkpoints_path)

    trajectory = synthetic_trajectory(config, rng)
    for checkpoint in trajectory:
        append_checkpoint(checkpoints_path, checkpoint)

    valid, failure_class, note = infer_failure_class(trajectory)
    summary = summarise_trajectory(trajectory)

    # Compose the three canonical scores plus the two decisive-challenge metrics.
    final_score = summary["final_search_eval"]
    selection_score = max(0.0, final_score - 0.01 - abs(rng.gauss(0, 0.01)))
    final_eval = max(0.0, final_score - 0.02 - abs(rng.gauss(0, 0.01)))

    model = config.get("model", {})
    training = config.get("training", {})
    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    steps = int(training.get("steps", 100))

    # Held-out generalization: wide/deep models overfit the training distribution.
    ood_penalty = 0.0
    if d_model > 96:
        ood_penalty += (d_model - 96) * 0.006
    if depth >= 6 and d_model >= 64:
        ood_penalty += 0.08
    if steps > 300:
        ood_penalty += 0.05
    holdout_generalization = max(0.0, final_score - ood_penalty - abs(rng.gauss(0, 0.02)))

    # Held-out stability: how well does the late-training signal match the peak?
    peak = summary["peak_search_eval"]
    if peak == 0.0:
        holdout_stability = 0.0
    else:
        stability_ratio = final_score / peak
        holdout_stability = max(0.0, min(1.0, stability_ratio - abs(rng.gauss(0, 0.02))))

    elapsed = time.perf_counter() - started
    param_count = estimate_param_count(config)

    payload = {
        "candidate_id": candidate["candidate_id"],
        "valid": valid,
        "proxy_metrics": {
            "elapsed_seconds": round(elapsed, 4),
            "param_count": param_count,
            "steps_completed": trajectory[-1]["step"] if trajectory else 0,
            "late_stability": summary["late_stability"],
            "mode": "synthetic",
        },
        "metrics": {
            "search": {"primary_metric": round(final_score, 6)},
            "selection": {"primary_metric": round(selection_score, 6)},
            "final": {"primary_metric": round(final_eval, 6)},
            "challenges": {
                "holdout_generalization": {"primary_metric": round(holdout_generalization, 6)},
                "holdout_stability": {"primary_metric": round(holdout_stability, 6)},
            },
        },
        "finding": synthetic_finding(config, valid, failure_class, note, summary),
        "resource_floor": round(param_count / 400_000.0, 4),
    }
    if failure_class:
        payload["failure_class"] = failure_class
    if not valid:
        payload["metrics"]["error"] = note or "training failed"
    return payload


def synthetic_finding(
    config: dict, valid: bool, failure_class: str | None, note: str | None, summary: dict
) -> str:
    model = config.get("model", {})
    training = config.get("training", {})
    shape = f"d={model.get('depth', '?')} h={model.get('heads', '?')} w={model.get('d_model', '?')} lr={training.get('lr', '?')} steps={training.get('steps', '?')}"
    if not valid:
        return f"{shape} {failure_class or 'other'}: {note or 'run failed'}"
    return f"{shape} final={summary['final_search_eval']} peak={summary['peak_search_eval']}"


def estimate_param_count(config: dict) -> int:
    model = config.get("model", {})
    depth = int(model.get("depth", 2))
    d_model = int(model.get("d_model", 32))
    vocab = 96  # rough character vocab size for our corpus
    block = int(config.get("data", {}).get("block_size", 32))
    per_layer = 4 * d_model * d_model + 8 * d_model * d_model + 4 * d_model
    embed = vocab * d_model + block * d_model
    head = d_model * vocab
    return int(embed + depth * per_layer + head)


def real_payload(candidate: dict, config: dict, checkpoints_path: Path, lab_root: Path) -> dict:
    """Train a tiny PyTorch transformer. Requires torch; falls back to an error payload if missing."""
    started = time.perf_counter()
    clear_checkpoint_log(checkpoints_path)
    try:
        import numpy as np  # noqa: F401
        import torch  # type: ignore
        from torch import nn  # type: ignore
    except Exception as exc:  # noqa: BLE001
        return {
            "candidate_id": candidate["candidate_id"],
            "valid": False,
            "proxy_metrics": {"elapsed_seconds": round(time.perf_counter() - started, 4), "mode": "real"},
            "metrics": {
                "search": {"primary_metric": 0.0},
                "selection": {"primary_metric": 0.0},
                "final": {"primary_metric": 0.0},
                "error": f"torch import failed: {exc}. Set training.mode=\"synthetic\" or install torch.",
            },
            "finding": "real mode requested but torch is not installed",
            "resource_floor": None,
            "failure_class": "arch",
        }

    train_text = (lab_root / config["data"]["train_path"]).read_text(encoding="utf-8")
    holdout_text = (lab_root / config["data"]["holdout_path"]).read_text(encoding="utf-8")

    vocab = sorted(set(train_text + holdout_text))
    stoi = {ch: i for i, ch in enumerate(vocab)}
    vocab_size = len(vocab)

    def encode(text: str) -> list[int]:
        return [stoi[c] for c in text if c in stoi]

    train_ids = torch.tensor(encode(train_text), dtype=torch.long)
    holdout_ids = torch.tensor(encode(holdout_text), dtype=torch.long)
    block_size = int(config["data"].get("block_size", 32))
    batch_size = int(config["training"].get("batch_size", 16))
    seed = int(config["training"].get("seed", 1337))
    torch.manual_seed(seed)

    # Split training ids into search / selection / final slices (90/5/5).
    n = train_ids.numel()
    train_end = int(n * 0.9)
    search_end = int(n * 0.95)
    train_slice = train_ids[:train_end]
    search_slice = train_ids[train_end:search_end]
    selection_slice = train_ids[search_end:]

    model_cfg = config["model"]
    depth = int(model_cfg.get("depth", 2))
    d_model = int(model_cfg.get("d_model", 32))
    heads = int(model_cfg.get("heads", 2))
    dropout = float(model_cfg.get("dropout", 0.0))
    activation = model_cfg.get("activation", "gelu")

    training_cfg = config["training"]
    steps = int(training_cfg.get("steps", 100))
    lr = float(training_cfg.get("lr", 0.003))
    warmup_steps = int(training_cfg.get("warmup_steps", 0))
    checkpoint_every = max(1, int(training_cfg.get("checkpoint_every", max(1, steps // 5))))

    if d_model % heads != 0:
        return {
            "candidate_id": candidate["candidate_id"],
            "valid": False,
            "proxy_metrics": {"elapsed_seconds": round(time.perf_counter() - started, 4), "mode": "real"},
            "metrics": {
                "search": {"primary_metric": 0.0},
                "selection": {"primary_metric": 0.0},
                "final": {"primary_metric": 0.0},
                "error": f"d_model ({d_model}) not divisible by heads ({heads})",
            },
            "finding": "architecture mismatch",
            "resource_floor": None,
            "failure_class": "arch",
        }

    class Block(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.ln1 = nn.LayerNorm(d_model)
            self.attn = nn.MultiheadAttention(d_model, heads, dropout=dropout, batch_first=True)
            self.ln2 = nn.LayerNorm(d_model)
            act = {"gelu": nn.GELU, "relu": nn.ReLU, "silu": nn.SiLU}.get(activation, nn.GELU)
            self.ffn = nn.Sequential(
                nn.Linear(d_model, 4 * d_model),
                act(),
                nn.Linear(4 * d_model, d_model),
                nn.Dropout(dropout),
            )

        def forward(self, x, mask):
            h = self.ln1(x)
            attn_out, _ = self.attn(h, h, h, attn_mask=mask, need_weights=False)
            x = x + attn_out
            x = x + self.ffn(self.ln2(x))
            return x

    class TinyTransformer(nn.Module):
        def __init__(self) -> None:
            super().__init__()
            self.tok_emb = nn.Embedding(vocab_size, d_model)
            self.pos_emb = nn.Embedding(block_size, d_model)
            self.blocks = nn.ModuleList([Block() for _ in range(depth)])
            self.ln_f = nn.LayerNorm(d_model)
            self.head = nn.Linear(d_model, vocab_size, bias=False)

        def forward(self, idx):
            B, T = idx.shape
            pos = torch.arange(T, device=idx.device)
            x = self.tok_emb(idx) + self.pos_emb(pos)
            mask = torch.triu(torch.ones(T, T, device=idx.device, dtype=torch.bool), diagonal=1)
            for block in self.blocks:
                x = block(x, mask)
            x = self.ln_f(x)
            return self.head(x)

    model = TinyTransformer()
    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, betas=(0.9, 0.95), weight_decay=0.0)

    def batch_from(ids):
        n = ids.numel() - block_size - 1
        if n <= 0:
            return None
        ixs = torch.randint(0, n, (batch_size,))
        xs = torch.stack([ids[i : i + block_size] for i in ixs])
        ys = torch.stack([ids[i + 1 : i + 1 + block_size] for i in ixs])
        return xs, ys

    @torch.no_grad()
    def eval_split(ids, max_batches: int = 8) -> float:
        model.eval()
        n_items = 0
        total = 0.0
        for _ in range(max_batches):
            sample = batch_from(ids)
            if sample is None:
                break
            xs, ys = sample
            logits = model(xs)
            loss = nn.functional.cross_entropy(logits.reshape(-1, vocab_size), ys.reshape(-1))
            total += float(loss.item())
            n_items += 1
        model.train()
        return math.exp(-(total / max(1, n_items)))

    intermediate_generalization: list[float] = []
    intermediate_stability_ref: float | None = None
    loss_nan = False

    for step in range(1, steps + 1):
        sample = batch_from(train_slice)
        if sample is None:
            return {
                "candidate_id": candidate["candidate_id"],
                "valid": False,
                "proxy_metrics": {"elapsed_seconds": round(time.perf_counter() - started, 4), "mode": "real"},
                "metrics": {
                    "search": {"primary_metric": 0.0},
                    "selection": {"primary_metric": 0.0},
                    "final": {"primary_metric": 0.0},
                    "error": "training corpus shorter than block_size",
                },
                "finding": "data too small",
                "resource_floor": None,
                "failure_class": "data",
            }
        xs, ys = sample

        if warmup_steps > 0 and step <= warmup_steps:
            for group in optimizer.param_groups:
                group["lr"] = lr * step / warmup_steps

        optimizer.zero_grad()
        logits = model(xs)
        loss = nn.functional.cross_entropy(logits.reshape(-1, vocab_size), ys.reshape(-1))
        if not torch.isfinite(loss):
            loss_nan = True
            append_checkpoint(
                checkpoints_path,
                {"step": step, "search_eval": 0.0, "loss": float("nan"), "valid": False, "note": "loss became non-finite"},
            )
            break
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), 1.0)
        optimizer.step()

        if step % checkpoint_every == 0 or step == steps:
            search_score = eval_split(search_slice)
            holdout_score = eval_split(holdout_ids)
            intermediate_generalization.append(holdout_score)
            if intermediate_stability_ref is None and step >= max(1, steps // 2):
                intermediate_stability_ref = holdout_score
            append_checkpoint(
                checkpoints_path,
                {
                    "step": step,
                    "search_eval": round(search_score, 6),
                    "holdout_eval": round(holdout_score, 6),
                    "loss": round(float(loss.item()), 6),
                    "valid": True,
                },
            )

    if loss_nan:
        return {
            "candidate_id": candidate["candidate_id"],
            "valid": False,
            "proxy_metrics": {"elapsed_seconds": round(time.perf_counter() - started, 4), "mode": "real"},
            "metrics": {
                "search": {"primary_metric": 0.0},
                "selection": {"primary_metric": 0.0},
                "final": {"primary_metric": 0.0},
                "error": "loss became non-finite during training",
            },
            "finding": "nan collapse during training",
            "resource_floor": None,
            "failure_class": "nan",
        }

    search_score = eval_split(search_slice)
    selection_score = eval_split(selection_slice)
    final_score = eval_split(selection_slice, max_batches=16)
    holdout_final = eval_split(holdout_ids, max_batches=16)
    if intermediate_stability_ref is not None and holdout_final > 0:
        stability = min(intermediate_stability_ref / holdout_final, holdout_final / intermediate_stability_ref)
    else:
        stability = 0.0

    elapsed = time.perf_counter() - started
    param_count = sum(p.numel() for p in model.parameters())

    payload = {
        "candidate_id": candidate["candidate_id"],
        "valid": True,
        "proxy_metrics": {
            "elapsed_seconds": round(elapsed, 4),
            "param_count": int(param_count),
            "steps_completed": steps,
            "mode": "real",
        },
        "metrics": {
            "search": {"primary_metric": round(search_score, 6)},
            "selection": {"primary_metric": round(selection_score, 6)},
            "final": {"primary_metric": round(final_score, 6)},
            "challenges": {
                "holdout_generalization": {"primary_metric": round(holdout_final, 6)},
                "holdout_stability": {"primary_metric": round(max(0.0, min(1.0, stability)), 6)},
            },
        },
        "finding": (
            f"d={depth} h={heads} w={d_model} lr={lr} steps={steps} "
            f"holdout={holdout_final:.4f} stability={stability:.4f}"
        ),
        "resource_floor": round(param_count / 400_000.0, 4),
    }
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Transformer-arch profile experiment runner.")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--dry-run", action="store_true", help="Force synthetic mode regardless of config.")
    args = parser.parse_args(argv)

    candidate = load_candidate(args.candidate)
    config = candidate["resolved_config"]
    checkpoints_path = derive_checkpoints_path(args.output)

    mode = "synthetic" if args.dry_run else str(config.get("training", {}).get("mode", "synthetic")).lower()
    lab_root = args.candidate.parents[3]

    if mode == "real":
        payload = real_payload(candidate, config, checkpoints_path, lab_root)
    else:
        payload = synthetic_payload(candidate, config, checkpoints_path)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(payload, f, indent=2)
        f.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
