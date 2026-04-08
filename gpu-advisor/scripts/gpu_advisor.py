#!/usr/bin/env python3
"""GPU Advisor — detect GPU and recommend llama.cpp KV cache configuration.

Zero dependencies (stdlib only). Supports AMD (rocm-smi) and NVIDIA (nvidia-smi).
"""

import argparse
import json
import subprocess
import sys

# --- Known model profiles ---
# (layers, kv_heads, head_dim, swa_model)
MODELS = {
    "qwen3.5-0.6b":  (28, 2, 128, False),
    "qwen3.5-1.7b":  (28, 4, 128, False),
    "qwen3.5-4b":    (36, 8, 128, False),
    "qwen3.5-9b":    (40, 8, 128, False),
    "qwen3.5-14b":   (48, 8, 128, False),
    "qwen3.5-27b":   (64, 8, 128, False),
    "qwen3-8b":      (36, 8, 128, False),
    "gemma-4-26b":   (50, 4, 256, True),   # MoE: 4 KV heads, 256 head_dim
    "gemma-4-31b":   (50, 16, 128, True),  # Dense
    "llama-3.1-8b":  (32, 8, 128, False),
    "llama-3.1-70b": (80, 8, 128, False),
    "mistral-7b":    (32, 8, 128, False),
}

# Approximate GGUF sizes in GiB for common quants
MODEL_SIZES = {
    "qwen3.5-9b":  {"Q4_K_M": 5.5, "Q5_K_M": 6.6, "Q8_0": 9.5},
    "qwen3.5-27b": {"Q4_K_M": 15.3, "Q5_K_M": 18.5, "Q8_0": 27.2},
    "gemma-4-26b": {"Q4_K_M": 15.9, "IQ4_XS": 12.5},
    "llama-3.1-8b": {"Q4_K_M": 4.9, "Q5_K_M": 5.7, "Q8_0": 8.5},
}

KV_BYTES = {"f16": 2.0, "q8_0": 1.0, "q4_0": 0.5, "turbo3": 0.375, "turbo4": 0.25}
OVERHEAD_MB = 500


def run(cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
        return r.stdout.strip() if r.returncode == 0 else None
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None


def detect_gpu():
    """Detect GPU via rocm-smi or nvidia-smi."""
    # Try AMD first
    out = run(["rocm-smi", "--showid", "--showproductname", "--showmeminfo", "vram", "--json"])
    if out:
        try:
            data = json.loads(out)
            card = next(iter(data.values())) if not isinstance(data, list) else data[0]
            # rocm-smi JSON varies by version, try common keys
            name = card.get("Card Series", card.get("card_series", "AMD GPU"))
            vram_total = int(card.get("VRAM Total Memory (B)", card.get("vram_total", 0))) // (1024 * 1024)
            vram_used = int(card.get("VRAM Total Used Memory (B)", card.get("vram_used", 0))) // (1024 * 1024)
        except (json.JSONDecodeError, StopIteration, KeyError, ValueError):
            name, vram_total, vram_used = "AMD GPU", 0, 0

        # Get arch from rocminfo
        arch = "unknown"
        ri = run(["rocminfo"])
        if ri:
            for line in ri.splitlines():
                if "gfx" in line.lower() and "name" in line.lower():
                    arch = line.split()[-1]
                    break

        # ROCm version
        rocm_ver = run(["cat", "/opt/rocm/.info/version"])

        return {
            "platform": "ROCm",
            "name": name,
            "arch": arch,
            "vram_total_mb": vram_total,
            "vram_used_mb": vram_used,
            "vram_free_mb": vram_total - vram_used,
            "driver": f"ROCm {rocm_ver}" if rocm_ver else "ROCm",
        }

    # Try NVIDIA
    out = run(["nvidia-smi", "--query-gpu=name,memory.total,memory.used,memory.free,driver_version,compute_cap",
               "--format=csv,noheader,nounits"])
    if out:
        parts = [p.strip() for p in out.split(",")]
        if len(parts) >= 6:
            return {
                "platform": "CUDA",
                "name": parts[0],
                "arch": f"sm_{parts[5].replace('.', '')}",
                "vram_total_mb": int(parts[1]),
                "vram_used_mb": int(parts[2]),
                "vram_free_mb": int(parts[3]),
                "driver": f"CUDA {parts[4]}",
            }

    return None


def kv_size_mb(layers, kv_heads, head_dim, ctx, kv_type):
    """Calculate KV cache size in MB."""
    bpe = KV_BYTES[kv_type]
    # 2 for K+V
    return (2 * layers * kv_heads * head_dim * ctx * bpe) / (1024 * 1024)


def max_ctx(layers, kv_heads, head_dim, kv_type, available_mb):
    """Max context that fits in available VRAM."""
    bpe = KV_BYTES[kv_type]
    bytes_per_token = 2 * layers * kv_heads * head_dim * bpe
    if bytes_per_token == 0:
        return 0
    return int((available_mb * 1024 * 1024) / bytes_per_token)


def recommend(model_key, quant, ctx, gpu):
    """Generate recommendation table."""
    model_key = model_key.lower().replace(" ", "-")
    profile = MODELS.get(model_key)
    if not profile:
        # Try fuzzy match
        for k in MODELS:
            if k in model_key or model_key in k:
                profile = MODELS[k]
                model_key = k
                break
    if not profile:
        return f"Unknown model '{model_key}'. Known: {', '.join(sorted(MODELS.keys()))}"

    layers, kv_heads, head_dim, is_swa = profile

    # Model size
    sizes = MODEL_SIZES.get(model_key, {})
    model_gb = sizes.get(quant, sizes.get("Q4_K_M", 0))
    model_mb = model_gb * 1024

    available_for_kv = gpu["vram_free_mb"] - model_mb - OVERHEAD_MB

    lines = []
    lines.append(f"GPU: {gpu['name']} ({gpu['arch']})")
    lines.append(f"VRAM: {gpu['vram_total_mb']} MiB total, {gpu['vram_free_mb']} MiB free")
    lines.append(f"Platform: {gpu['driver']}")
    lines.append("")
    lines.append(f"Model: {model_key} {quant} ({model_gb:.1f} GiB)")
    lines.append(f"Context: {ctx:,} tokens")
    if is_swa:
        lines.append("⚠ SWA model — turbo on SWA layers causes quality loss. Use f16 for SWA.")
    lines.append("")
    lines.append(f"  {'KV type':<10}| {'KV size':>8} | {'Total VRAM':>10} | {'Fits?':>5} | {'Max context':>11}")
    lines.append(f"  {'-'*10}|{'-'*10}|{'-'*12}|{'-'*7}|{'-'*13}")

    best = None
    for kv_type in ["f16", "q4_0", "turbo3", "turbo4"]:
        kv_mb = kv_size_mb(layers, kv_heads, head_dim, ctx, kv_type)
        total = model_mb + kv_mb + OVERHEAD_MB
        fits = total <= gpu["vram_free_mb"]
        mctx = max_ctx(layers, kv_heads, head_dim, kv_type, available_for_kv)
        lines.append(f"  {kv_type:<10}| {kv_mb:>6.0f} MB | {total:>8.0f} MB | {'YES' if fits else ' NO':>5} | ~{mctx // 1000}K")
        if fits and best is None:
            best = kv_type

    lines.append("")
    if best:
        if best == "f16":
            lines.append("Recommendation: f16 — model fits with full precision KV cache.")
        elif best == "q4_0":
            lines.append("Recommendation: q4_0 — good compression, widely supported.")
        elif best == "turbo3":
            lines.append("Recommendation: turbo3 — best quality/compression tradeoff.")
            lines.append("  Requires: TurboQuant-compatible llama.cpp build")
            lines.append("  Repo: https://github.com/domvox/llama.cpp-turboquant-hip")
        else:
            lines.append(f"Recommendation: {best} — needed to fit in VRAM.")
            lines.append("  Requires: TurboQuant-compatible llama.cpp build")
            lines.append("  Repo: https://github.com/domvox/llama.cpp-turboquant-hip")
        lines.append("")
        cmd = f"  llama-server -m model.gguf -ngl 99 --ctx-size {ctx}"
        if best != "f16":
            cmd += f" \\\n    --cache-type-k {best} --cache-type-v {best}"
            if is_swa:
                cmd += f" \\\n    --cache-type-k-swa f16 --cache-type-v-swa f16"
        lines.append(cmd)
    else:
        lines.append("⚠ Model does not fit in VRAM even with turbo4. Try a smaller quant or model.")

    return "\n".join(lines)


def check(model_size_gb, ctx, kv_type, gpu):
    """Quick check if a config fits."""
    model_mb = model_size_gb * 1024
    # Use generic 27B-class profile as fallback
    layers, kv_heads, head_dim = 64, 8, 128
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

    elif args.cmd == "recommend":
        gpu = detect_gpu()
        if not gpu:
            print("No GPU detected.", file=sys.stderr)
            sys.exit(1)
        print(recommend(args.model, args.quant, args.ctx, gpu))

    elif args.cmd == "check":
        gpu = detect_gpu()
        if not gpu:
            print("No GPU detected.", file=sys.stderr)
            sys.exit(1)
        check(args.model_size, args.ctx, args.kv_type, gpu)

    else:
        p.print_help()


if __name__ == "__main__":
    main()
