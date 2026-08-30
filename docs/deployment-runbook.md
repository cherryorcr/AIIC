# AIIC deployment runbook

## Current topology

- CPU application host: `146.56.204.146` (`ubuntu`), Docker Compose runs
  PostgreSQL 16, FastAPI backend and the Nginx frontend.
- GPU host: `100.126.175.112` (`pc-rack-server`), two RTX 4090 cards run the
  existing Qwen3-32B-AWQ vLLM service as
  `Qwen3-32B-AWQ-vLLM` on port 8000. With the current 32K context/64 sequence
  settings it uses about 42.6 GB on each 48 GB card.
- The GPU host maintains a restricted, systemd-managed SSH reverse tunnel to
  the CPU host's Docker bridge address `172.18.0.1:18000`. The backend reaches
  it through `host.docker.internal:18000`; the model port is not published by
  the CPU Compose project or bound on a public CPU interface.

## CPU host commands

```bash
cd /home/ubuntu/aiic/backend
docker compose -f deploy/compose.cpu.yml up -d --build
docker compose -f deploy/compose.cpu.yml ps
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8080/health
```

The deployed backend uses PostgreSQL and seeds `data/approved-dataset.json`.
Secrets are stored only in `/home/ubuntu/aiic/backend/.env` and
`/home/ubuntu/aiic/secrets/`, with mode `0600`.

## GPU host checks

```bash
nvidia-smi
systemctl status aiic-model-tunnel.service
curl http://127.0.0.1:8000/v1/models
```

The vLLM process is managed by the host's existing model startup service. The
reverse tunnel unit is checked in as `backend/deploy/aiic-model-tunnel.service`
for reproducibility.

## External access

The frontend listens on TCP 8080. If `http://146.56.204.146:8080` is not
reachable externally, add an inbound TCP/8080 rule in the Tencent Cloud security
group (the container and host listener are already healthy). Keep PostgreSQL,
FastAPI port 8000, model port 8000 on the GPU host, and tunnel port 18000
closed to the public Internet.

## Model provider status

The local Qwen gateway is healthy and remains the fallback for question
generation and evaluation. The third-party strong-model endpoint is configured
as an OpenAI-compatible gateway using model `codex-auto-review`. Keep its key
only in the CPU host `.env` (mode `0600`); never commit or print it. If the
provider is unavailable, the router automatically falls back to Qwen and then
the deterministic rubric evaluator.
