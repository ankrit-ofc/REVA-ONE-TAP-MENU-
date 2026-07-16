/**
 * WebUSB transport for ESC/POS thermal printers.
 *
 * WebUSB isn't in the TS DOM lib, so we declare the minimal surface we use.
 * Caveats (surfaced as typed errors):
 *  - Chromium-only, secure context (HTTPS) — `unsupported`.
 *  - requestDevice() needs a user gesture (the Pair button).
 *  - On Windows the OS `usbprint` driver usually claims the printer, so
 *    claimInterface() fails — `claim-failed` (fix: swap to WinUSB via Zadig).
 */

interface USBEndpoint {
  endpointNumber: number
  direction: 'in' | 'out'
  type: string
}
interface USBAlternateInterface {
  interfaceClass: number
  endpoints: USBEndpoint[]
}
interface USBInterface {
  interfaceNumber: number
  alternate: USBAlternateInterface
  claimed: boolean
}
interface USBConfiguration {
  interfaces: USBInterface[]
}
export interface USBDevice {
  vendorId: number
  productId: number
  serialNumber?: string
  productName?: string
  manufacturerName?: string
  opened: boolean
  configuration: USBConfiguration | null
  open(): Promise<void>
  close(): Promise<void>
  selectConfiguration(configurationValue: number): Promise<void>
  claimInterface(interfaceNumber: number): Promise<void>
  releaseInterface(interfaceNumber: number): Promise<void>
  transferOut(endpointNumber: number, data: BufferSource): Promise<{ status: string; bytesWritten: number }>
}
interface USB {
  requestDevice(options: { filters: Array<{ vendorId?: number; classCode?: number }> }): Promise<USBDevice>
  getDevices(): Promise<USBDevice[]>
}

declare global {
  interface Navigator {
    usb?: USB
  }
}

export type PrinterFailureKind = 'unsupported' | 'no-device' | 'claim-failed' | 'transfer-failed'

export class PrinterError extends Error {
  kind: PrinterFailureKind
  constructor(kind: PrinterFailureKind, message?: string) {
    super(message ?? kind)
    this.name = 'PrinterError'
    this.kind = kind
  }
}

function getUsb(): USB {
  if (typeof navigator === 'undefined' || !navigator.usb) {
    throw new PrinterError(
      'unsupported',
      'WebUSB is not available. Use Chrome/Edge over HTTPS.',
    )
  }
  return navigator.usb
}

/** Prompt the user to pick a printer (must be called from a user gesture). */
export async function requestPrinter(): Promise<USBDevice> {
  // Empty filter shows all USB devices so generic printers (which often report
  // their class only at the interface level) are selectable.
  return getUsb().requestDevice({ filters: [] })
}

/** Devices the user has already granted, available without a prompt. */
export async function listPaired(): Promise<USBDevice[]> {
  if (typeof navigator === 'undefined' || !navigator.usb) return []
  return navigator.usb.getDevices()
}

/** Find a claimable interface with a bulk-OUT endpoint (prefer printer class 7). */
function findOut(device: USBDevice): { interfaceNumber: number; endpointNumber: number } {
  const config = device.configuration
  if (!config) throw new PrinterError('claim-failed', 'No USB configuration.')
  const candidates = config.interfaces
    .map((iface) => {
      const out = iface.alternate.endpoints.find(
        (e) => e.direction === 'out' && e.type === 'bulk',
      )
      return out
        ? { interfaceNumber: iface.interfaceNumber, endpointNumber: out.endpointNumber, cls: iface.alternate.interfaceClass }
        : null
    })
    .filter((x): x is { interfaceNumber: number; endpointNumber: number; cls: number } => x !== null)
  if (candidates.length === 0) {
    throw new PrinterError('claim-failed', 'No printable (bulk-OUT) interface found.')
  }
  const printer = candidates.find((c) => c.cls === 7) ?? candidates[0]
  return { interfaceNumber: printer.interfaceNumber, endpointNumber: printer.endpointNumber }
}

/** Open/claim if needed and send the bytes to the printer. */
export async function sendBytes(device: USBDevice, data: Uint8Array): Promise<void> {
  try {
    if (!device.opened) await device.open()
    if (device.configuration === null) await device.selectConfiguration(1)
    const { interfaceNumber, endpointNumber } = findOut(device)
    try {
      await device.claimInterface(interfaceNumber)
    } catch (e) {
      // Already-claimed is fine; a real claim failure is the Windows driver case.
      const iface = device.configuration?.interfaces.find(
        (i) => i.interfaceNumber === interfaceNumber,
      )
      if (!iface?.claimed) {
        throw new PrinterError(
          'claim-failed',
          'Could not claim the printer. On Windows, install the WinUSB driver for it with Zadig.',
        )
      }
      void e
    }
    await device.transferOut(endpointNumber, data)
  } catch (e) {
    if (e instanceof PrinterError) throw e
    throw new PrinterError('transfer-failed', e instanceof Error ? e.message : 'Print failed.')
  }
}

export function describePrinterError(e: unknown): string {
  if (e instanceof PrinterError) {
    switch (e.kind) {
      case 'unsupported':
        return 'WebUSB is unavailable. Use Chrome or Edge over HTTPS on the counter computer.'
      case 'no-device':
        return 'Printer is not paired on this computer. Click Pair and pick the printer.'
      case 'claim-failed':
        return 'Windows is holding this printer. Install its WinUSB driver with Zadig, then retry.'
      default:
        return 'Printing failed. Check the printer is on, has paper, and is connected.'
    }
  }
  return 'Printing failed.'
}
