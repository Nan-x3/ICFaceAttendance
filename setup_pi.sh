#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Raspberry Pi Setup Script for Face Attendance System
#  Tested on: Raspberry Pi 4/5, Raspberry Pi OS (64-bit Bookworm)
#
#  Usage:  chmod +x setup_pi.sh && ./setup_pi.sh
# ═══════════════════════════════════════════════════════════════

set -e

echo "╔══════════════════════════════════════════════════╗"
echo "║  Face Attendance System — Raspberry Pi Setup     ║"
echo "╚══════════════════════════════════════════════════╝"
echo ""

# ── 1. System Updates ────────────────────────────────────────
echo "[1/5] Updating system packages..."
sudo apt-get update && sudo apt-get upgrade -y

# ── 2. Install system dependencies ───────────────────────────
echo "[2/5] Installing system dependencies..."
sudo apt-get install -y \
    python3-pip \
    python3-venv \
    cmake \
    build-essential \
    libatlas-base-dev \
    libhdf5-dev \
    libjasper-dev \
    libqt5gui5 \
    libqt5webkit5 \
    libqt5test5 \
    libgstreamer1.0-dev \
    python3-picamera2 \
    libcamera-dev \
    libopenblas-dev \
    liblapack-dev \
    gfortran

# ── 3. Create virtual environment ────────────────────────────
echo "[3/5] Setting up Python virtual environment..."
cd "$(dirname "$0")"
python3 -m venv venv --system-site-packages
source venv/bin/activate

# ── 4. Install Python packages ───────────────────────────────
echo "[4/5] Installing Python packages (dlib may take 30-90 min)..."

# Increase swap for dlib compilation (needs ~2GB RAM)
echo "  → Temporarily increasing swap to 2GB for dlib build..."
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=2048/' /etc/dphys-swapfile
sudo systemctl restart dphys-swapfile

pip install --upgrade pip
pip install numpy
pip install opencv-python-headless
pip install flask

echo "  → Building dlib (this will take a while — grab some chai ☕)..."
pip install dlib
pip install face-recognition

# Restore swap
echo "  → Restoring original swap size..."
sudo sed -i 's/CONF_SWAPSIZE=.*/CONF_SWAPSIZE=100/' /etc/dphys-swapfile
sudo systemctl restart dphys-swapfile

# ── 5. Configure for Pi Camera ───────────────────────────────
echo "[5/5] Configuring for Pi Camera..."
# Update config.py to use picamera2
sed -i 's/CAMERA_SOURCE = 0/CAMERA_SOURCE = "picamera2"/' config.py

echo ""
echo "╔══════════════════════════════════════════════════╗"
echo "║  ✅ Setup complete!                              ║"
echo "║                                                  ║"
echo "║  To run:                                         ║"
echo "║    source venv/bin/activate                      ║"
echo "║    python app.py                                 ║"
echo "║                                                  ║"
echo "║  Then open in browser:                           ║"
echo "║    http://<pi-ip-address>:5000                   ║"
echo "╚══════════════════════════════════════════════════╝"

# ── Optional: Create systemd service ─────────────────────────
read -p "Create a systemd service to auto-start on boot? (y/n) " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
    sudo tee /etc/systemd/system/face-attendance.service > /dev/null <<EOF
[Unit]
Description=Face Recognition Attendance System
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=$SCRIPT_DIR
ExecStart=$SCRIPT_DIR/venv/bin/python $SCRIPT_DIR/app.py
Restart=always
RestartSec=5
Environment=DISPLAY=:0

[Install]
WantedBy=multi-user.target
EOF

    sudo systemctl daemon-reload
    sudo systemctl enable face-attendance.service
    echo "✅ Service created! It will auto-start on boot."
    echo "   Manual control: sudo systemctl start|stop|status face-attendance"
fi
