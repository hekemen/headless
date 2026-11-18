# Headless AI Workstation

Local LLM inference rig: TabbyAPI serving ExLlamaV3 models over an OpenAI-compatible API, managed from the browser via code-server. No display attached — everything is driven remotely.

## Hardware

| Component | Spec |
|-----------|------|
| CPU | AMD Ryzen 9 5950X (16C / 32T, up to 5.9 GHz) |
| Motherboard | ASUS Pro WS X570-ACE |
| GPU | 2× NVIDIA GeForce RTX 3060 12 GB (PCIe, PHB host-bridge topology) |
| GPU driver | 595.71.05 |
| RAM | 32 GB DDR4 + 16 GB zram swap |
| Storage | Samsung 990 PRO 1 TB NVMe (OS), Samsung 850 500 GB SSD |
| OS | Ubuntu, kernel 7.0.0-43-generic |

The two GPUs sit behind separate PCIe host bridges (`nvidia-smi topo -m` shows `PHB`), with no NVLink — inter-GPU traffic goes through the CPU. That's why the P2P tuning below matters.

## Software Stack

| Tool | What it does | Link |
|------|--------------|------|
| [TabbyAPI](https://github.com/theroyallab/tabbyapi) | OpenAI-compatible API server for ExLlamaV3 models. Runs as `ghcr.io/theroyallab/tabbyapi:cu13`, exposed on port **8080** | <https://github.com/theroyallab/tabbyapi> |
| [code-server](https://github.com/coder/code-server) | VS Code in the browser — the admin console for this box. Systemd service (`code-server@hekemen.service`), port **8088** | <https://github.com/coder/code-server> |
| ExLlamaV3 | Model format + kernels. Models live in `models/` (EXL3 quants) | <https://github.com/turboderp/exllamav3> |
| [gpu-unlock](https://github.com/Zagitta/gpu-unlock) | DKMS kernel module that unlocks full-speed tensor cores on GeForce cards (see below) | <https://github.com/Zagitta/gpu-unlock> |
| [opencode](https://opencode.ai) | Terminal AI coding agent — the primary client of this API. The agent traffic in `logs/` (140k+ completions over 30 days) is opencode sessions talking to TabbyAPI | <https://github.com/sst/opencode> |

## Configuration

```
docker-compose.yaml      TabbyAPI container: GPU reservations, volumes
config-qwen38.yml        Model config → mounted as /app/config.yml for the Qwen3.8-27B stack
config-gemma4.yml        Model config for the Gemma 4 26B stack
cache/                   ExLlamaV3 KV-cache state (gitignored, 100s of GB)
models/                  EXL3 model weights (gitignored, 100s of GB)
logs/                    TabbyAPI logs (gitignored)
venv/                    Python env for the tuning scripts (gitignored, `make install`)
overclock.py             One-time GPU tuning (run with sudo, see below)
```

### TabbyAPI

- Started with `docker compose up -d` — reserves all NVIDIA GPUs, sets `shm_size: 8gb`, `expandable_segments:True` to reduce CUDA OOM fragmentation, and maps `./cache`, `./models`, `./logs` into the container.
- The active config is mounted at `/app/config.yml`. Key knobs in the config files:
  - `model.model_name` / `model.model_dir` — which EXL3 quant to serve
  - `model.cache_size` — KV cache size in MB (sized to fit 3 concurrent sessions with idle prefixes kept)
  - `model.cache_mode` — e.g. `6,4` (FP6/FP4 KV) or `Q8` (quantized KV to save VRAM per session)
  - `model.max_seq_len` — context length
  - `network.disable_auth: true` — fine on a trusted LAN; add auth if you expose it further
- API base URL: `http://<host>:8080/v1` (OpenAI-compatible chat completions).

### code-server

- Runs as a per-user systemd service on port 8088 (`cert: false` — local network only).
- This is the day-to-day entry point: edit configs, `docker compose` commands, watch `logs/`, run the tuning script.

### Setup

```bash
make install     # create venv/ + install Python deps (pynvml, huggingface-hub, PyYAML)
sudo ./venv/bin/python overclock.py   # one-time GPU tuning, applies and exits
docker compose up -d
```

`overclock.py` applies per-GPU profiles and exits (no keep-alive loop): persistence mode, locked core clocks, VRAM VF-curve offset, power caps, and a forced fan profile for the hot sandwiched card. Locked state persists until a driver reset (reboot, `nvidia-smi -rgc -rmc -rac`).

Current state (from `nvidia-smi`, profile applied):

| GPU | Core clock | Memory clock | Power draw / limit | Temp |
|-----|-----------|--------------|--------------------|------|
| 0 | 1800 MHz (locked, max boost 2160) | 8201 MHz (max 8401) | 99.6 W / 200 W | 60 °C |
| 1 | 1800 MHz (locked, max boost 2160) | 8201 MHz (max 8401) | 102.7 W / 200 W | 56 °C |

Both cards run with persistence mode enabled. Stock memory clock is ~7301 MHz; the +900 MHz VF-curve offset in `overclock.py` takes it to 8201 MHz.

## Performance

Figures below are from the container logs (`logs/`, Nov 2026) under a real opencode agent workload — 45k–74k-token prompts with 98–100% prompt-cache hits, not a synthetic benchmark.

| Metric | Value |
|--------|-------|
| Model load | 19.4 s (tensor-parallel across both GPUs, 67 modules) |
| Generation | 22–43 tok/s per request |
| Prompt processing (prefill) | 264–383 tok/s on new tokens |
| Time to first token | 0.96–4.5 s (45k–74k token prompts, mostly cached) |
| Prompt cache hit rate | 98–100% (disk cache, 150 GB pool in `cache/`) |
| Speculative draft acceptance | 50–81% (MTP + 16-token hybrid drafting) |
| Errors | 0 in the most recent log |
| Traffic | ~142k `chat/completions` requests over 30 days |

Stack details: ExLlamaV3 1.6.7 with MTP speculative decoding, `cudaMallocAsync` backend, FP16 recurrent state. Throughput varies with prompt size and concurrent sessions — a micro-benchmark run while other sessions were active measured ~17 tok/s, so expect the table's range under normal agent load and less under contention.

## NVIDIA P2P & gpu-unlock

### PCIe P2P

The NVIDIA driver supports peer-to-peer DMA over PCIe, letting the two GPUs exchange data directly without bouncing through system RAM. Two things make it work well here:

- **`pcie_aspm=off`** in the GRUB kernel command line — disables PCIe active-state power management so the links don't drop into low-power states that add latency to P2P transfers.
- **`amd_iommu=on iommu=pt`** — IOMMU in passthrough mode avoids translation overhead on GPU DMA.

### gpu-unlock

Stock NVIDIA drivers cap GeForce cards at half their tensor-core rate: FP16/BF16/TF32 matmuls run at 1× while the silicon is capable of 2×. [gpu-unlock](https://github.com/Zagitta/gpu-unlock) is a DKMS kernel module that applies the SM speed-select override **before** the stock NVIDIA driver starts, so the cards run at full tensor rate — roughly 2× FP16/BF16 throughput, and ~25–55% faster LLM prefill on top of that.

- **v2.0.0**, "Ampere pre-driver hardware unlock", ships GA10x firmware (covers the GA106-based RTX 3060)
- Installed via DKMS (`/lib/modules/.../updates/dkms/gpu_unlock.ko.zst`) with its firmware bundled
- Opt-in via the kernel parameter **`gpu_unlock.targets=all`** in GRUB — without it the module stays dormant
- Independent of `overclock.py`: that script handles clocks/VRAM offset/power, gpu-unlock handles tensor-core rate