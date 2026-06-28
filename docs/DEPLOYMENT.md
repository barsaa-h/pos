# POS System — Deployment Guide

## Docker (Recommended)

```bash
# Build and start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down

# Update
docker compose down
docker compose build --no-cache
docker compose up -d
```

The app runs on `http://localhost:8765`. Data persists in Docker volumes.

## Bare Metal (Ubuntu)

```bash
# Install dependencies
sudo apt update && sudo apt install -y python3 python3-venv python3-pip sqlite3 nginx

# Clone and setup
sudo mkdir -p /opt/pos
sudo cp -r . /opt/pos/
sudo useradd -r -s /bin/false pos
cd /opt/pos
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install waitress

# Create data directory
sudo mkdir -p /opt/pos/data/logs /opt/pos/data/backups
sudo chown -R pos:pos /opt/pos
```

### Reverse Proxy (Nginx)

```bash
sudo cp deploy/nginx.conf /etc/nginx/sites-available/pos
sudo ln -s /etc/nginx/sites-available/pos /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
```

### Systemd Service

```bash
sudo cp ubuntu/pos.service /etc/systemd/system/pos.service
sudo systemctl daemon-reload
sudo systemctl enable --now pos
```

### Backup Cron

```bash
# Run backup every 6 hours
sudo cp deploy/backup.sh /usr/local/bin/pos-backup
echo "0 */6 * * * root /usr/local/bin/pos-backup" | sudo tee /etc/cron.d/pos-backup
```

## SSL/TLS

For internet-facing deployments, use Let's Encrypt:

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d pos.example.com
```

For LAN-only deployments, use a self-signed certificate:

```bash
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
    -keyout /etc/ssl/private/pos.key \
    -out /etc/ssl/certs/pos.crt
```

## First Run

1. Open `http://[server]:8765`
2. Click the lock icon to go to admin login
3. Enter a 4-digit PIN code (this becomes the admin password)
4. Configure store name, address, printer port, and eBarimt in Settings

## Troubleshooting

| Issue | Check |
|-------|-------|
| App won't start | `journalctl -u pos -n 50` |
| Database locked | Restart the service: `systemctl restart pos` |
| Printer not working | Verify port in Settings, check cable, try `/dev/usb/lp0` |
| eBarimt not sending | Check API URL, merchant TIN, branch ID in Settings |
| Slow queries | Run SQLite VACUUM from Settings page |
