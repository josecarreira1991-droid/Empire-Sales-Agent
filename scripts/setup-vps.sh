#!/bin/bash
# ============================================
# Empire Sales Agent - VPS Setup Script
# Run this on a FRESH Ubuntu 24.04 Hostinger VPS
# Usage: sudo bash setup-vps.sh
# ============================================

set -euo pipefail

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log() { echo -e "${GREEN}[SETUP]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Check root
if [ "$EUID" -ne 0 ]; then
    err "Run this script as root: sudo bash setup-vps.sh"
fi

log "=========================================="
log "Empire Sales Agent - VPS Setup"
log "=========================================="

# ------------------------------------------
# 1. System Update
# ------------------------------------------
log "Updating system packages..."
apt update && apt upgrade -y
apt install -y git curl wget ufw fail2ban unzip software-properties-common \
    build-essential libpq-dev chromium-browser chromium-chromedriver

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
# 3. SSH Hardening
# ------------------------------------------
log "Hardening SSH..."
SSH_CONFIG="/etc/ssh/sshd_config"
cp "$SSH_CONFIG" "${SSH_CONFIG}.bak"

# Change SSH port to 2222
sed -i 's/^#\?Port .*/Port 2222/' "$SSH_CONFIG"
sed -i 's/^#\?PermitRootLogin .*/PermitRootLogin no/' "$SSH_CONFIG"
sed -i 's/^#\?PasswordAuthentication .*/PasswordAuthentication no/' "$SSH_CONFIG"
sed -i 's/^#\?PubkeyAuthentication .*/PubkeyAuthentication yes/' "$SSH_CONFIG"
sed -i 's/^#\?MaxAuthTries .*/MaxAuthTries 3/' "$SSH_CONFIG"

# Copy SSH keys to empire user
if [ -d /root/.ssh ]; then
    mkdir -p /home/empire/.ssh
    cp /root/.ssh/authorized_keys /home/empire/.ssh/ 2>/dev/null || true
    chown -R empire:empire /home/empire/.ssh
    chmod 700 /home/empire/.ssh
    chmod 600 /home/empire/.ssh/authorized_keys 2>/dev/null || true
fi

systemctl restart sshd
log "SSH hardened. New port: 2222"

# ------------------------------------------
# 4. Firewall (UFW)
# ------------------------------------------
log "Configuring firewall..."
ufw default deny incoming
ufw default allow outgoing
ufw allow 2222/tcp    # SSH
ufw allow 80/tcp      # HTTP (Caddy/Let's Encrypt)
ufw allow 443/tcp     # HTTPS (Twilio webhooks)
echo "y" | ufw enable
log "Firewall active. Open ports: 2222, 80, 443"

# ------------------------------------------
# 5. Fail2Ban
# ------------------------------------------
log "Configuring Fail2Ban..."
cat > /etc/fail2ban/jail.local << 'JAIL'
[sshd]
enabled = true
port = 2222
filter = sshd
logpath = /var/log/auth.log
maxretry = 3
bantime = 3600
findtime = 600
JAIL
systemctl enable fail2ban
systemctl restart fail2ban

# ------------------------------------------
# 6. Install Docker
# ------------------------------------------
log "Installing Docker..."
if ! command -v docker &>/dev/null; then
    curl -fsSL https://get.docker.com | sh
    usermod -aG docker empire
fi
systemctl enable docker
systemctl start docker

# ------------------------------------------
# 7. Install Node.js 22
# ------------------------------------------
log "Installing Node.js 22..."
if ! command -v node &>/dev/null || [[ $(node -v | cut -d. -f1 | tr -d v) -lt 22 ]]; then
    curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
    apt install -y nodejs
fi
log "Node.js version: $(node -v)"

# ------------------------------------------
# 8. Install Python 3.12
# ------------------------------------------
log "Installing Python 3.12..."
if ! command -v python3.12 &>/dev/null; then
    add-apt-repository -y ppa:deadsnakes/ppa
    apt update
    apt install -y python3.12 python3.12-venv python3.12-dev python3-pip
fi
log "Python version: $(python3.12 --version)"

# ------------------------------------------
# 9. Install PostgreSQL
# ------------------------------------------
log "Installing PostgreSQL..."
if ! command -v psql &>/dev/null; then
    apt install -y postgresql postgresql-contrib
fi
systemctl enable postgresql
systemctl start postgresql

# Create database and user
sudo -u postgres psql -c "CREATE USER empire WITH PASSWORD '${DB_PASSWORD:-changeme}';" 2>/dev/null || true
sudo -u postgres psql -c "CREATE DATABASE empire_leads OWNER empire;" 2>/dev/null || true
sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE empire_leads TO empire;" 2>/dev/null || true

# Secure PostgreSQL - localhost only
PG_HBA=$(find /etc/postgresql -name pg_hba.conf | head -1)
PG_CONF=$(find /etc/postgresql -name postgresql.conf | head -1)
if [ -n "$PG_CONF" ]; then
    sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" "$PG_CONF"
fi
systemctl restart postgresql
log "PostgreSQL configured (localhost only)"

# ------------------------------------------
# 10. Install Caddy (Reverse Proxy + Auto SSL)
# ------------------------------------------
log "Installing Caddy..."
if ! command -v caddy &>/dev/null; then
    apt install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
    apt update
    apt install -y caddy
fi

# Caddy config will be set up after domain is known
log "Caddy installed. Configure /etc/caddy/Caddyfile after setting up domain."

# ------------------------------------------
# 11. Install OpenClaw
# ------------------------------------------
log "Installing OpenClaw..."
su - empire -c 'npm install -g openclaw@latest' || true
log "OpenClaw installed"

# ------------------------------------------
# 12. Setup Python virtual environment
# ------------------------------------------
log "Setting up Python virtual environment and installing packages..."
su - empire -c '
    mkdir -p ~/empire-sales-agent
    cd ~/empire-sales-agent
    python3.12 -m venv venv
    source venv/bin/activate
    pip install --upgrade pip
    pip install beautifulsoup4 selenium requests psycopg2-binary pandas pdfplumber schedule python-dotenv lxml undetected-chromedriver geopandas
'

# ------------------------------------------
# 13. Create directory structure
# ------------------------------------------
log "Creating directory structure..."
su - empire -c '
    mkdir -p ~/.openclaw/workspace/skills
    mkdir -p ~/empire-sales-agent/data
    chmod 700 ~/.openclaw
'

# ------------------------------------------
# Done
# ------------------------------------------
log "=========================================="
log "VPS Setup Complete!"
log "=========================================="
log ""
log "NEXT STEPS:"
log "1. SSH into the VPS as 'empire' user on port 2222:"
log "   ssh -p 2222 empire@YOUR_VPS_IP"
log ""
log "2. Clone your repo:"
log "   cd ~ && git clone YOUR_REPO_URL empire-sales-agent"
log ""
log "3. Copy and edit .env:"
log "   cd empire-sales-agent && cp .env.example .env && nano .env"
log ""
log "4. Run database schema:"
log "   psql -U empire -d empire_leads -f database/schema.sql"
log ""
log "5. Install Python dependencies:"
log "   source venv/bin/activate && pip install -r scripts/scraper/requirements.txt"
log ""
log "6. Copy OpenClaw config:"
log "   cp openclaw/openclaw.json ~/.openclaw/"
log "   cp openclaw/.env ~/.openclaw/"
log "   cp -r openclaw/workspace/* ~/.openclaw/workspace/"
log ""
log "7. Configure Caddy (edit /etc/caddy/Caddyfile with your domain)"
log ""
log "8. Start OpenClaw:"
log "   openclaw start"
log ""
warn "IMPORTANT: Change DB_PASSWORD in .env before running!"
warn "IMPORTANT: SSH port is now 2222 (not 22)"
