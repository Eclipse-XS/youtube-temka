# syntax=docker/dockerfile:1.7
FROM python:3.12-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df
# The same pinned Deno runtime used by the OpenShorts foundation. yt-dlp's
# installed EJS solver runs with restricted runtime permissions.
COPY --from=denoland/deno:bin@sha256:b507583d3c68ba69f3ed2ce5969ae5b8b70f43421c781279c7aea06435263543 /deno /usr/local/bin/deno
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-noto-core ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements-factory.lock ./
RUN --mount=type=cache,target=/root/.cache/pip pip install --timeout 300 --retries 8 -r requirements-factory.lock
COPY requirements-tts.lock requirements-factory-gpu.lock ./
COPY deploy/download-wheels.py deploy/gpu-wheels.json /opt/gpu-build/
ARG WITH_TTS=0
RUN if [ "$WITH_TTS" = "1" ]; then pip install --no-cache-dir -r requirements-tts.lock; fi
ARG GPU=0
RUN --mount=type=cache,target=/root/.cache/pip --mount=type=cache,target=/root/.cache/factory-wheels --mount=type=bind,source=deploy/wheels,target=/seed if [ "$GPU" = "1" ]; then python /opt/gpu-build/download-wheels.py /root/.cache/factory-wheels && pip install --no-index --find-links=/root/.cache/factory-wheels --require-hashes --only-binary=:all: -r requirements-factory-gpu.lock; fi
ENV LD_LIBRARY_PATH=/usr/local/lib/python3.12/site-packages/nvidia/cublas/lib:/usr/local/lib/python3.12/site-packages/nvidia/cudnn/lib:/usr/local/lib/python3.12/site-packages/nvidia/cuda_nvrtc/lib
# Explicit allowlist: commercial cloud/ and OAuth files never enter this image.
COPY factory ./factory
COPY docs/licenses ./docs/licenses
COPY subtitles.py transcribe_backends.py ffmpeg_utils.py gpu_decode.py jsonfile.py security_utils.py ssrf_guard.py LICENSE NOTICE ./
RUN useradd --uid 10001 --create-home factory && mkdir -p /data /scratch /home/factory/.cache && chown factory /data /scratch /home/factory/.cache
USER factory
ENV FACTORY_DATA=/data PYTHONUNBUFFERED=1 WHISPER_DEVICE=cpu WHISPER_COMPUTE=int8 ASR_HOST_SLOTS=1 FFMPEG_THREADS=2
HEALTHCHECK --interval=15s --timeout=3s --start-period=20s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health',timeout=2)"
CMD ["uvicorn","factory.api:app","--host","0.0.0.0","--port","8000"]
