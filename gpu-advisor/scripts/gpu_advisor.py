#!/usr/bin/env python3
"""GPU Advisor — detect GPU and recommend llama.cpp KV cache configuration.

Zero dependencies (stdlib only). Supports AMD (rocm-smi) and NVIDIA (nvidia-smi).
"""

import argparse
import json
import subprocess
import sys

# (layers, kv_heads, head_dim, swa_model)
MODELS = {
    "qwen3.5-0.6b":  (28, 2, 128, False),
    "qwen3.5-1.7b":  (28, 4, 128, False),
    "qwen3.5-4b":    (36, 8, 128, False),
    "qwen3.5-9b":    (40, 8, 128, False),
    "qwen3.5-14b":   (48, 8, 128, False),
    "qwen3.5-27b":   (64, 8, 128, False),
    "qwen3-8b":      (36, 8, 128, False),
    "gemma-4-26b":   (50, 4, 256, True),
    "gemma-4-31b":   (50, 16, 128, True),
    "llama-3.1-8b":  (32, 8, 128, False),
    "llama-3.1-70b": (80, 8, 128, False),
    "mistral-7b":    (32, 8, 128, False),
}

MODEL_SIZES = {
    "qwen3.5-9b":  {"Q4_K_M": 5.5, "Q5_K_M": 6.6, "Q8_0": 9.5},
    "qwen3.5-27b": {"Q4_K_M": 15.3, "Q5_K_M": 18.5, "Q8_0": 27.2},
    "gemma-4-26b": {"Q4_K_M": 15.9, "IQ4_XS": 12.5},
    "llama-3.1-8b": {"Q4_K_M": 4.9, "Q5_K_M": 5.7, "Q8_0": 8.5},
}

KV_TYPES = ["f16", "q8_0", "q4_0", "turbo3", "turbo4"]
KV_BYTES = {"f16": 2.0, "q8_0": 1.0, "q4_0": 0.5, "turbo3": 0.375, "turbo4": 0.25}
OVERHEAD_MB = 500

# Terminal colors (disabled if not a TTY)
if sys.stdout.isatty():
    C_BOLD  = "\033[1m"
    C_GREEN = "\033[32m"
    C_RED   = "\033[31m"
    C_CYAN  = "\033[36m"
    C_YELLOW = "\033[33m"
    C_DIM   = "\033[2m"
    C_RESET = "\033[0m"
else:
    C_BOLD = C_GREEN = C_RED = C_CYAN = C_YELLOW = C_DIM = C_RESET = ""


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def detect_gpu():
    """Detect GPU via rocm-smi or nvidia-smi."""
    out = run(["rocm-smi", "--showid", "--showproductname", "--showmeminfo", "vram", "--json"])
    if out:
        try:
            data = json.loads(out)
            card = next(iter(data.values())) if not isinstance(data, list) else data[0]
            name = card.get("Card Series", card.get("card_series", "AMD GPU"))
            vram_total = int(card.get("VRAM Total Memory (B)", card.get("vram_total", 0))) // (1024 * 1024)
            vram_used = int(card.get("VRAM Total Used Memory (B)", card.get("vram_used", 0))) // (1024 * 1024)
        except (json.JSONDecodeError, StopIteration, KeyError, ValueError):
            name, vram_total, vram_used = "AMD GPU", 0, 0

        arch = "unknown"
        ri = run(["rocminfo"])
        if ri:
            for line in ri.splitlines():
                if "gfx" in line.lower() and "name" in line.lower():
                    arch = line.split()[-1]
                    break

        rocm_ver = run(["cat", "/opt/rocm/.info/version"])
        return {
            "platform": "ROCm", "name": name, "arch": arch,
            "vram_total_mb": vram_total, "vram_used_mb": vram_used,
            "vram_free_mb": vram_total - vram_used,
            "driver": f"ROCm {rocm_ver}" if rocm_ver else "ROCm",
        }

    out = run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version,compute_cap",
               "--format=csv,noheader,nounits"])
    if out:
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 6:
            return {
                "platform": "CUDA", "name": parts[0],
                "arch": f"sm_{parts[5].replace('.', '')}",
                "vram_total_mb": int(parts[1]), "vram_used_mb": int(parts[2]),
                "vram_free_mb": int(parts[3]),
                "driver": f"CUDA {parts[4]}",
            }

    return None


def kv_size_mb(layers, kv_heads, head_dim, ctx, kv_type):
    return (2 * layers * kv_heads * head_dim * ctx * KV_BYTES[kv_type]) / (1024 * 1024)


def max_ctx(layers, kv_heads, head_dim, kv_type, available_mb):
    bpe = KV_BYTES[kv_type]
    bytes_per_token = 2 * layers * kv_heads * head_dim * bpe
    if bytes_per_token == 0 or available_mb <= 0:
        return 0
    return int((available_mb * 1024 * 1024) / bytes_per_token)


def resolve_model(model_key):
    """Resolve model name to profile with fuzzy matching."""
    model_key = model_key.lower().replace(" ", "-")
    if model_key in MODELS:
        return model_key, MODELS[model_key]
    for k in MODELS:
        if k in model_key or model_key in k:
            return k, MODELS[k]
    return model_key, None


def recommend(model_key, quant, ctx, gpu):
    model_key, profile = resolve_model(model_key)
    if not profile:
        return f"Unknown model '{model_key}'. Known: {', '.join(sorted(MODELS.keys()))}"

    layers, kv_heads, head_dim, is_swa = profile
    sizes = MODEL_SIZES.get(model_key, {})
    model_gb = sizes.get(quant, sizes.get("Q4_K_M", 0))
    if model_gb == 0:
        return f"No size data for {model_key} {quant}. Known quants: {list(sizes.keys()) or 'none'}"
    model_mb = model_gb * 1024
    available_for_kv = max(0, gpu["vram_free_mb"] - model_mb - OVERHEAD_MB)

    lines = [
        f"{C_BOLD}🖥  GPU: {gpu['name']} ({gpu['arch']}){C_RESET}",
        f"   VRAM: {gpu['vram_total_mb']} MiB total, {C_CYAN}{gpu['vram_free_mb']} MiB free{C_RESET}",
        f"   Platform: {gpu['driver']}",
        "",
        f"{C_BOLD}📦 Model: {model_key} {quant} ({model_gb:.1f} GiB){C_RESET}",
        f"   Context: {ctx:,} tokens",
    ]
    if is_swa:
        lines.append(f"   {C_YELLOW}⚠ SWA model — turbo on SWA layers causes quality loss. Use f16 for SWA.{C_RESET}")
    lines.append("")
    lines.append(f"  {C_DIM}{'KV type':<10}│ {'KV size':>8} │ {'Total VRAM':>10} │ {'Fits?':>5} │ {'Max context':>11}{C_RESET}")
    lines.append(f"  {C_DIM}{'─'*10}┼{'─'*10}┼{'─'*12}┼{'─'*7}┼{'─'*13}{C_RESET}")

    best = None
    for kv_type in KV_TYPES:
        kv_mb = kv_size_mb(layers, kv_heads, head_dim, ctx, kv_type)
        total = model_mb + kv_mb + OVERHEAD_MB
        fits = total <= gpu["vram_free_mb"]
        mctx = max_ctx(layers, kv_heads, head_dim, kv_type, available_for_kv)
        ctx_str = f"~{mctx // 1000}K" if mctx > 0 else "—"
        fit_str = f"{C_GREEN}  ✓  {C_RESET}" if fits else f"{C_RED}  ✗  {C_RESET}"
        highlight = C_BOLD if fits and best is None else ""
        lines.append(f"  {highlight}{kv_type:<10}│ {kv_mb:>6.0f} MB │ {total:>8.0f} MB │{fit_str}│ {ctx_str:>11}{C_RESET}")
        if fits and best is None:
            best = kv_type

    lines.append("")
    if best:
        labels = {
            "f16": "f16 — full precision, no compression needed.",
            "q8_0": "q8_0 — minimal quality loss, 2× compression.",
            "q4_0": "q4_0 — good compression (4×), widely supported.",
            "turbo3": "turbo3 — 5.3× compression, best TurboQuant tradeoff.",
            "turbo4": "turbo4 — 8× compression, needed to fit in VRAM.",
        }
        lines.append(f"  {C_GREEN}✅ Recommendation: {labels[best]}{C_RESET}")
        if best.startswith("turbo"):
            lines.append(f"  {C_DIM}Requires: TurboQuant-compatible llama.cpp build{C_RESET}")
            lines.append(f"  {C_DIM}Repo: https://github.com/domvox/llama.cpp-turboquant-hip{C_RESET}")
        lines.append("")
        cmd = f"  llama-server -m model.gguf -ngl 99 --ctx-size {ctx}"
        if best != "f16":
            cmd += f" \\\n    --cache-type-k {best} --cache-type-v {best}"
            if is_swa:
                cmd += " \\\n    --cache-type-k-swa f16 --cache-type-v-swa f16"
        lines.append(f"  {C_CYAN}{cmd}{C_RESET}")
    else:
        lines.append(f"  {C_RED}❌ Model does not fit in VRAM even with turbo4. Try a smaller quant or model.{C_RESET}")

    return "\n".join(lines)


def check(model_size_gb, ctx, kv_type, gpu):
    model_mb = model_size_gb * 1024
    # Show all KV types if none specified
    layers, kv_heads, head_dim = 64, 8, 128  # fallback profile
    kv_mb = kv_size_mb(layers, kv_heads, head_dim, ctx, kv_type)
    total = model_mb + kv_mb + OVERHEAD_MB
    fits = total <= gpu["vram_free_mb"]
    print(f"Model: {model_size_gb:.1f} GiB | KV ({kv_type}): {kv_mb:.0f} MB | Total: {total:.0f} MB")
    print(f"VRAM free: {gpu['vram_free_mb']} MB | {'✅ FITS' if fits else '❌ OOM'}")


def main():
    p = argparse.ArgumentParser(description="GPU Advisor for llama.cpp")
    sub = p.add_subparsers(dest="cmd")

    sub.add_parser("detect", help="Detect GPU hardware")

    rec = sub.add_parser("recommend", help="Recommend KV cache config")
    rec.add_argument("--model", required=True, help="Model name (e.g. Qwen3.5-27B)")
    rec.add_argument("--quant", default="Q4_K_M", help="Quantization (default: Q4_K_M)")
    rec.add_argument("--ctx", type=int, default=32000, help="Target context length")

    chk = sub.add_parser("check", help="Check if config fits")
    chk.add_argument("--model-size", type=float, required=True, help="Model size in GiB")
    chk.add_argument("--ctx", type=int, required=True, help="Context length")
    chk.add_argument("--kv-type", default="f16", choices=KV_BYTES.keys())

    args = p.parse_args()

    if args.cmd == "detect":
        gpu = detect_gpu()
        if gpu:
            print(json.dumps(gpu, indent=2))
        else:
            print("No GPU detected. Install rocm-smi (AMD) or nvidia-smi (NVIDIA).", file=sys.stderr)
            sys.exit(1)
    elif args.cmd in ("recommend", "check"):
        gpu = detect_gpu()
        if not gpu:
            print("No GPU detected.", file=sys.stderr)
            sys.exit(1)
        if args.cmd == "recommend":
            print(recommend(args.model, args.quant, args.ctx, gpu))
        else:
            check(args.model_size, args.ctx, args.kv_type, gpu)
    else:
        p.print_help()


if __name__ == "__main__":
    main()
