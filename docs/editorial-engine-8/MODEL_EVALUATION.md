# Phase 4 — Multimodal Model Evaluation Report

Status: `IN_PROGRESS`

## Candidate Local Models Available for Empirical Benchmarking
Hardware under test: NVIDIA GeForce RTX 3050 Laptop GPU (4096 MiB VRAM), 16 GB System RAM, Ollama `0.40.16`.
- `qwen3-vl:2b` (1.9 GB on disk) — Qwen3-VL 2B Instruct quantized via Ollama
- `moondream:latest` (1.7 GB on disk) — Moondream2 1.8B via Ollama
- `cv_heuristic_fallback` (0 MB VRAM, CPU-only OpenCV/PyAV) — Deterministic no-VLM baseline

## Pending Empirical Measurements (Executed in Phase 4)
To be populated by `verification/benchmark_vlm.py` on the 10-case frame-sequence benchmark:
1. Coherent GTA multi-shot event
2. Driving followed by unrelated boat scene
3. Gameplay followed by title card (`PUMBA PRESENTS`)
4. Title card followed by aircraft footage
5. Scene cuts inside one continuous action
6. Two unrelated scenes sharing similar appearance
7. End card without long silence (`PUMBA`)
8. Gameplay with continuous background music
9. Gameplay with no speech
10. Podcast / two-speaker cut switching

Metrics to measure empirically: accuracy, false continuity merges, false discontinuity splits, end-card detection recall, schema validity rate, median latency (s), peak VRAM (MiB via `nvidia-smi`), peak RAM (MB), failure rate.
