# Ollama 0.40.16 refresh experiment

The patch targets upstream commit `d63b702609c4300a2ca07be2bdb0adb9834725e5`. Set `OLLAMA_GPU_REFRESH_TIMEOUT` to a positive Go duration such as `15s`. The experimental default is 15 seconds per refresh phase. The longer initial discovery and memory admission logic are unchanged.

Build from PowerShell at the Factory repository root. The experimental image compiles the Go entrypoint using the upstream CGO and PIE build flags and reuses the pinned release's CUDA libraries.

```powershell
$files = Resolve-Path verification/factory10/ollama-refresh
$ctx = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid().ToString())
New-Item -ItemType Directory $ctx | Out-Null
git clone --depth 1 --branch v0.40.16 https://github.com/ollama/ollama.git "$ctx/source"
if ((git -C "$ctx/source" rev-parse HEAD) -ne 'd63b702609c4300a2ca07be2bdb0adb9834725e5') { throw 'Unexpected upstream source' }
git -C "$ctx/source" apply --check "$files/refresh.patch"
if ($LASTEXITCODE -ne 0) { throw 'Patch check failed' }
Copy-Item "$files/Dockerfile","$files/refresh.patch" $ctx
docker build -t factory10-ollama:0.40.16-refresh15 $ctx
if ($LASTEXITCODE -ne 0) { throw 'Build failed' }
docker run --rm factory10-ollama:0.40.16-refresh15 --version
```

Run during a Factory idle window with native Ollama stopped. The cache is mounted read-only, no model is pulled, and the experimental API binds to loopback. Replace the JPEG paths with three authorized frames in chronological order. Use the Factory Python environment for the probe.

```powershell
docker stop youtube-temka-ollama-1
if ($LASTEXITCODE -ne 0) { throw 'Stock Ollama did not stop' }
try {
    docker run -d --name factory10-ollama-refresh --gpus all --memory 4g --memory-swap 4g --cpus 4 -p 127.0.0.1:11435:11434 -e OLLAMA_DEBUG=1 -e OLLAMA_LLM_LIBRARY=cuda_v12 -e OLLAMA_NUM_PARALLEL=1 -e OLLAMA_MAX_LOADED_MODELS=1 -e OLLAMA_GPU_REFRESH_TIMEOUT=15s --mount type=volume,source=youtube-temka_ollama_models,target=/root/.ollama/models,volume-subpath=models,readonly factory10-ollama:0.40.16-refresh15
    if ($LASTEXITCODE -ne 0) { throw 'Experimental Ollama did not start' }
    $deadline = (Get-Date).AddSeconds(45)
    do {
        try { $ready = Invoke-RestMethod http://127.0.0.1:11435/api/version -TimeoutSec 2 } catch { Start-Sleep 1 }
    } until ($ready -or (Get-Date) -ge $deadline)
    if (-not $ready) { throw 'Experimental Ollama not ready' }
    .venv/Scripts/python.exe -m verification.factory10.ollama-refresh.probe frame1.jpg frame2.jpg frame3.jpg
    if ($LASTEXITCODE -ne 0) { throw 'Cold-reload verification failed' }
} finally {
    docker stop factory10-ollama-refresh
    docker start youtube-temka-ollama-1
}
```
