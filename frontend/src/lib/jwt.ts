/**
 * Decodes the payload of a JWT without verifying its signature.
 * The backend always verifies; here we only need to read claims for UX/routing.
 */
export function decodeJwtPayload(token: string): Record<string, unknown> {
  const parts = token.split('.')
  if (parts.length !== 3) throw new Error('Invalid JWT format')
  const b64 = parts[1].replace(/-/g, '+').replace(/_/g, '/')
  const json = atob(b64)
  return JSON.parse(json) as Record<string, unknown>
}
