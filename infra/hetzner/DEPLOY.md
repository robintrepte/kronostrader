# Hetzner CCX deploy notes
#
# 1. Provision an Ubuntu CCX instance (dedicated vCPU recommended for Kronos CPU inference).
# 2. Install Docker + Compose plugin:
#      sudo apt update && sudo apt install -y docker.io docker-compose-v2 git
#      sudo usermod -aG docker $USER   # re-login
# 3. Clone this repo with submodules:
#      git clone --recurse-submodules https://github.com/robintrepte/kronostrader.git
#      cd kronostrader
# 4. Create production env:
#      cp .env.example .env
#      # set ALPACA keys, POSTGRES_PASSWORD, PUBLIC_API_URL, PUBLIC_WS_URL, MOCK_MARKET_DATA=false
#      # KEEP ALPACA_PAPER=true and ALPACA_LIVE=false until you intentionally go live
# 5. Edit infra/hetzner/nginx.conf — replace YOUR_DOMAIN everywhere.
# 6. Bootstrap TLS (first time, temporarily comment the SSL server block / use certbot standalone), e.g.:
#      sudo apt install -y certbot
#      sudo certbot certonly --webroot -w infra/hetzner/certbot-www -d YOUR_DOMAIN
#      # or mount host /etc/letsencrypt into ./infra/hetzner/certs
# 7. Start stack:
#      docker compose -f infra/docker-compose.prod.yml --env-file .env up -d --build
# 8. Verify:
#      curl https://YOUR_DOMAIN/health
#      open https://YOUR_DOMAIN
#
# Security:
# - Inference (:8000) stays on the Docker network only — nginx does not proxy it.
# - Never commit .env. Rotate Alpaca keys if leaked.
# - Live trading requires ALPACA_LIVE=true AND ALPACA_PAPER=false (both required by trader).
