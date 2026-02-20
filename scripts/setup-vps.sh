#!/bin/bash
# ============================================
# Empire Sales Agent - VPS Setup Script
# Run this on a FRESH Ubuntu 24.04 Hostinger VPS
# Usage: bash setup-vps.sh
# ============================================

set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

if [ "$EUID" -ne 0 ]; then
    err "Run this script as root: bash setup-vps.sh"
fi

log "=========================================="
log "Empire Sales Agent - VPS Setup"
log "=========================================="

# ------------------------------------------
# 1. System Update
# ------------------------------------------
log "Updating system packages..."
apt update && DEBIAN_FRONTEND=noninteractive apt upgrade -y
apt install -y git curl wget unzip software-properties-common \
    build-essential libpq-dev

# Install Chrome separately (package name varies)
apt install -y chromium-browser 2>/dev/null || apt install -y chromium 2>/dev/null || true
apt install -y chromium-chromedriver 2>/dev/null || true

# ------------------------------------------
# 2. Create dedicated user
# ------------------------------------------
log "Creating 'empire' user..."
if ! id "empire" &>/dev/null; then
    adduser --disabled-password --gecos "" empire
    usermod -aG sudo empire
    echo "empire ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/empire
fi

# ------------------------------------------
# 3. Install Docker
# ------------------------------------------
log "Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker empire
fi
systemctl enable docker
systemctl start docker
log "Docker installed: $(docker --version)"

# ------------------------------------------
# 4. Install Node.js 22
# ------------------------------------------
log "Installing Node.js 22..."
if ! command -v node &>/dev/null || [[ $(node -v | cut -d. -f1 | tr -d v) -lt 22 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt install -y nodejs
fi
log "Node.js version: $(node -v)"

# ------------------------------------------
# 5. Install Python 3.12
# ------------------------------------------
log "Installing Python 3.12..."
if ! command -v python3.12 &>/dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
    apt update
    apt install -y python3.12 python3.12-venv python3.12-dev python3-pip 2>/dev/null || \
    apt install -y python3 python3-venv python3-dev python3-pip
fi
log "Python version: $(python3.12 --version 2>/dev/null || python3 --version)"

# ------------------------------------------
# 6. Install PostgreSQL
# ------------------------------------------
log "Installing PostgreSQL..."
if ! command -v psql &>/dev/null; then
    apt install -y postgresql postgresql-contrib
fi
systemctl enable postgresql
systemctl start postgresql

sudo -u postgres psql -c "CREATE USER empire WITH PASSWORD 'changeme';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE empire_leads OWNER empire;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE empire_leads TO empire;" 2>/dev/null || true
sudo -u postgres psql -c "ALTER USER empire CREATEDB;" 2>/dev/null || true

PG_CONF=$(find /etc/postgresql -name postgresql.conf 2>/dev/null | head -1)
if [ -n "$PG_CONF" ]; then
    sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
fi
systemctl restart postgresql
log "PostgreSQL configured"

# ------------------------------------------
# 7. Install Caddy
# ------------------------------------------
log "Installing Caddy..."
if ! command -v caddy &>/dev/null; then
    apt install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg 2>/dev/null
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt update
    apt install -y caddy
fi
log "Caddy installed"

# ------------------------------------------
# 8. Install OpenClaw
# ------------------------------------------
log "Installing OpenClaw..."
su - empire -c 'npm install -g openclaw@latest 2>/dev/null' || true
log "OpenClaw installed"

# ------------------------------------------
# 9. Setup Python venv + install packages
# ------------------------------------------
log "Setting up Python environment and installing BeautifulSoup + deps..."
su - empire -c '
    mkdir -p ~/empire-sales-agent
    cd ~/empire-sales-agent
    python3.12 -m venv venv 2>/dev/null || python3 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install beautifulsoup4 selenium requests psycopg2-binary pandas pdfplumber schedule python-dotenv lxml undetected-chromedriver
'
log "Python packages installed (BeautifulSoup, Selenium, etc.)"

# ------------------------------------------
# 10. Create directories
# ------------------------------------------
log "Creating directory structure..."
su - empire -c '
    mkdir -p ~/.openclaw/workspace/skills
    mkdir -p ~/empire-sales-agent/data/pdfs
    mkdir -p ~/empire-sales-agent/data/images
    mkdir -p ~/backups
    chmod 700 ~/.openclaw
'

# ------------------------------------------
# 11. Clone repo and setup
# ------------------------------------------
log "Cloning Empire Sales Agent repo..."
if [ ! -d /root/Empire-Sales-Agent ]; then
    git clone https://github.com/josecarreira1991-droid/Empire-Sales-Agent.git /root/Empire-Sales-Agent
fi

# Copy to empire user
cp -r /root/Empire-Sales-Agent/* /home/empire/empire-sales-agent/ 2>/dev/null || true
chown -R empire:empire /home/empire/empire-sales-agent

# Run database schema
log "Setting up database schema..."
sudo -u empire psql -d empire_leads -f /home/empire/empire-sales-agent/database/schema.sql 2>/dev/null || \
sudo -u postgres psql -d empire_leads -f /root/Empire-Sales-Agent/database/schema.sql 2>/dev/null || true

# Copy OpenClaw config
log "Copying OpenClaw configuration..."
su - empire -c '
    cp ~/empire-sales-agent/openclaw/openclaw.json.example ~/.openclaw/openclaw.json 2>/dev/null || true
    cp -r ~/empire-sales-agent/openclaw/workspace/* ~/.openclaw/workspace/ 2>/dev/null || true
'

# ------------------------------------------
# Done!
# ------------------------------------------
log "=========================================="
log "VPS Setup Complete!"
log "=========================================="
log ""
log "INSTALLED:"
log "  - Docker:     $(docker --version 2>/dev/null | head -c 40)"
log "  - Node.js:    $(node -v 2>/dev/null)"
log "  - Python:     $(python3.12 --version 2>/dev/null || python3 --version 2>/dev/null)"
log "  - PostgreSQL: $(psql --version 2>/dev/null | head -c 30)"
log "  - Caddy:      $(caddy version 2>/dev/null | head -c 20)"
log "  - OpenClaw:   installed"
log "  - BeautifulSoup + Selenium: installed"
log ""
log "DATABASE: empire_leads (user: empire, pass: changeme)"
log ""
log "NEXT STEPS:"
log "  1. Edit /home/empire/empire-sales-agent/.env with your API keys"
log "  2. Create Twilio + ElevenLabs + DeepSeek accounts"
log "  3. Start OpenClaw: su - empire -c 'openclaw start'"
log ""
warn "IMPORTANT: Change DB password and run SSH hardening later!"
