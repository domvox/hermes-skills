---
name: gpu-advisor
description: Detect local GPU hardware and recommend optimal llama.cpp model + KV cache configuration. Supports AMD (ROCm) and NVIDIA (CUDA). Recommends TurboQuant KV compression when standard f16 cache won't fit.
version: 0.1.0
author: Dominik Kordek (domvox)
license: Apache-2.0
metadata:
  hermes:
    tags: [GPU, VRAM, llama.cpp, ROCm, CUDA, AMD, NVIDIA, KV Cache, TurboQuant, Optimization, Inference]
    related_skills: [gguf-quantization]
---

# GPU Advisor — Local Inference Optimization

Detect your GPU and get actionable recommendations for running LLMs locally with llama.cpp.

## When to Use

- User asks "what model can I run on my GPU?"
- User asks "will this model fit in my VRAM?"
- User is getting OOM errors with llama.cpp
- User wants to maximize context length on their hardware
- User asks about KV cache quantization or TurboQuant

## Prerequisites

- **AMD GPU**: `rocm-smi` available (ROCm installed)
- **NVIDIA GPU**: `nvidia-smi` available (CUDA drivers installed)
- Python 3.8+ (stdlib only, no dependencies)

## Commands

### Detect GPU

```bash
python3 scripts/gpu_advisor.py detect
```

Returns: GPU name, arch, VRAM total/used/free, driver version, compute platform.

### Recommend model configuration

```bash
python3 scripts/gpu_advisor.py recommend --model Qwen3.5-27B --quant Q5_K_M
```

Returns: whether it fits, recommended KV cache type (f16/q4_0/turbo3/turbo4), max context length, estimated throughput class.

### Check if a specific config fits

```bash
python3 scripts/gpu_advisor.py check --model-size 18.5 --ctx 80000 --kv-type turbo3
```

Returns: VRAM breakdown (model + KV + overhead), fit/no-fit verdict.

## How It Works

The advisor uses a simple VRAM budget model:

```
Total VRAM = Model weights + KV cache + Compute overhead (~500MB)

KV cache size = 2 × n_layers × n_kv_heads × head_dim × ctx_length × bytes_per_element
  f16:    2 bytes/element (baseline)
  q4_0:   0.5 bytes/element (4× compression)
  turbo3: 0.375 bytes/element (5.3× compression)
  turbo4: 0.25 bytes/element (8× compression)
```

For SWA models (Gemma 4), the advisor recommends f16 on SWA layers + turbo on global layers, because turbo on SWA causes catastrophic quality loss.

## Example Output

```
GPU: AMD Radeon RX 7900 XTX (gfx1100)
VRAM: 24576 MiB total, 22891 MiB free
Platform: ROCm 6.4

Model: Qwen3.5-27B Q5_K_M (18.5 GiB)
Context: 80,000 tokens

  KV type   | KV size  | Total VRAM | Fits? | Max context
  ----------|----------|------------|-------|------------
  f16       | 5,120 MB | 24,444 MB  |  NO   | ~62K
  q4_0      | 1,280 MB | 20,604 MB  |  YES  | ~250K
  turbo3    |   960 MB | 20,284 MB  |  YES  | ~330K
  turbo4    |   640 MB | 19,964 MB  |  YES  | ~500K

Recommendation: turbo3 — best quality/compression tradeoff.
  llama-server -m model.gguf -ngl 99 --ctx-size 80000 \
    --cache-type-k turbo3 --cache-type-v turbo3
```

## Known Model Profiles

The advisor includes VRAM profiles for popular models:

| Model | Params | Q4_K_M | Q5_K_M | Q8_0 | Layers | KV heads | Head dim |
|-------|--------|--------|--------|------|--------|----------|----------|
| Qwen3.5-9B | 9B | 5.5G | 6.6G | 9.5G | 40 | 8 | 128 |
| Qwen3.5-27B | 27B | 15.3G | 18.5G | 27.2G | 64 | 8 | 128 |
| Gemma-4-26B-A4B | 26B | 15.9G | — | — | 50 | 16 | 128 |
| Llama-3.1-8B | 8B | 4.9G | 5.7G | 8.5G | 32 | 8 | 128 |

## Limitations

- Throughput estimates are rough classes (fast/medium/slow), not precise tok/s
- SWA detection is based on known model names, not parsed from GGUF metadata
- TurboQuant requires a compatible llama.cpp build (upstream or domvox/llama.cpp-turboquant-hip)
