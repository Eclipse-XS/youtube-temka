# Factory 10 target hardware

The Windows 11 host reported NVIDIA GeForce RTX 3050 6GB Laptop GPU, 6,144 MiB and driver 582.05. The operating system reported 16,312,205,312 bytes of RAM. WSL 2 was present and Docker Desktop's Linux engine reported version 29.8.0. This host is suitable for development evidence. Physical acceptance remains blocked pending the specified Ryzen 5 6600H, 16 GiB host and RTX 3050 Laptop GPU with 4,096 MiB.

The local probe reached model execution but timed out. Only requested GPU layers and host-wide resource samples were available. Actual model placement and real workload throughput remain open. [Development model measurements](PERFORMANCE.md)

## Run on the 4 GiB machine

From the target checkout, record `nvidia-smi --query-gpu=name,memory.total,driver_version --format=csv`, `wsl --list --verbose` and `docker info --format '{{.ServerVersion}} {{.OSType}}'`. Start Factory and install the vision tag in its containerized Ollama service. The model requires an Ollama release that supports Qwen3-VL. [Ollama Qwen3-VL model card](https://ollama.com/library/qwen3-vl:2b)

```powershell
.\scripts\start-factory.ps1 -Role Controller -Rebuild
docker compose -f docker-compose.yml -f compose.gpu.yml --profile controller exec -T ollama ollama pull qwen3-vl:2b
docker compose -f docker-compose.yml -f compose.gpu.yml --profile controller exec -T ollama ollama list
```

Place `manifest.json` in the authorized corpus folder. Create a private output directory on a disk with space for the three cold and three warm runs per workload. Inside that directory the runner creates a new subdirectory per invocation.

```powershell
$factory10Source = (Get-Location).Path
$factory10Corpus = (Resolve-Path 'D:/factory10-acceptance-corpus').Path
$factory10Output = (New-Item -ItemType Directory -Force 'D:/factory10-acceptance-results').FullName
$factory10Compose = @('-f','docker-compose.yml','-f','compose.gpu.yml','--profile','controller')
$factory10Mounts = @('-v',"${factory10Source}:/verify-code:ro",'-v',"${factory10Corpus}:/verify-corpus:ro",'-v',"${factory10Output}:/verify-results")
docker compose @factory10Compose run --rm --no-deps @factory10Mounts -w /verify-code --entrypoint python controller verification/factory10/accept_release.py --corpus /verify-corpus/manifest.json --corpus-root /verify-corpus --config /verify-code/verification/factory10/STABLE_PROFILE.json --output /verify-results/held-out-1 --mode acceptance --hardware-profile rtx3050-4gib --ollama http://ollama:11434
docker compose @factory10Compose run --rm --no-deps @factory10Mounts -w /verify-code --entrypoint python controller verification/factory10/accept_release.py --corpus /verify-corpus/manifest.json --corpus-root /verify-corpus --config /verify-code/verification/factory10/STABLE_PROFILE.json --output /verify-results/benchmark-1 --mode benchmark --hardware-profile rtx3050-4gib --ollama http://ollama:11434
```

`results.json` contains individual times, medians and maxima, stage durations, cache activity, decoded media checks, model placements when reported by Ollama, and sampled resources. VRAM samples describe the entire device. Review the model and encoder telemetry and record any fallback before awarding hardware or throughput points.
