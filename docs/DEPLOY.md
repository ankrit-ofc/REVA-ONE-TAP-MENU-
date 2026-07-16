# Deploying to your Vultr VPS — step by step

This is a beginner's runbook. Follow it top to bottom. Copy-paste the commands.
Lines starting with `#` are explanations — you don't type those.

**What you'll end up with:** your app live at `https://YOURDOMAIN`, with automatic
HTTPS, a real PostgreSQL database, product images that survive restarts, and live
WebSocket updates — all on one $6 Vultr box in Mumbai.

**Your setup:** Vultr 1 GB / 1 vCPU, Mumbai, Ubuntu 24.04, auto-backups on.

Notation: `you$` = type in your own computer (PowerShell). `server#` = type on the
VPS after you SSH in. Replace `YOURDOMAIN` with your real domain everywhere.

---

## Phase 0 — Point your domain at the server (do this first)

DNS changes take a few minutes to propagate, so start here.

1. In the Vultr dashboard, open your instance and copy its **public IP** (e.g. `139.84.x.x`).
2. In your domain registrar / DNS provider, add an **A record**:
   - **Host/Name:** `order` (gives you `order.YOURDOMAIN`) — or `@` for the root domain.
   - **Value:** your Vultr IP.
   - **TTL:** default.
3. **If your DNS is on Cloudflare:** set the record to **DNS only** (grey cloud, not
   orange) so Caddy can obtain its own certificate. You can switch on the proxy later.
4. Verify it resolves (wait a few minutes first):
   ```
   you$ nslookup order.YOURDOMAIN
   ```
   It should print your Vultr IP.

---

> ### Don't have the domain wired yet? Deploy on the IP first.
> You can **skip Phase 0** and come back later. Caddy serves your app over HTTPS using a
> **self-signed certificate** on the server's IP — the browser shows a one-time "not
> secure" warning you click through; everything else works normally.
> Wherever the steps below ask for your domain, use your **Vultr IP** instead:
> - Root `.env`: `DOMAIN=YOUR_VULTR_IP` (a bare IP makes Caddy auto-use a self-signed
>   cert — it does **not** attempt Let's Encrypt, so nothing fails).
> - `backend/.env`: set `BACKEND_BASE_URL`, `FRONTEND_BASE_URL`, and `ALLOWED_ORIGINS`
>   all to `https://YOUR_VULTR_IP`.
> - Then open `https://YOUR_VULTR_IP` (Phase 7) and accept the warning.
>
> **Wait until the real domain is set for:** printing/sharing table **QR codes** (they
> embed the base URL) and **phone/PWA** testing (phones distrust the self-signed cert).
> Desktop testing works fully right now.
>
> **To add the domain later:** do Phase 0 (add the A record), then edit `DOMAIN` and those
> three URLs to your real domain and re-run `./deploy.sh`. Caddy automatically swaps the
> self-signed cert for a real Let's Encrypt one — that's the only rework.

---

## Phase 1 — Log into the server

Vultr created a **root password** — find it on the instance page (Overview → "View
Console" credentials, or the password field). Then from PowerShell:

```
you$ ssh root@YOUR_VULTR_IP
```

- Type `yes` to accept the host key the first time.
- Paste the root password (right-click pastes in PowerShell; nothing shows as you type).

You're in when the prompt becomes `root@multitenant-qr-resturand:~#`.

---

## Phase 2 — Prepare the server (one time)

```
# Update the OS
server# apt update && apt -y upgrade

# Add 2 GB swap — IMPORTANT on a 1 GB box so builds & image processing don't crash
server# fallocate -l 2G /swapfile
server# chmod 600 /swapfile
server# mkswap /swapfile
server# swapon /swapfile
server# echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Install Docker (includes the compose plugin)
server# curl -fsSL https://get.docker.com | sh

# Firewall: allow SSH + web only
server# ufw allow OpenSSH
server# ufw allow 80/tcp
server# ufw allow 443/tcp
server# ufw --force enable

# Quick checks
server# docker --version
server# free -h        # should show 2.0Gi swap
```

---

## Phase 3 — Get your code onto the server

First make sure the latest code (including the deploy files) is pushed to GitHub from
your computer — see "Pushing updates" at the bottom. Then on the server:

```
server# cd /opt
```

**If your GitHub repo is public:**
```
server# git clone https://github.com/YOUR_USERNAME/YOUR_REPO.git app
```

**If it's private:** create a GitHub Personal Access Token (github.com → Settings →
Developer settings → Tokens → *Fine-grained* → read-only access to this repo), then:
```
server# git clone https://YOUR_TOKEN@github.com/YOUR_USERNAME/YOUR_REPO.git app
```

```
server# cd /opt/app
```

---

## Phase 4 — Configure secrets

Two env files: one for Caddy/HTTPS (root), one for the app + database (backend).

```
# 1) Root env for the domain + HTTPS email
server# cp .env.prod.example .env
server# nano .env
```
Set:
```
DOMAIN=order.YOURDOMAIN
ACME_EMAIL=you@example.com
```
Save in nano with `Ctrl+O`, `Enter`, then `Ctrl+X`.

```
# 2) Backend/app env
server# cp backend/.env.prod.example backend/.env

# Generate two different secrets and look at them:
server# openssl rand -hex 32      # copy this -> SECRET_KEY
server# openssl rand -hex 32      # copy this -> QR_SECRET
server# openssl rand -hex 24      # copy this -> use as the DB password

server# nano backend/.env
```
Fill in:
- `SECRET_KEY=` and `QR_SECRET=` → the two 64-char values above.
- `POSTGRES_PASSWORD=` → a strong password (can be the 48-char one).
- `APP_DB_PASSWORD=` → the DB password (the 48-char one). **Put the same value in
  `DATABASE_URL`** where it says `REPLACE_WITH_APP_DB_PASSWORD`.
- Replace every `order.yourdomain.com` with your real domain (`BACKEND_BASE_URL`,
  `FRONTEND_BASE_URL`, `ALLOWED_ORIGINS`, `KHALTI_WEBSITE_URL`, `SMTP_FROM`).
- Payments: leave the commented payment lines as-is for the sandbox demo.

Save and exit (`Ctrl+O`, `Enter`, `Ctrl+X`).

> Double-check: the password in `DATABASE_URL` and `APP_DB_PASSWORD` must be **identical**,
> or the app can't log into its own database.

---

## Phase 5 — Deploy

```
server# chmod +x deploy.sh
server# ./deploy.sh
```

This builds the frontend, builds the backend image, runs database migrations, and
starts everything. The first run takes a few minutes (downloading images, building).
Caddy automatically fetches an HTTPS certificate for your domain — this only works if
Phase 0's DNS is pointing at this server.

When it finishes you'll see a status table with `db`, `backend`, and `caddy` all `running`.

> If `./deploy.sh` says "bad interpreter" or "cannot execute": run
> `sed -i 's/\r$//' deploy.sh` then `bash deploy.sh`.

---

## Phase 6 — Create your first superadmin

The database is empty, so create the platform owner account (you log in with this to
onboard restaurants). **Pick your own email and a strong password:**

```
server# docker compose -f docker-compose.prod.yml exec backend python -c "
from app.db.session import SessionLocal
from app.models.user import User
from app.models.restaurant import Restaurant, RestaurantSettings
from app.core import security
from app.models.enums import Role
db = SessionLocal()
r = Restaurant(name='Platform', slug='platform', is_active=True)
db.add(r); db.flush()
db.add(RestaurantSettings(restaurant_id=r.id))
db.add(User(restaurant_id=r.id, email='YOU@EXAMPLE.COM',
            password_hash=security.hash_password('CHOOSE_A_STRONG_PASSWORD'),
            role=Role.SUPERADMIN))
db.commit(); print('Superadmin created.'); db.close()
"
```

---

## Phase 7 — Verify it's live

1. Open `https://order.YOURDOMAIN` in your browser — you should see the app with a
   valid padlock (real HTTPS).
2. Log in with the superadmin you just created → create a restaurant + an admin.
3. Log in as that admin → add a category, a product (test the image upload), a table.
4. Open the table's **Show QR**, scan it with your phone → the customer menu loads,
   place a test order, and confirm the kitchen/counter screens update live.

🎉 You're deployed.

---

## Day-2 operations

### Pushing updates (your computer → server)
```
# On your computer, after making changes:
you$ git add -A && git commit -m "..." && git push

# On the server:
server# cd /opt/app && ./deploy.sh
```

### View logs
```
server# cd /opt/app
server# docker compose -f docker-compose.prod.yml logs -f --tail=100           # all
server# docker compose -f docker-compose.prod.yml logs -f backend              # just backend
```

### Restart / stop
```
server# docker compose -f docker-compose.prod.yml restart
server# docker compose -f docker-compose.prod.yml down      # stop (keeps data volumes)
server# docker compose -f docker-compose.prod.yml up -d     # start again
```

### Database backups
Vultr's automatic backups snapshot the whole disk daily (you enabled this). For an
extra app-level backup you can also dump the database any time:
```
server# docker compose -f docker-compose.prod.yml exec db pg_dump -U postgres appdb > ~/backup-$(date +%F).sql
```
Copy it off the server occasionally (from your computer):
```
you$ scp root@YOUR_VULTR_IP:~/backup-*.sql .
```

---

## Troubleshooting

- **Browser says "not secure" / cert error:** Caddy couldn't get a certificate. Check
  DNS points to this server (`nslookup`), ports 80+443 are open (`ufw status`), and if
  on Cloudflare the record is **DNS only (grey)**. Watch `docker compose -f
  docker-compose.prod.yml logs caddy`.
- **App loads but API calls fail / CORS error:** make sure `ALLOWED_ORIGINS`,
  `BACKEND_BASE_URL`, `FRONTEND_BASE_URL` in `backend/.env` all equal `https://YOURDOMAIN`,
  then `./deploy.sh` again.
- **"password authentication failed" in backend logs:** `APP_DB_PASSWORD` and the
  password inside `DATABASE_URL` don't match. Fix `backend/.env`. (If the database
  volume was already created with a different password, you must reset it — ask before
  doing this, it deletes data: `docker compose -f docker-compose.prod.yml down -v`.)
- **Build killed / out of memory:** confirm swap is on (`free -h`). Re-run `./deploy.sh`.
- **A service keeps restarting:** read its logs (`logs <service>`); usually a typo in
  `backend/.env`.
