# Deployment Guide — VPS Server

Deploy `newsbrief` on a cheap VPS (DigitalOcean / Hetzner / Linode / AWS Lightsail etc.) for always-on, unattended operation.

> **Best for:** daily unattended digests, stable uptime, no laptop dependency.

---

## Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| OS | Ubuntu 22.04 / Debian 12 / any Docker-capable Linux | Ubuntu 22.04 LTS |
| CPU | 1 vCPU | 1-2 vCPU |
| RAM | 512 MB | 1 GB |
| Disk | 5 GB | 10 GB |
| Bandwidth | 1 GB/mo | 10 GB/mo |
| Public IP | Required | IPv4 |

**Cost:** ~$4-6/month (Hetzner CX11, DigitalOcean basic droplet, Vultr cloud compute).

Don't need: domain, SSL, reverse proxy (unless exposing webhook publicly).

---

## Architecture decisions

`newsbrief` on VPS is designed to be **inward-facing**:

- Container binds to `127.0.0.1` only (not exposed to internet)
- Telegram API is the only communication channel (outbound)
- No public endpoints needed
- SSH-only access for admin

If you need bot's webhook mode later, add Caddy/Nginx reverse proxy with TLS.

---

## Prerequisites

Same as [local deployment](deploy-local.md):

1. Telegram bot token (from @BotFather)
2. LLM API key (Groq free recommended)
3. SSH access to the VPS with sudo rights

---

## Step-by-step deployment

### Step 1 — Prepare the VPS

SSH in:
```bash
ssh root@your-server-ip
# or: ssh user@your-server-ip
```

Update and install Docker:
```bash
apt update && apt upgrade -y
apt install -y git curl ca-certificates

# Install Docker (official script)
curl -fsSL https://get.docker.com | sh

# Verify
docker --version
docker compose version
```

Create non-root user (if you're on `root`):
```bash
adduser newsbrief
usermod -aG docker newsbrief
usermod -aG sudo newsbrief      # optional
su - newsbrief
```

### Step 2 — Firewall (recommended)

```bash
# On Ubuntu
sudo ufw default deny incoming
sudo ufw default allow outgoing
sudo ufw allow 22/tcp            # SSH
sudo ufw enable
```

No other ports need to be open — `newsbrief` only makes outbound calls.

### Step 3 — Clone

```bash
cd ~
git clone https://github.com/newsbrief/newsbrief
cd newsbrief
```

### Step 4 — Run setup wizard

```bash
docker compose run --rm newsbrief setup
```

Same 5 questions as local. Since you're on a remote shell, for chat_id auto-detection:
1. Open your bot in Telegram from any device
2. Send `/start` or any message
3. Wizard detects the chat_id within 60 sec

### Step 5 — Start as daemon

```bash
docker compose up -d
```

Verify:
```bash
docker compose ps
docker compose logs -f newsbrief
```

### Step 6 — Enable auto-start on reboot

Docker Compose restart policy handles this automatically (`restart: unless-stopped` in docker-compose.yml). After VPS reboot, `newsbrief` comes back up.

If you want extra safety, use systemd:

```bash
sudo tee /etc/systemd/system/newsbrief.service <<EOF
[Unit]
Description=newsbrief digest daemon
Requires=docker.service
After=docker.service network-online.target

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/newsbrief/newsbrief
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
User=newsbrief

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable newsbrief
sudo systemctl start newsbrief
sudo systemctl status newsbrief
```

### Step 7 — Verify

```bash
docker compose exec newsbrief newsbrief doctor
```

Send test digest:
```bash
docker compose exec newsbrief newsbrief run
```

---

## Security hardening

### SSH

```bash
# /etc/ssh/sshd_config
PermitRootLogin no
PasswordAuthentication no
PubkeyAuthentication yes
```

```bash
sudo systemctl restart ssh
```

### Automatic security updates

```bash
sudo apt install unattended-upgrades
sudo dpkg-reconfigure -plow unattended-upgrades
```

### Fail2ban (SSH bruteforce protection)

```bash
sudo apt install fail2ban
sudo systemctl enable fail2ban
```

### File permissions

```bash
chmod 600 ~/newsbrief/.env
chmod 600 ~/newsbrief/config.yaml
```

### Docker daemon logging

Limit log sizes (`/etc/docker/daemon.json`):

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

```bash
sudo systemctl restart docker
docker compose up -d
```

---

## Automated backups

### Daily PostgreSQL-style dump (of SQLite)

```bash
mkdir -p ~/newsbrief-backups

# Create backup script
cat > ~/newsbrief-backups/backup.sh <<'EOF'
#!/bin/bash
set -e
cd /home/newsbrief/newsbrief
docker compose exec -T newsbrief newsbrief backup --output /app/data/backup-$(date +%Y%m%d).tar.gz 2>/dev/null || {
  # Fallback: manual copy
  DATE=$(date +%Y%m%d_%H%M%S)
  tar -czf /home/newsbrief/newsbrief-backups/nb-$DATE.tar.gz \
    -C /home/newsbrief/newsbrief \
    config.yaml data/
}
# Keep 7 days
find /home/newsbrief/newsbrief-backups -name 'nb-*.tar.gz' -mtime +7 -delete
EOF

chmod +x ~/newsbrief-backups/backup.sh

# Cron: daily 3 AM
(crontab -l 2>/dev/null; echo "0 3 * * * /home/newsbrief/newsbrief-backups/backup.sh >> /home/newsbrief/newsbrief-backups/backup.log 2>&1") | crontab -
```

### Off-site backup (optional)

Add to script:
```bash
# Copy to S3 / rclone / scp to another server
rclone copy /home/newsbrief/newsbrief-backups/nb-$DATE.tar.gz mybackups:newsbrief/
```

---

## Monitoring

### Simple uptime check

Use [UptimeRobot](https://uptimerobot.com) (free tier):

1. The container doesn't expose a public port, so monitor indirectly:
2. Set up a cron on VPS to ping UptimeRobot if container is healthy:

```bash
cat > ~/newsbrief-heartbeat.sh <<'EOF'
#!/bin/bash
cd /home/newsbrief/newsbrief
if docker compose ps --quiet newsbrief | xargs -I {} docker inspect -f '{{.State.Running}}' {} | grep -q true; then
  curl -fsSL https://uptimerobot.com/your-heartbeat-url >/dev/null
fi
EOF
chmod +x ~/newsbrief-heartbeat.sh

# Every 5 minutes
(crontab -l; echo "*/5 * * * * /home/newsbrief/newsbrief-heartbeat.sh") | crontab -
```

### Telegram alerts on daemon failure

If digest doesn't arrive at scheduled time, `newsbrief doctor` will detect. Add cron:

```bash
cat > ~/nb-healthcheck.sh <<'EOF'
#!/bin/bash
cd /home/newsbrief/newsbrief
OUTPUT=$(docker compose exec -T newsbrief newsbrief doctor 2>&1)
if echo "$OUTPUT" | grep -q "Errors: [1-9]"; then
  curl -s -X POST \
    "https://api.telegram.org/bot${TELEGRAM_TOKEN}/sendMessage" \
    -d "chat_id=${CHAT_ID}" \
    -d "text=⚠️ newsbrief problems detected: $OUTPUT"
fi
EOF
chmod +x ~/nb-healthcheck.sh

# Check every hour
(crontab -l; echo "0 * * * * /home/newsbrief/nb-healthcheck.sh") | crontab -
```

---

## Resource monitoring

```bash
docker stats newsbrief --no-stream
```

Expected (Groq LLM):
- Idle: ~50-80 MB RAM
- During pipeline (once per day): ~150-250 MB RAM, ~30 seconds CPU

If RAM consistently hits 512 MB — increase `mem_limit` in docker-compose.yml.

---

## Scaling / advanced

### Multiple users on one VPS

Currently single-user. For multi-user, run separate instances:

```bash
cd ~/newsbrief
cp -r . ../newsbrief-alice
cp -r . ../newsbrief-bob

cd ../newsbrief-alice
# Edit docker-compose.yml: change container_name: alice_newsbrief
docker compose up -d
```

### PostgreSQL instead of SQLite

Edit `.env`:
```
DATABASE_URL=postgresql://user:pass@host:5432/newsbrief
```

Install psycopg2:
```yaml
# docker-compose.yml, newsbrief service:
environment:
  - DATABASE_URL=${DATABASE_URL}
```

Run: `newsbrief setup` will use PostgreSQL if DATABASE_URL is set.

### HTTPS webhook (advanced)

If you want to switch Telegram bot from polling to webhook (scales better, lower latency):

1. Get a domain pointing to your VPS (e.g. `bot.example.com`)
2. Install Caddy:
   ```bash
   sudo apt install -y debian-keyring debian-archive-keyring
   curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy.gpg
   echo "deb [signed-by=/usr/share/keyrings/caddy.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
   sudo apt update && sudo apt install caddy
   ```
3. Caddyfile:
   ```
   bot.example.com {
     reverse_proxy 127.0.0.1:8080
   }
   ```
4. Register webhook:
   ```bash
   curl -F "url=https://bot.example.com/telegram/callback" \
     "https://api.telegram.org/bot<TOKEN>/setWebhook"
   ```

---

## Troubleshooting

### Container restarts constantly

Check logs:
```bash
docker compose logs --tail 50 newsbrief
```

Common causes: invalid config, bad API key, OOM (increase `mem_limit`).

### Digest not arriving at scheduled time

```bash
docker compose exec newsbrief newsbrief doctor
docker compose exec newsbrief newsbrief logs --pipeline --tail 100
```

Check:
- Is container running? `docker compose ps`
- Is scheduler active? Look for `[scheduler] started` in logs
- Is LLM reachable? `newsbrief llm test`
- Is Telegram token valid? `newsbrief doctor`

### Time zone is wrong

VPS default is often UTC. Override:
```bash
sudo timedatectl set-timezone Europe/Moscow
# Restart container
docker compose restart newsbrief
```

Or in config.yaml:
```yaml
schedule:
  send_at: "09:00"
  timezone: "Europe/Moscow"
```

### Out of disk

```bash
df -h
docker system prune -af            # clean old images/containers
rm -rf ~/newsbrief-backups/nb-*    # delete old backups
```

### SSH locked out after fail2ban / ufw

Use VPS provider's web console (Hetzner, DO, Vultr all have one) to login and fix firewall.

---

## Upgrading

```bash
cd ~/newsbrief
git pull
docker compose build
docker compose down
docker compose up -d
```

Config and data survive.

---

## Complete uninstall

```bash
cd ~/newsbrief
docker compose down -v
cd ..
rm -rf newsbrief/

# Remove systemd service if used
sudo systemctl stop newsbrief
sudo systemctl disable newsbrief
sudo rm /etc/systemd/system/newsbrief.service

# Revoke tokens
# Telegram: @BotFather → /revoke
# Groq: console.groq.com → delete key
```

---

## Cost breakdown (monthly)

| Item | Cost |
|------|------|
| Hetzner CX11 VPS (1 vCPU, 2 GB) | $4.50 |
| DigitalOcean basic droplet | $6.00 |
| Vultr cloud compute | $5.00 |
| Groq LLM (free tier) | $0.00 |
| Telegram API | $0.00 |
| **Total** | **$4-6/month** |

Paid LLMs (optional):
- OpenAI GPT-4o-mini: ~$0.01-0.05/day = $0.30-1.50/month
- Claude Haiku: ~$0.02-0.10/day = $0.60-3.00/month
- DeepSeek: ~$0.005-0.02/day = $0.15-0.60/month

---

## Next steps

- [Bot UI](bot-ui.md) — settings via Telegram keyboard
- [Source Discovery](discovery.md) — how to find more sources
- [Configuration reference](configuration.md) — advanced YAML options
- [Custom prompts](custom-prompts.md) — override AI behavior
