/**
 * Headless auto-print controller. Mounted once in StaffLayout for COUNTER/ADMIN.
 *
 * Listens on the existing staff WebSocket and prints via WebUSB only when the
 * matching printer is paired *in this browser* and the feature is enabled — so
 * it safely no-ops on any machine without printers (e.g. an admin's laptop).
 *
 *   order.created  → kitchen printer  (KOT, from the event payload)
 *   invoice.paid   → bill printer     (itemized bill, fetched, ×copies)
 */
import { useEffect, useRef } from 'react'
import { useStaffRealtime } from '@/features/realtime/useRealtime'
import { useGetMeQuery } from '@/features/auth/authApi'
import { useGetPrintConfigQuery, useLazyGetReceiptQuery } from '@/features/counter/counterApi'
import { resolveDevice } from '@/features/printing/printerDevices'
import { buildKotBytes, buildBillBytes, type KotItem } from '@/features/printing/receipts'
import { sendBytes } from '@/lib/escpos/webusbPrinter'
import type { PrintConfig } from '@/lib/schemas/admin'
import type { RealtimeEvent } from '@/types'

function copyLabels(copies: number): string[] {
  if (copies <= 1) return ['']
  return Array.from({ length: copies }, (_, i) => (i === 0 ? 'Merchant Copy' : 'Customer Copy'))
}

function parseKotItems(raw: unknown): KotItem[] {
  if (!Array.isArray(raw)) return []
  return raw.map((r) => {
    const o = (r ?? {}) as Record<string, unknown>
    return {
      product_name: typeof o.product_name === 'string' ? o.product_name : '',
      variant_name: typeof o.variant_name === 'string' ? o.variant_name : null,
      quantity: typeof o.quantity === 'number' ? o.quantity : 1,
      special_instructions:
        typeof o.special_instructions === 'string' ? o.special_instructions : null,
      addons: Array.isArray(o.addons) ? o.addons.filter((a): a is string => typeof a === 'string') : [],
      line_total: typeof o.line_total === 'string' || typeof o.line_total === 'number' ? o.line_total : null,
    }
  })
}

/** Read a string money field off the event, or undefined. */
function evStr(event: RealtimeEvent, key: string): string | undefined {
  return typeof event[key] === 'string' ? (event[key] as string) : undefined
}

export default function PrintController() {
  const { data: me } = useGetMeQuery()
  const { data: config } = useGetPrintConfigQuery()
  const [fetchReceipt] = useLazyGetReceiptQuery()

  const configRef = useRef<PrintConfig | undefined>(config)
  configRef.current = config
  const restaurantNameRef = useRef<string>('')
  restaurantNameRef.current = me?.restaurant_name ?? ''

  // De-dup guards: invoices print once; KOTs use a short-lived signature window.
  const printedInvoices = useRef<Set<string>>(new Set())
  const recentKot = useRef<Map<string, number>>(new Map())
  // Manual KOT reprints (kot.print) carry a unique job_id; print each once.
  const printedKotJobs = useRef<Set<string>>(new Set())

  useEffect(() => {
    const map = recentKot.current
    const t = setInterval(() => {
      const now = Date.now()
      for (const [k, ts] of map) if (now - ts > 10_000) map.delete(k)
    }, 10_000)
    return () => clearInterval(t)
  }, [])

  useStaffRealtime((event: RealtimeEvent) => {
    // Manual KOT reprint relayed from a waiter/counter. Explicit action → print
    // regardless of the auto-print toggle; only needs a paired kitchen printer.
    // In worker mode the kot-printer Windows service owns all KOT printing, so
    // the browser stays out of it (the backend queues instead of broadcasting).
    if (configRef.current?.kot_print_mode === 'worker' && (event.type === 'kot.print' || event.type === 'order.created')) {
      return
    }
    if (event.type === 'kot.print') {
      const jobId = typeof event['job_id'] === 'string' ? event['job_id'] : ''
      if (!jobId || printedKotJobs.current.has(jobId)) return
      printedKotJobs.current.add(jobId)
      const items = parseKotItems(event['items'])
      if (items.length === 0) return
      const orderNumber = typeof event['order_number'] === 'number' ? event['order_number'] : 0
      void (async () => {
        const device = await resolveDevice('kitchen')
        if (!device) {
          console.warn('[print] KOT reprint received but no kitchen printer is paired on this computer')
          return
        }
        const bytes = buildKotBytes({
          restaurantName: restaurantNameRef.current,
          orderNumber,
          tableName: typeof event['table_name'] === 'string' ? event['table_name'] : '',
          items,
          currency: evStr(event, 'currency'),
          subtotal: evStr(event, 'subtotal'),
          taxTotal: evStr(event, 'tax_total'),
          total: evStr(event, 'total'),
        })
        try {
          await sendBytes(device, bytes)
        } catch {
          /* printer offline / not claimable — silent, Devices page surfaces it */
        }
      })()
      return
    }

    const cfg = configRef.current
    if (!cfg) return

    if (event.type === 'order.created' && cfg.print_kot_enabled) {
      const items = parseKotItems(event['items'])
      if (items.length === 0) return
      const orderNumber = typeof event['order_number'] === 'number' ? event['order_number'] : 0
      const sig = `${String(event['order_id'])}:${orderNumber}:${items.length}`
      const now = Date.now()
      const last = recentKot.current.get(sig)
      if (last && now - last < 10_000) return
      recentKot.current.set(sig, now)

      void (async () => {
        const device = await resolveDevice('kitchen')
        if (!device) {
          // KOT is enabled and an order arrived, but no kitchen printer is paired in
          // this browser — surface it (silent no-op otherwise makes this undebuggable).
          console.warn('[print] KOT received but no kitchen printer is paired on this computer')
          return
        }
        const bytes = buildKotBytes({
          restaurantName: restaurantNameRef.current,
          orderNumber,
          tableName: typeof event['table_name'] === 'string' ? event['table_name'] : '',
          items,
          currency: evStr(event, 'currency'),
          subtotal: evStr(event, 'subtotal'),
          taxTotal: evStr(event, 'tax_total'),
          total: evStr(event, 'total'),
        })
        try {
          await sendBytes(device, bytes)
        } catch {
          /* printer offline / not claimable — silent, Devices page surfaces it */
        }
      })()
      return
    }

    if (event.type === 'invoice.paid' && cfg.print_bill_enabled) {
      const invoiceId = typeof event['invoice_id'] === 'string' ? event['invoice_id'] : null
      if (!invoiceId || printedInvoices.current.has(invoiceId)) return
      printedInvoices.current.add(invoiceId)

      void (async () => {
        const device = await resolveDevice('bill')
        if (!device) return
        try {
          const receipt = await fetchReceipt(invoiceId).unwrap()
          for (const label of copyLabels(cfg.bill_copies)) {
            await sendBytes(device, buildBillBytes(receipt, label))
          }
        } catch {
          // On failure allow a later manual reprint to retry.
          printedInvoices.current.delete(invoiceId)
        }
      })()
    }
  })

  return null
}
