FROM golang:1.26.10 AS toolchain
FROM ubuntu:24.04 AS build
COPY --from=toolchain /usr/local/go /usr/local/go
ENV PATH=/usr/local/go/bin:$PATH CGO_ENABLED=1
RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates gcc g++ git && rm -rf /var/lib/apt/lists/*
WORKDIR /src
COPY source/go.mod source/go.sum ./
RUN --mount=type=cache,target=/root/go/pkg/mod go mod download
COPY source/ ./
COPY refresh.patch /tmp/refresh.patch
RUN git apply /tmp/refresh.patch
RUN --mount=type=cache,target=/root/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    go build -p 3 -trimpath -buildmode=pie -ldflags="-w -s -X github.com/ollama/ollama/version.Version=0.40.16" -o /ollama .
FROM ollama/ollama@sha256:910d0d8107b538fb0894e63163eb195de0cc7aefcbc666dc62d3b18f71124592
COPY --from=build /ollama /bin/ollama
