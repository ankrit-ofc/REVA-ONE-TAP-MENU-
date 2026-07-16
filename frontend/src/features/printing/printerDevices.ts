/**
 * Maps the two logical printer roles (kitchen, bill) to a physical USB device
 * the browser has been granted. The mapping is stored in localStorage and is
 * therefore local to this browser/computer — pairing must be done on the counter
 * PC. WebUSB grants persist across reloads, so resolveDevice() reconnects without
 * a prompt.
 */
import { listPaired, type USBDevice } from '@/lib/escpos/webusbPrinter'

export type PrinterRole = 'kitchen' | 'bill'

export interface SavedDevice {
  vendorId: number
  productId: number
  serialNumber?: string
  label?: string
}

type DeviceMap = Record<PrinterRole, SavedDevice | null>

const KEY = 'printer_devices_v1'

function loadMap(): DeviceMap {
  try {
    const raw = localStorage.getItem(KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<DeviceMap>
      return { kitchen: parsed.kitchen ?? null, bill: parsed.bill ?? null }
    }
  } catch {
    /* ignore */
  }
  return { kitchen: null, bill: null }
}

function saveMap(map: DeviceMap): void {
  try {
    localStorage.setItem(KEY, JSON.stringify(map))
  } catch {
    /* ignore */
  }
}

export function getSavedDevice(role: PrinterRole): SavedDevice | null {
  return loadMap()[role]
}

export function setSavedDevice(role: PrinterRole, device: SavedDevice | null): void {
  const map = loadMap()
  map[role] = device
  saveMap(map)
}

export function toSaved(d: USBDevice, label?: string): SavedDevice {
  return {
    vendorId: d.vendorId,
    productId: d.productId,
    serialNumber: d.serialNumber,
    label: label ?? d.productName ?? `USB ${d.vendorId.toString(16)}:${d.productId.toString(16)}`,
  }
}

/**
 * Resolve a role's saved mapping to a live granted USBDevice, or null if it
 * isn't paired/connected. Exact serial match wins; for two identical printers
 * with no serial, kitchen→first / bill→second is a best-effort distinction.
 */
export async function resolveDevice(role: PrinterRole): Promise<USBDevice | null> {
  const map = loadMap()
  const saved = map[role]
  if (!saved) return null

  const paired = await listPaired()
  const matches = paired.filter(
    (p) => p.vendorId === saved.vendorId && p.productId === saved.productId,
  )
  if (matches.length === 0) return null

  if (saved.serialNumber) {
    const exact = matches.find((m) => m.serialNumber === saved.serialNumber)
    if (exact) return exact
  }
  if (matches.length === 1) return matches[0]

  // Two indistinguishable identical printers — route kitchen→[0], bill→[1].
  const other = role === 'kitchen' ? map.bill : map.kitchen
  const identicalToOther =
    other != null &&
    other.vendorId === saved.vendorId &&
    other.productId === saved.productId &&
    !other.serialNumber &&
    !saved.serialNumber
  if (identicalToOther) {
    const idx = role === 'kitchen' ? 0 : 1
    return matches[idx] ?? matches[0]
  }
  return matches[0]
}
