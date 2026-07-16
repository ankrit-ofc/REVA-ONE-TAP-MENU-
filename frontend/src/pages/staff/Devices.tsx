/**
 * Printer devices page (COUNTER + ADMIN).
 *
 * Pairing is local to this browser (WebUSB grant) — so it must be done on the
 * counter computer that has the printers plugged in. The auto-print toggles +
 * bill-copy count are restaurant settings: ADMIN edits them here, COUNTER sees
 * them read-only.
 */
import { useEffect, useState } from 'react'
import { useAuth } from '@/features/auth/useAuth'
import { useGetPrintConfigQuery } from '@/features/counter/counterApi'
import {
  useGetSettingsQuery,
  useUpdateSettingsMutation,
  useRotateKotWorkerTokenMutation,
} from '@/features/admin/adminApi'
import {
  getSavedDevice,
  setSavedDevice,
  toSaved,
  resolveDevice,
  type PrinterRole,
} from '@/features/printing/printerDevices'
import { requestPrinter, sendBytes, describePrinterError } from '@/lib/escpos/webusbPrinter'
import { buildTestBytes } from '@/features/printing/receipts'
import styles from './Devices.module.css'

interface CardProps {
  role: PrinterRole
  title: string
  hint: string
}

function PrinterCard({ role, title, hint }: CardProps) {
  const [label, setLabel] = useState<string | null>(getSavedDevice(role)?.label ?? null)
  const [connected, setConnected] = useState<boolean | null>(null)
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ kind: 'ok' | 'err'; text: string } | null>(null)

  const refresh = async () => {
    const saved = getSavedDevice(role)
    setLabel(saved?.label ?? null)
    setConnected(saved ? (await resolveDevice(role)) !== null : null)
  }

  useEffect(() => {
    void refresh()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const pair = async () => {
    setMsg(null)
    setBusy(true)
    try {
      const device = await requestPrinter()
      setSavedDevice(role, toSaved(device, device.productName))
      // Immediately test so the operator sees which physical unit responded.
      await sendBytes(device, buildTestBytes(title))
      await refresh()
      setMsg({ kind: 'ok', text: 'Paired — a test slip printed. Confirm it was the right printer.' })
    } catch (e) {
      // User cancelling the chooser throws — treat quietly.
      const name = (e as { name?: string }).name
      if (name === 'NotFoundError' || name === 'AbortError') setMsg(null)
      else setMsg({ kind: 'err', text: describePrinterError(e) })
    } finally {
      setBusy(false)
    }
  }

  const test = async () => {
    setMsg(null)
    setBusy(true)
    try {
      const device = await resolveDevice(role)
      if (!device) {
        setMsg({ kind: 'err', text: 'Not paired on this computer. Click Pair first.' })
        return
      }
      await sendBytes(device, buildTestBytes(title))
      setMsg({ kind: 'ok', text: 'Test slip sent.' })
    } catch (e) {
      setMsg({ kind: 'err', text: describePrinterError(e) })
    } finally {
      setBusy(false)
    }
  }

  const unpair = () => {
    setSavedDevice(role, null)
    setLabel(null)
    setConnected(null)
    setMsg(null)
  }

  return (
    <div className={styles.card}>
      <div className={styles.cardHead}>
        <h2 className={styles.cardTitle}>{title}</h2>
        {label == null ? (
          <span className={`${styles.badge} ${styles.badgeMuted}`}>Not paired</span>
        ) : connected ? (
          <span className={`${styles.badge} ${styles.badgeOk}`}>Connected</span>
        ) : (
          <span className={`${styles.badge} ${styles.badgeWarn}`}>Paired · offline</span>
        )}
      </div>
      <p className={styles.hint}>{hint}</p>
      {label && <div className={styles.deviceLabel}>{label}</div>}

      <div className={styles.cardActions}>
        <button className={styles.btnPrimary} onClick={() => void pair()} disabled={busy}>
          {label ? 'Re-pair' : 'Pair'}
        </button>
        <button className={styles.btnSecondary} onClick={() => void test()} disabled={busy || !label}>
          Test print
        </button>
        {label && (
          <button className={styles.btnGhost} onClick={unpair} disabled={busy}>
            Unpair
          </button>
        )}
      </div>
      {msg && <p className={msg.kind === 'ok' ? styles.ok : styles.err}>{msg.text}</p>}
    </div>
  )
}

export default function Devices() {
  const { role } = useAuth()
  const isAdmin = role === 'ADMIN'
  const { data: config } = useGetPrintConfigQuery()
  // Settings (ADMIN-only endpoint) carry the worker token for the config.json.
  const { data: settings } = useGetSettingsQuery(undefined, { skip: !isAdmin })
  const [updateSettings, { isLoading: saving }] = useUpdateSettingsMutation()
  const [rotateToken, { isLoading: rotating }] = useRotateKotWorkerTokenMutation()

  const [kot, setKot] = useState(false)
  const [bill, setBill] = useState(false)
  const [copies, setCopies] = useState(2)
  const [mode, setMode] = useState<'browser' | 'worker'>('browser')
  const [printerName, setPrinterName] = useState('')
  const [saved, setSaved] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const [tokenMsg, setTokenMsg] = useState<string | null>(null)

  useEffect(() => {
    if (config) {
      setKot(config.print_kot_enabled)
      setBill(config.print_bill_enabled)
      setCopies(config.bill_copies)
      setMode(config.kot_print_mode)
      setPrinterName(config.kot_printer_name ?? '')
    }
  }, [config])

  const save = async () => {
    setErr(null)
    setSaved(false)
    try {
      await updateSettings({
        print_kot_enabled: kot,
        print_bill_enabled: bill,
        bill_copies: copies,
        kot_print_mode: mode,
        kot_printer_name: printerName.trim(),
      }).unwrap()
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (e) {
      const d = (e as { data?: { detail?: string } }).data?.detail
      setErr(d ?? 'Save failed')
    }
  }

  const workerToken = settings?.kot_worker_token ?? null

  const copyToken = async () => {
    if (!workerToken) return
    try {
      await navigator.clipboard.writeText(workerToken)
      setTokenMsg('Token copied.')
    } catch {
      setTokenMsg('Copy failed — select and copy it manually.')
    }
    setTimeout(() => setTokenMsg(null), 3000)
  }

  const regenerateToken = async () => {
    if (
      workerToken &&
      !window.confirm(
        'Generate a new token? The print service stops working until its config.json is updated with the new token.',
      )
    ) {
      return
    }
    setTokenMsg(null)
    try {
      await rotateToken().unwrap()
      setTokenMsg('New token generated — update config.json on the print-service computer.')
    } catch {
      setTokenMsg('Could not generate a token.')
    }
  }

  return (
    <div className={styles.root}>
      <h1 className={styles.title}>Printers</h1>

      <div className={styles.banner}>
        Pair printers <strong>on the counter computer</strong> (Chrome/Edge, over https). On Windows a
        USB printer must use the <strong>WinUSB driver</strong> — if pairing says it can’t be claimed,
        install WinUSB for it with <strong>Zadig</strong>, then re-pair. Pairing is per-computer.
      </div>

      <div className={styles.cards}>
        <PrinterCard
          role="kitchen"
          title="Kitchen Printer"
          hint="Prints a kitchen ticket (KOT) the moment a customer orders."
        />
        <PrinterCard
          role="bill"
          title="Bill Printer"
          hint="Prints the itemized bill after payment, and from the Print button."
        />
      </div>

      <div className={styles.settings}>
        <h2 className={styles.cardTitle}>Kitchen ticket (KOT) printing</h2>
        {isAdmin ? (
          <>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Print pipeline</span>
              <select
                className={styles.input}
                value={mode}
                onChange={(e) => setMode(e.target.value === 'worker' ? 'worker' : 'browser')}
              >
                <option value="browser">This browser (WebUSB — pair above)</option>
                <option value="worker">Windows print service (kot-printer)</option>
              </select>
            </label>
            {mode === 'worker' && (
              <>
                <label className={styles.field}>
                  <span className={styles.fieldLabel}>Windows printer name</span>
                  <input
                    className={styles.input}
                    type="text"
                    maxLength={120}
                    placeholder="e.g. POS-80"
                    value={printerName}
                    onChange={(e) => setPrinterName(e.target.value)}
                  />
                </label>
                <p className={styles.hint}>
                  Exact name of the printer installed on the computer running the print
                  service (as shown in Windows “Printers &amp; scanners”). Leave empty to use
                  the service&apos;s default printer.
                </p>
                <div className={styles.field}>
                  <span className={styles.fieldLabel}>Print service token</span>
                  {workerToken ? (
                    <div className={styles.deviceLabel}>{workerToken}</div>
                  ) : (
                    <p className={styles.hint}>No token yet — generate one.</p>
                  )}
                </div>
                <div className={styles.cardActions}>
                  {workerToken && (
                    <button className={styles.btnSecondary} onClick={() => void copyToken()}>
                      Copy token
                    </button>
                  )}
                  <button
                    className={styles.btnGhost}
                    onClick={() => void regenerateToken()}
                    disabled={rotating}
                  >
                    {rotating ? 'Generating…' : workerToken ? 'Regenerate token' : 'Generate token'}
                  </button>
                </div>
                {tokenMsg && <p className={styles.ok}>{tokenMsg}</p>}
                <p className={styles.hint}>
                  In the print service&apos;s <strong>config.json</strong> set{' '}
                  <strong>server.baseUrl</strong> to this backend&apos;s URL +{' '}
                  <strong>/printworker/</strong> and <strong>server.token</strong> to the token
                  above. Tickets queue on the server and print even if no browser is open.
                </p>
              </>
            )}
            {err && <p className={styles.err}>{err}</p>}
            {saved && <p className={styles.ok}>Saved ✓</p>}
            <button className={styles.btnPrimary} onClick={() => void save()} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </>
        ) : (
          <ul className={styles.readonlyList}>
            <li>
              Pipeline:{' '}
              <strong>{mode === 'worker' ? 'Windows print service' : 'This browser (WebUSB)'}</strong>
            </li>
            {mode === 'worker' && (
              <li>
                Printer: <strong>{printerName || 'service default'}</strong>
              </li>
            )}
          </ul>
        )}
      </div>

      <div className={styles.settings}>
        <h2 className={styles.cardTitle}>Auto-print</h2>
        {isAdmin ? (
          <>
            <label className={styles.toggle}>
              <span>Print kitchen ticket on new order</span>
              <input type="checkbox" checked={kot} onChange={(e) => setKot(e.target.checked)} />
            </label>
            <label className={styles.toggle}>
              <span>Print bill automatically after payment</span>
              <input type="checkbox" checked={bill} onChange={(e) => setBill(e.target.checked)} />
            </label>
            <label className={styles.field}>
              <span className={styles.fieldLabel}>Bill copies (1–3)</span>
              <input
                className={styles.input}
                type="number"
                min={1}
                max={3}
                value={copies}
                onChange={(e) => setCopies(Math.min(3, Math.max(1, Number(e.target.value) || 1)))}
              />
            </label>
            {err && <p className={styles.err}>{err}</p>}
            {saved && <p className={styles.ok}>Saved ✓</p>}
            <button className={styles.btnPrimary} onClick={() => void save()} disabled={saving}>
              {saving ? 'Saving…' : 'Save'}
            </button>
          </>
        ) : (
          <ul className={styles.readonlyList}>
            <li>Kitchen ticket on new order: <strong>{kot ? 'On' : 'Off'}</strong></li>
            <li>Bill after payment: <strong>{bill ? 'On' : 'Off'}</strong></li>
            <li>Bill copies: <strong>{copies}</strong></li>
            <li className={styles.hint}>These are set by an admin.</li>
          </ul>
        )}
      </div>
    </div>
  )
}
