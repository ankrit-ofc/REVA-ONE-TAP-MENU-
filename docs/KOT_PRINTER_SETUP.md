# KOT Print Service — install & operations runbook

How to install the **kot-printer** worker on a Windows device so kitchen tickets
print automatically on an 80mm thermal printer. Written runbook-style like
`DEPLOY.md`: follow top to bottom on the new device.

---

## How it works (30 seconds)

```
Customer orders (or waiter approves)          Windows device at the restaurant
        │                                              │
        ▼                                              │  polls every ~3s
backend enqueues a ticket row in          ◄────────────┤  POST {baseUrl}kot/get
kot_print_jobs (same DB transaction                    │
as the order — no order, no ticket)       ────────────►│  renders 80mm PDF,
        ▲                                              │  prints via Windows
        │  marks printed                               │  spooler (SumatraPDF)
        └─────────────────────────────────  ◄──────────┤  POST {baseUrl}kot/ack
```

- The worker is a small **Node.js app** (source lives in the separate
  `kot-printer/` project, sibling of this repo; its `README.md` documents the
  exact API contract).
- **Auth = the per-restaurant worker token** (Bearer). The token *is* the tenant
  scoping — one token per restaurant, one worker device per token.
- Tickets enqueue when the restaurant is in **worker** print mode with
  **Print KOT** enabled. With the **order-approval gate** on, tickets enqueue at
  waiter approval, not at order placement. Manual **reprints** from the counter
  enqueue regardless of the Print KOT toggle.
- The target **printer name rides on each ticket** and is resolved from the
  restaurant's settings *at fetch time* — you can change the printer name in the
  web app without touching the device.
- Reliability: a ticket is acked **only after it printed without error**;
  unprinted tickets are re-fetched on the next poll. Replayed acks are no-ops.

---

## 1. Prerequisites on the device

- Windows 10/11.
- **Node.js LTS** — https://nodejs.org (check: `node --version`).
- The thermal printer installed as a **normal Windows printer with a real
  driver**, and its exact name noted (Settings → Printers).
  - ⚠️ "Microsoft Print to PDF" **cannot print silently** (its PORTPROMPT: port
    needs a save dialog) — fine for a smoke test only if you repoint its port to
    a fixed file; never for production.
- Outbound HTTPS to the backend (production: `https://revatap.com`).

List printer names the worker can see (run inside the app folder later):

```powershell
node -e "require('./src/printer').listPrinters().then(p=>console.log(p.map(x=>x.name)))"
```

## 2. Get the app onto the device

Use the packaged zip (`kot-printer-install.zip` — source + fonts, no tokens) or
copy the `kot-printer/` folder **excluding** `node_modules/`, `logs/`, and
`config.json`. Then:

```powershell
# e.g. unzip to C:\reva\kot-printer
cd C:\reva\kot-printer
npm install
```

## 3. Configure the device

```powershell
copy config.example.json config.json
notepad config.json
```

Set exactly three values:

| Key | Value |
|---|---|
| `server.baseUrl` | `https://revatap.com/printworker/` (dev: `http://<pc-ip>:8000/printworker/`) |
| `server.token` | The restaurant's worker token — web app → **Admin → Devices** → *Kitchen ticket (KOT) printing* → copy token |
| `print.defaultPrinter` | Exact Windows printer name from step 1 |

Optional: `print.printerMap` routes by kitchen code (`{ "HOT": "Kitchen-1", "BAR": "Bar-1" }`),
`poll.intervalSeconds` (default 3), `print.copies`.

## 4. Configure the restaurant (web app, once)

As that restaurant's **admin** → **Devices** page:

1. KOT pipeline → **Worker** (browser mode bypasses the queue entirely).
2. **Windows printer name** → same name as `print.defaultPrinter` (this is what
   tickets carry; the device value is only a fallback).
3. Ensure **Print KOT** is enabled (Settings/Devices toggle) — without it,
   normal orders never enqueue (reprints still do).

## 5. Test before trusting it

```powershell
node scripts\test-print.js --print   # local print leg only — sample ticket should print
npm start                            # live: place a test order, watch it poll → print → ack
```

Logs: `logs\` in the app folder. A healthy loop logs fetch/print/ack lines;
`[]` responses mean nothing pending.

## 6. Run unattended (scheduled task at logon)

The repo ships `start-kot.vbs` (runs node hidden, output to
`logs\service.out.log`). **Edit the hardcoded path inside it first** —
`sh.CurrentDirectory = "..."` must point at the install folder. Then (admin
PowerShell):

```powershell
schtasks /Create /TN "KOT Printer" /TR "wscript.exe C:\reva\kot-printer\start-kot.vbs" /SC ONLOGON /RL HIGHEST /F
```

**Restart procedure** (stopping the task does NOT kill node):

```powershell
Stop-ScheduledTask -TaskName "KOT Printer"
Stop-Process -Name node -Force
Start-ScheduledTask -TaskName "KOT Printer"
```

---

## Operations & gotchas

- **One worker per restaurant token.** Two devices on the same token race for
  the queue (each ticket still prints exactly once — on whichever polls first).
  Different restaurant → its own token and its own device/config.
- **Token rotation** (Devices → *Regenerate token*, audited) invalidates the old
  token immediately → update `config.json` on the device and restart the worker.
  Rotate whenever a token may have leaked or a device is retired.
- **Changing printers**: rename in the web app (Devices) — tickets pick it up on
  the next fetch. The device's `defaultPrinter` matters only when a ticket
  carries no printer name.
- **Nothing prints?** Check in order:
  1. Worker running? (`logs\service.out.log`, Task Manager → node.exe)
  2. `kot_print_mode` = worker AND `print_kot_enabled` = true for the tenant?
  3. Approval gate on? Ticket only enqueues after the waiter **approves**.
  4. 401 in logs → token wrong/rotated.
  5. Prints nothing but acks fine → wrong printer name (check spelling against
     the list-printers one-liner) or a dialog-based pseudo-printer.
- **Dev testing without a backend**: `node scripts\mock-server.js` serves a fake
  API on `http://localhost:5000/api/`.

## Backend reference (for developers)

- Endpoints: `POST /printworker/kot/get`, `POST /printworker/kot/ack`
  (`backend/app/api/printworker.py`), token-authed, tenant-scoped by token.
- Queue table: `kot_print_jobs` (migration `0015`); `printed_at IS NULL` =
  pending. Enqueue logic: `backend/app/services/kot_print_service.py`, called
  from `order_service.place_or_append` / `approve_pending_items` /
  `request_kot_print`.
- Token rotation endpoint: `POST /admin/settings/kot-worker-token`.
