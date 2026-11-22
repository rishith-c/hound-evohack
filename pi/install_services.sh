#!/bin/sh
# install_services.sh — run ON THE PI. Installs cloudflared and two systemd services:
#   rover-web.service     the remote-control web app (port 8080), restarts on failure, starts at boot
#   rover-tunnel.service  a Cloudflare quick tunnel to it (public https://<random>.trycloudflare.com URL)
# The tunnel URL changes every time the tunnel service restarts; read it with:  sh ~/rover/tunnel_url.sh
set -e
U="$(whoami)"; H="$HOME"

if ! command -v cloudflared >/dev/null 2>&1; then
  arch=$(dpkg --print-architecture)
  curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-${arch}.deb" -o /tmp/cloudflared.deb
  sudo dpkg -i /tmp/cloudflared.deb >/dev/null
fi

sudo tee /etc/systemd/system/rover-web.service >/dev/null <<EOF
[Unit]
Description=Hound remote-control web app
After=network.target
[Service]
User=$U
WorkingDirectory=$H/rover
ExecStart=$H/rover/venv/bin/python $H/rover/web.py
Restart=always
RestartSec=2
[Install]
WantedBy=multi-user.target
EOF

sudo tee /etc/systemd/system/rover-tunnel.service >/dev/null <<EOF
[Unit]
Description=Cloudflare quick tunnel to the Hound web app
After=network-online.target rover-web.service
Wants=network-online.target
[Service]
User=$U
ExecStart=/usr/bin/cloudflared tunnel --no-autoupdate --url http://localhost:8080
Restart=always
RestartSec=5
[Install]
WantedBy=multi-user.target
EOF

cat > "$H/rover/tunnel_url.sh" <<'EOF'
#!/bin/sh
# prints the current public URL of the rover remote (with the access key)
url=$(journalctl -u rover-tunnel --no-pager -o cat 2>/dev/null | grep -o 'https://[a-z0-9-]*\.trycloudflare\.com' | tail -1)
key=$(cat "$HOME/rover/web.key" 2>/dev/null)
[ -n "$url" ] && echo "$url/?k=$key" || echo "tunnel not up yet"
EOF
chmod +x "$H/rover/tunnel_url.sh"

sudo systemctl daemon-reload
sudo systemctl enable --now rover-web.service rover-tunnel.service >/dev/null
sleep 8
systemctl is-active rover-web.service rover-tunnel.service | tr '\n' ' '; echo
sh "$H/rover/tunnel_url.sh"
