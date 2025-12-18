# GPU Monitoring System - A6000 48GB Remote Monitoring

## Overview

Comprehensive GPU monitoring system for remote NVIDIA A6000 48GB GPU hosted on Vast.ai. Provides real-time metrics, automated alerting, web dashboard, and Telegram bot integration.

## Features

### Core Monitoring (`core/gpu_monitor.py`)
- **Remote SSH Monitoring**: Connect to GPU node via SSH and execute nvidia-smi
- **Real-time Metrics**: VRAM usage, GPU utilization, temperature, power draw
- **Caching**: 10-second cache with background updates every 30 seconds
- **History Tracking**: Store metrics history for trend analysis
- **Health Checks**: Automated health status based on configurable thresholds
- **Fallback Support**: Return cached data on connection errors

### Alerting System (`core/gpu_alerts.py`)
- **Background Monitoring**: Check GPU metrics every 60 seconds
- **Alert Conditions**:
  - VRAM > 90% for 2 minutes → Warning
  - VRAM > 95% for 30 seconds → Critical
  - Temperature > 80°C → Warning
  - Temperature > 85°C → Critical
  - GPU offline > 5 minutes → Critical
- **Rate Limiting**: Max 1 alert per condition per 15 minutes
- **Auto-Resolution**: Automatically resolve alerts when conditions clear
- **Telegram Notifications**: Send alerts to admin via Telegram bot
- **Redis History**: Store alert history with 7-day TTL

### Web Dashboard (`backend/templates/gpu_dashboard.html`)
- **Real-time Updates**: Live metrics with 10-second polling
- **Visual Indicators**: Color-coded progress bars and status badges
- **VRAM Monitoring**: Usage graphs with warning/critical thresholds
- **Temperature Tracking**: Real-time temperature with visual alerts
- **Alert History**: Display recent alerts with timestamps
- **Responsive Design**: Works on desktop and mobile

### API Endpoints
- `GET /system/gpu` - Get current GPU metrics and health status
- `GET /system/gpu?history_minutes=60` - Include historical data
- `GET /system/gpu/alerts` - Get alert status and history
- `GET /dashboard/gpu` - HTML dashboard for monitoring

### Telegram Bot Commands
- `/gpu` - Show current GPU status (VRAM, utilization, temperature)
- `/gpu_history` - Display 60-minute metrics trends and statistics
- `/gpu_alerts` - List recent alerts (last 24 hours)

### System Integration
- **AutoBug**: GPU health check integrated into system diagnostics
- **System Status**: GPU metrics included in `/system/status` endpoint

## Configuration

### Environment Variables

Add these to your `.env` or `ENV_A6000_48GB_OPTIMIZED.env`:

```bash
# GPU Monitoring Mode
GPU_MONITORING_MODE=remote  # auto, local, remote, disabled

# SSH Connection to GPU Node (Vast.ai)
GPU_SSH_HOST=localhost
GPU_SSH_PORT=22
GPU_SSH_USER=root
GPU_SSH_KEY_PATH=/path/to/ssh/key
GPU_SSH_PASSWORD=  # Optional, prefer key auth
GPU_SSH_TIMEOUT=10

# Metrics Caching
GPU_METRICS_CACHE_TTL=10
GPU_BACKGROUND_UPDATE_INTERVAL=30

# Alert Thresholds
GPU_ALERT_ENABLED=1
GPU_ALERT_VRAM_WARNING=90
GPU_ALERT_VRAM_CRITICAL=95
GPU_ALERT_TEMP_WARNING=80
GPU_ALERT_TEMP_CRITICAL=85
GPU_ALERT_OFFLINE_CRITICAL_MINUTES=5

# Alert Duration Thresholds
GPU_ALERT_VRAM_WARNING_DURATION=120  # 2 minutes
GPU_ALERT_VRAM_CRITICAL_DURATION=30  # 30 seconds

# Alert Configuration
GPU_ALERT_CHECK_INTERVAL=60
GPU_ALERT_RATE_LIMIT_SECONDS=900  # 15 minutes
GPU_ALERT_HISTORY_TTL_DAYS=7

# Telegram Configuration (for alerts)
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_ADMIN_CHAT_ID=your_chat_id

# AutoBug GPU Check
AUTOBUG_ENABLE_GPU=1
AUTOBUG_GPU_TIMEOUT_S=10.0

# Backend URLs (for Telegram bot)
QUANTUM_GPU_URL=http://127.0.0.1:8081/system/gpu
QUANTUM_GPU_ALERTS_URL=http://127.0.0.1:8081/system/gpu/alerts
```

## Setup Instructions

### 1. Install Dependencies

```bash
pip install paramiko>=3.0.0
```

Optional (for full functionality):
```bash
pip install redis>=5.0.0
pip install python-telegram-bot>=20.0
```

### 2. Configure SSH Access

**Option A: SSH Key Authentication (Recommended)**
```bash
# Generate SSH key if you don't have one
ssh-keygen -t rsa -b 4096 -f ~/.ssh/vast_gpu_key

# Copy public key to Vast.ai GPU instance
ssh-copy-id -i ~/.ssh/vast_gpu_key.pub root@your-vast-ip

# Set in .env
GPU_SSH_KEY_PATH=/home/user/.ssh/vast_gpu_key
GPU_SSH_HOST=your-vast-ip
GPU_SSH_PORT=22
GPU_SSH_USER=root
```

**Option B: SSH Tunnel (for security)**
```bash
# Create SSH tunnel from VPS to Vast.ai GPU
ssh -N -L 2222:localhost:22 root@your-vast-ip &

# Set in .env
GPU_SSH_HOST=localhost
GPU_SSH_PORT=2222
GPU_SSH_USER=root
GPU_SSH_KEY_PATH=/path/to/key
```

### 3. Verify nvidia-smi Access

Test that nvidia-smi works on the GPU node:

```bash
ssh -p 22 root@your-vast-ip "nvidia-smi --query-gpu=index,name,memory.used,memory.total,utilization.gpu,temperature.gpu,power.draw --format=csv,noheader,nounits"
```

Expected output:
```
0, NVIDIA A6000, 12345, 49140, 75, 65, 250.5
```

### 4. Start Backend Server

```bash
cd "Contabo VPS/quantumdev-open"
python3 backend/quantum_api.py
```

Backend will start on `http://127.0.0.1:8081`

### 5. Start Telegram Bot (Optional)

```bash
python3 scripts/telegram_bot.py
```

### 6. Access Dashboard

Open your browser to: `http://your-server-ip:8081/dashboard/gpu`

## Usage Examples

### Python API

```python
from core.gpu_monitor import get_gpu_monitor

# Get GPU monitor instance
monitor = get_gpu_monitor()

# Get current metrics
metrics = monitor.get_metrics()
print(f"VRAM: {metrics['gpus'][0]['memory_percent']:.1f}%")
print(f"Temperature: {metrics['gpus'][0]['temperature']:.1f}°C")

# Get historical data
history = monitor.get_metrics_history(minutes=60)
print(f"History entries: {len(history)}")

# Check health
is_healthy = monitor.is_healthy()
should_alert, alerts = monitor.should_alert()

if should_alert:
    for alert in alerts:
        print(f"Alert: {alert}")
```

### REST API

**Get current GPU status:**
```bash
curl http://localhost:8081/system/gpu
```

**Get GPU status with history:**
```bash
curl "http://localhost:8081/system/gpu?history_minutes=60"
```

**Get alerts:**
```bash
curl "http://localhost:8081/system/gpu/alerts?hours=24"
```

### Telegram Bot

Send these commands in your Telegram chat:

```
/gpu
```
Output:
```
🖥️ GPU Status:

✅ Status: OK
📡 Mode: REMOTE

🎮 GPU 0: NVIDIA A6000
🟢 VRAM: 18.5 / 48.0 GB (38.5%)
⚡ Utilization: 75.0%
🟢 Temperature: 65.0°C
⚡ Power: 250.5W

✅ Health: HEALTHY
```

## Monitoring Modes

### Auto Mode (Recommended)
```bash
GPU_MONITORING_MODE=auto
```
- Tries remote monitoring first
- Falls back to local pynvml if remote fails
- Best for flexible deployments

### Remote Mode
```bash
GPU_MONITORING_MODE=remote
```
- Only uses SSH remote monitoring
- Use when GPU is on separate machine (Vast.ai)
- Requires SSH configuration

### Local Mode
```bash
GPU_MONITORING_MODE=local
```
- Only uses pynvml (local GPU)
- Use when GPU is on the same machine
- Requires nvidia-ml-py package

### Disabled Mode
```bash
GPU_MONITORING_MODE=disabled
```
- Disables GPU monitoring completely

## Alerting Rules

### VRAM Alerts
- **Warning**: VRAM > 90% for 2 consecutive minutes
- **Critical**: VRAM > 95% for 30 consecutive seconds

### Temperature Alerts
- **Warning**: Temperature > 80°C (immediate)
- **Critical**: Temperature > 85°C (immediate)

### Offline Alerts
- **Critical**: GPU monitoring offline for 5+ minutes

### Rate Limiting
- Maximum 1 alert per condition per 15 minutes
- Prevents notification spam

### Auto-Resolution
- Alerts automatically resolve when condition clears
- Resolution notification sent to Telegram

## Troubleshooting

### SSH Connection Issues

**Problem**: "SSH connection failed"
```bash
# Test SSH connection manually
ssh -p 22 root@your-vast-ip

# Check SSH key permissions
chmod 600 ~/.ssh/vast_gpu_key

# Test nvidia-smi command
ssh -p 22 root@your-vast-ip "nvidia-smi"
```

**Problem**: "nvidia-smi: command not found"
```bash
# Verify nvidia-smi is installed on GPU node
ssh root@your-vast-ip "which nvidia-smi"

# Check NVIDIA driver
ssh root@your-vast-ip "nvidia-smi --version"
```

### Monitoring Not Working

**Check logs:**
```bash
# Backend logs
tail -f /var/log/quantum-api.log

# GPU monitor logs (if configured)
tail -f /var/log/gpu-monitor.log
```

**Test API endpoint:**
```bash
curl -v http://localhost:8081/system/gpu
```

**Check AutoBug diagnostics:**
```bash
curl http://localhost:8081/autobug/run | jq '.checks[] | select(.name == "gpu")'
```

### Alert Issues

**Alerts not sending:**
```bash
# Check alert manager status
curl http://localhost:8081/system/gpu/alerts | jq '.status'

# Verify Telegram configuration
echo $TELEGRAM_BOT_TOKEN
echo $TELEGRAM_ADMIN_CHAT_ID

# Test Telegram bot
python3 -c "
from agents.telegram_bot_agent import TelegramBotAgent
bot = TelegramBotAgent()
bot.send_message('YOUR_CHAT_ID', 'Test message')
"
```

**Redis not available:**
- Alert history won't persist across restarts
- Active alerts still work
- Consider installing Redis for production

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   VPS (Contabo)                     │
│                                                     │
│  ┌─────────────────────────────────────────────┐  │
│  │         Backend (quantum_api.py)            │  │
│  │                                             │  │
│  │  • /system/gpu endpoint                    │  │
│  │  • /system/gpu/alerts endpoint             │  │
│  │  • /dashboard/gpu HTML dashboard           │  │
│  └─────────────────┬───────────────────────────┘  │
│                    │                               │
│  ┌─────────────────▼───────────────────────────┐  │
│  │      GPU Monitor (gpu_monitor.py)          │  │
│  │                                             │  │
│  │  • SSH connection to GPU node              │  │
│  │  • nvidia-smi parsing                      │  │
│  │  • Metrics caching (10s TTL)               │  │
│  │  • Background updates (30s)                │  │
│  └─────────────────┬───────────────────────────┘  │
│                    │                               │
│  ┌─────────────────▼───────────────────────────┐  │
│  │    Alert Manager (gpu_alerts.py)           │  │
│  │                                             │  │
│  │  • Background monitoring (60s)             │  │
│  │  • Alert conditions evaluation             │  │
│  │  • Rate limiting (15m cooldown)            │  │
│  │  • Auto-resolution                         │  │
│  └─────────────────┬───────────────────────────┘  │
│                    │                               │
│  ┌─────────────────▼───────────────────────────┐  │
│  │   Telegram Bot (telegram_bot.py)           │  │
│  │                                             │  │
│  │  • /gpu command                            │  │
│  │  • /gpu_history command                    │  │
│  │  • /gpu_alerts command                     │  │
│  │  • Alert notifications                     │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
                           │
                           │ SSH (port 22 or tunnel)
                           │
┌──────────────────────────▼──────────────────────────┐
│              GPU Node (Vast.ai)                     │
│                                                     │
│  ┌─────────────────────────────────────────────┐  │
│  │      NVIDIA A6000 48GB                      │  │
│  │                                             │  │
│  │  • nvidia-smi monitoring                   │  │
│  │  • vLLM API (port 5000)                    │  │
│  │  • DeepSeek-R1-Distill-Qwen-32B           │  │
│  └─────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────┘
```

## Security Considerations

1. **SSH Key Authentication**: Always prefer SSH keys over passwords
2. **SSH Tunneling**: Use SSH tunnels to avoid exposing GPU node directly
3. **Firewall Rules**: Restrict SSH access to known IPs
4. **Telegram Admin**: Only send alerts to authorized admin chat IDs
5. **API Access**: Consider adding authentication to dashboard endpoint

## Performance Impact

- **CPU**: < 1% average (monitoring overhead)
- **Memory**: ~50MB for monitor + alerts (Python process)
- **Network**: ~1KB every 30 seconds for nvidia-smi via SSH
- **GPU Impact**: None (nvidia-smi is read-only)

## Future Enhancements

- [ ] Prometheus/Grafana integration
- [ ] Email alerts in addition to Telegram
- [ ] GPU metrics graphing (matplotlib/plotly)
- [ ] Multi-GPU support improvements
- [ ] WebSocket for real-time dashboard updates
- [ ] Custom alert rules configuration
- [ ] Alert acknowledgment system
- [ ] Performance profiling and optimization metrics

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review logs for error messages
3. Test SSH connection manually
4. Verify environment variables are set correctly

## License

Part of QuantumDev project - Matteo Loco © 2025
