# 🚀 GPU Inference Node Setup (Vast.ai) - "The Muscles"

This guide covers setting up the GPU inference node that runs on GPU servers (e.g., Vast.ai).
The system acts as a pure compute backend, exposing OpenAI-compatible APIs consumed by the central server (VPS Contabo) via a secure SSH tunnel.

## 🏗 Architecture

* **Model:** `DeepSeek-R1-Distill-Qwen-32B-abliterated-Q6_K.gguf`
* **Engine:** Text Generation WebUI (Oobabooga) + `llama.cpp` loader
* **Hardware Target:** NVIDIA RTX A6000 / A40 (or higher with >24GB VRAM)
* **Connection:** API exposed on port `5000`, accessible ONLY via SSH Tunnel (no public internet exposure)

---

## 🛠 Setup & Recovery (Quick Start)

If the instance is destroyed or restarted, follow these steps to get back online in 2 minutes.

### 1. Starting the AI Server (Persistent)

To ensure the server automatically restarts on crash or memory errors, we use a loop script within `tmux`.

1. Access the Vast.ai terminal
2. Create/Enter tmux session:
   ```bash
   tmux new -s cervello
   ```

3. Launch the **Startup Loop** (Copy-paste the entire block):
   ```bash
   cd /workspace/text-generation-webui/
   
   while true; do
       echo "🧠 [$(date)] Starting AI Brain..."
       
       ./start_linux.sh --listen --api --api-port 5000 \
       --model DeepSeek-R1-Distill-Qwen-32B-abliterated-Q6_K.gguf \
       --loader llama.cpp \
       --n-gpu-layers 100 \
       --n_ctx 32768
       
       echo "⚠️ [$(date)] AI CRASHED! Auto-restart in 5 seconds..."
       sleep 5
   done
   ```

4. **Detach** (Let it run in background):
   * Press `CTRL` + `B`, release, then press `D`
   * Or simply close the terminal window

### 2. Check Status

To verify if the AI is running or to read logs:
```bash
tmux attach -t cervello
```

To detach again: `CTRL` + `B` then `D`

---

## 🔗 Connecting to the "Brain" (Contabo VPS)

The GPU is not exposed to the public internet. To connect it to the VPS running the application logic, we use a Reverse SSH Tunnel from the VPS side.

### Required Information from Vast.ai:

- `IP_HOST`: The public IP address of the instance
- `PORT_SSH`: The assigned SSH port (e.g., 31542)

### Command (run on Contabo VPS):

```bash
# Replace with current Vast instance data
ssh -o ServerAliveInterval=60 -N -L 5000:localhost:5000 root@IP_HOST -p PORT_SSH
```

See the README in the `deployment/` directory for the auto-reconnection tunnel script.

---

## 📂 Model Management

GGUF models should be placed in: `/workspace/text-generation-webui/user_data/models/`

### Download New Models

Example command to download models:
```bash
cd /workspace/text-generation-webui/
python download-model.py --output user_data/models/ TheBloke/Model-Name-GGUF
```

---

## 📝 Technical Notes

### Context Window
Set to 32768 tokens. If you encounter OOM (Out Of Memory) errors, reduce this value in the startup command.

### API Port
- **Port 5000**: OpenAI Compatible API (used in production)
- **Port 7860**: WebUI (active but not used for production)

### GPU Layers
The `--n-gpu-layers 100` parameter loads the entire model onto GPU. Adjust based on your VRAM:
- **48GB VRAM**: Use 100 (full offload)
- **24GB VRAM**: Try 40-60
- **Less than 24GB**: May need to reduce context window

---

## 🔧 Troubleshooting

### Server Won't Start
1. Check if port 5000 is already in use: `lsof -i :5000`
2. Verify model file exists in the models directory
3. Check available VRAM: `nvidia-smi`

### Connection Issues
1. Verify SSH tunnel is active on VPS side
2. Test local connection from GPU node: `curl http://localhost:5000/v1/models`
3. Check firewall rules if using public access (not recommended)

### Out of Memory
1. Reduce context window: `--n_ctx 16384` or `--n_ctx 8192`
2. Reduce GPU layers: `--n-gpu-layers 50`
3. Use a smaller quantization (Q4 instead of Q6)

---

## 🔒 Security Considerations

**IMPORTANT**: The GPU node should NEVER be exposed to the public internet directly.

- All access should be through SSH tunnels
- Use SSH key authentication only (disable password auth)
- Keep the instance SSH port randomized by Vast.ai
- Monitor for unauthorized access attempts

---

## 💡 Performance Tips

1. **Use tmux** for persistent sessions
2. **Monitor GPU usage** with `nvidia-smi -l 1`
3. **Set appropriate context window** based on your use case
4. **Use higher quantization** (Q6, Q8) for better quality if VRAM allows
5. **Enable GPU layers** to maximize performance

---

## 🚦 Quick Commands Reference

```bash
# Create/attach to tmux session
tmux new -s cervello
tmux attach -t cervello

# Detach from tmux
CTRL+B then D

# Kill tmux session
tmux kill-session -t cervello

# Monitor GPU
nvidia-smi -l 1

# Check if API is running
curl http://localhost:5000/v1/models

# View API logs (if detached from tmux)
tmux attach -t cervello
```

---

## 📊 Recommended Vast.ai Configuration

- **GPU**: RTX A6000 (48GB) or A40 (48GB)
- **RAM**: 32GB+ system RAM
- **Storage**: 100GB+ (for models and cache)
- **Network**: Unmetered bandwidth preferred

---

For more deployment information, see:
- [Deployment Checklist](DEPLOYMENT_CHECKLIST.md)
- [Full Deployment Guide](STEP2_DEPLOYMENT_GUIDE.md)
