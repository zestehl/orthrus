# Orthrus Deployment

---
status: approved
author: zestehl
date: 2026-04-10
parent: spec/INDEX.md
related: spec/04-apis/cli-spec.md, spec/04-apis/config-schema.md
---

## Table of Contents
1. [Overview](#1-overview)
2. [Installation](#2-installation)
3. [Docker](#3-docker)
4. [systemd Service (macOS)](#4-systemd-service-macos)
5. [Edge Node: Pi 5](#5-edge-node-pi-5)
6. [Configuration](#6-configuration)
7. [Monitoring](#7-monitoring)
8. [Backup](#8-backup)

---

## 1. Overview

Orthrus is a Python package (`orthrus`) installed via `pip` or `uv`. It runs as a background service (daemon) that captures agent interactions. Two deployment patterns are supported:

| Pattern | Host | Use case |
|---------|------|----------|
| **systemd service** | macOS (Mac Mini M1) | Primary host, runs 24/7 |
| **Docker** | Any Docker host | Isolation, easy migration |
| **Edge node** | Raspberry Pi 5 | AdGuard/MQTT/Grafana node, remote sync target |

### 1.1 Infrastructure Reference

| Node | Role | Hostname | Services |
|------|------|---------|----------|
| Mac Mini M1 | Primary host | `macmini-server.tailec92ef.ts.net` | HA, Docker/OrbStack |
| Pi 5 | Edge/sync target | `pi5control` | AdGuard, MQTT, Grafana |

Network: AT&T fiber / Eero (`192.168.4.0/22`), Tailscale (`100.65.187.70`).

---

## 2. Installation

### 2.1 Requirements

- Python 3.12+
- `uv` package manager (preferred)
- 500MB disk minimum

### 2.2 From PyPI (future)

```bash
uv pip install orthrus
```

### 2.3 From Source

```bash
git clone https://github.com/zestehl/orthrus.git
cd orthrus
uv pip install -e .
```

### 2.4 Initialize Config

```bash
orthrus config init
orthrus config validate
```

---

## 3. Docker

### 3.1 Dockerfile

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install orthrus
COPY pyproject.toml .
RUN uv pip install --system -e .

# Default config and data volumes
VOLUME ["/root/.orthrus", "/data"]

CMD ["orthrus", "capture", "enable"]
```

### 3.2 Build and Run

```bash
docker build -t orthrus:latest .
docker run -d \
  --name orthrus \
  --restart unless-stopped \
  -v orthrus-data:/root/.orthrus \
  -v /path/to/capture/data:/data \
  orthrus:latest
```

### 3.3 Docker Compose (recommended)

```yaml
services:
  orthrus:
    image: orthrus:latest
    container_name: orthrus
    restart: unless-stopped
    volumes:
      - orthrus-config:/root/.orthrus
      - orthrus-capture:/root/.orthrus/capture
    environment:
      - ORTHRUS_PROFILE=standard
    build: .
    healthcheck:
      test: ["CMD", "orthrus", "config", "validate"]
      interval: 5m
      timeout: 10s
      retries: 3

volumes:
  orthrus-config:
  orthrus-capture:
```

### 3.4 OrbStack Notes

On macOS with OrbStack (instead of Colima/limactl):

```bash
# OrbStack is already installed and running
docker context use orbstack  # if multiple contexts
docker compose up -d
```

Port 53 must remain available — do not run containerized DNS servers that bind port 53.

---

## 4. systemd Service (macOS)

Orthrus runs as a systemd user service on macOS via `launchd` (which provides `launchctl`). Alternatively, use a native macOS LaunchAgent plist.

### 4.1 LaunchAgent Plist

Create `~/Library/LaunchAgents/com.orthrus.capture.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.orthrus.capture</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/zestehl/Projects/orthrus/.venv/bin/orthrus</string>
        <string>capture</string>
        <string>run</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <dict>
        <key>SuccessfulExit</key>
        <false/>
    </dict>
    <key>StandardOutPath</key>
    <string>/tmp/orthrus.log</string>
    <key>StandardErrorPath</key>
    <string>/tmp/orthrus.err</string>
    <key>WorkingDirectory</key>
    <string>/Users/zestehl/Projects/orthrus</string>
</dict>
</plist>
```

### 4.2 Manage the Service

```bash
# Load (start on boot)
launchctl load ~/Library/LaunchAgents/com.orthrus.capture.plist

# Unload (stop)
launchctl unload ~/Library/LaunchAgents/com.orthrus.capture.plist

# Restart
launchctl unload ~/Library/LaunchAgents/com.orthrus.capture.plist
launchctl load ~/Library/LaunchAgents/com.orthrus.capture.plist

# Check status
launchctl list | grep orthrus
```

### 4.3 Install

```bash
cp ~/Projects/orthrus/deploy/macos/com.orthrus.capture.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.orthrus.capture.plist
```

---

## 5. Edge Node: Pi 5

The Pi 5 (`pi5control`) acts as a sync target and optional edge capture node. It runs AdGuard, MQTT, and Grafana alongside Orthrus sync.

### 5.1 OS Setup

```bash
# Install Raspberry Pi OS (64-bit)
# SSH access enabled
ssh pi@pi5control.local
```

### 5.2 Sync Target Configuration

On the primary host (Mac Mini), add to `~/.orthrus/config.yaml`:

```yaml
sync:
  enabled: true
  targets:
    - type: rsync
      path: pi@pi5control.local:/home/pi/orthrus-backup
      schedule: daily
      compression: zstd
      compression_level: 3
```

On the Pi 5, ensure rsync is installed and SSH key auth is configured:

```bash
# On Pi 5
sudo apt install rsync
mkdir -p /home/pi/orthrus-backup

# On Mac Mini (primary host)
ssh-copy-id pi@pi5control.local
```

### 5.3 Verify SSH Access

```bash
ssh -i ~/.ssh/id_orthrus pi@pi5control.local "ls /home/pi/orthrus-backup"
```

### 5.4 Test Sync

```bash
orthrus sync --target pi5-backup --dry-run
orthrus sync --target pi5-backup
```

### 5.5 Monitoring (Grafana)

Grafana is already running on Pi 5 (port 3000). Orthrus metrics can be exported via Prometheus.

See [hermes-metrics-exporter](../mlops/hermes-metrics-exporter/README.md) for Prometheus scrape configuration.

---

## 6. Configuration

### 6.1 Config File Location

Default: `~/.orthrus/config.yaml`

### 6.2 Production Profile

For the Mac Mini (primary host), use the `performance` profile:

```bash
orthrus config init --path ~/.orthrus/config.yaml
# Then edit: profile: performance
```

### 6.3 Environment Variables

| Variable | Description |
|----------|-------------|
| `ORTHRUS_CONFIG` | Path to config file (overrides default search) |
| `ORTHRUS_PROFILE` | Override resource profile |
| `AWS_ACCESS_KEY_ID` | S3 sync credentials |
| `AWS_SECRET_ACCESS_KEY` | S3 sync credentials |
| `AWS_DEFAULT_REGION` | S3 region (default: `us-east-1`) |

---

## 7. Monitoring

### 7.1 Health Check

```bash
orthrus capture status
```

Returns a table with queue depth, capture health, and embedding status.

### 7.2 Prometheus Metrics

Orthrus exports metrics via the Hermes metrics exporter endpoint. Scrape target: `http://localhost:8080/metrics` (or via Tailscale: `http://100.65.187.70:8080/metrics`).

### 7.3 Log Rotation

Logs are written to the capture directory. Configure log rotation in `/etc/logrotate.d/orthrus`:

```
/root/.orthrus/*.log {
    daily
    rotate 7
    compress
    delaycompress
}
```

---

## 8. Backup

### 8.1 Local Backup (rsync to Pi 5)

```bash
# Manual sync
orthrus sync --target pi5-backup

# Automated via cron
0 2 * * * orthrus sync --target pi5-backup >> ~/.orthrus/sync.log 2>&1
```

### 8.2 Backup Schedule

| Data class | Frequency | Retention |
|-----------|-----------|-----------|
| Capture (hot) | Daily | 30 days local |
| Warm storage | Weekly | 90 days local, 365 days remote |
| Archive | Monthly | Indefinite on Pi 5 |

### 8.3 Restore from Backup

```bash
# On Pi 5, pull data back to Mac Mini
orthrus sync --target pi5-backup --pull
```

---

## Related Documents

- [CLI Specification](spec/04-apis/cli-spec.md) — `orthrus capture`, `orthrus sync`
- [Config Schema](spec/04-apis/config-schema.md) — SyncConfig, SyncTarget, profile settings
- [Sync Module Spec](spec/02-architecture/modules/sync/README.md) — sync targets (local, rsync, S3)
- [Hermes Gateway Harness](../devops/hermes-gateway-harness/README.md) — Cloudflare DDNS + nginx gateway control plane
