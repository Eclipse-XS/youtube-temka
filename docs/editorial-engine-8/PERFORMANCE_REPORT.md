# Phase 10 — Performance Engineering Report

Status: `IN_PROGRESS`

## Hardware Profile
- GPU: NVIDIA GeForce RTX 3050 Laptop GPU (4096 MiB total VRAM, 3962 MiB free idle)
- RAM: ~15.2 GiB total physical memory (Windows 11)
- Local Ollama: `0.40.16` with `qwen2.5:3b` (1.9 GB), `qwen3-vl:2b` (1.9 GB), `moondream:latest` (1.7 GB)

## Baseline Measurements (`aef60f1` on 617.906 s GTA source)
- Coarse visual + audio sampling (309 seeks): `21.62 s`
- Independent planning + local fine inspection (32 seeks × 3 + 1 Ollama call): `171.52 s`
- Connected Story (6 Ollama calls): `314.10 s`
- Peak VRAM / RAM: Not recorded in baseline.

## Factory 8.0 Measured Performance
*(To be populated with actual measured timings, peak VRAM, peak RAM, disk usage, model call counts, and cache hit rates during Phase 4, Phase 10, and Phase 11 runs.)*
