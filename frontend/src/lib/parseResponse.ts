import type { ZodType } from 'zod'

/**
 * Builds an RTK Query `transformResponse` that validates + coerces the raw
 * response through a Zod schema.
 *
 * This is mandatory for any endpoint returning money: the backend serializes
 * Decimal as JSON **strings** (Pydantic v2), and the schemas declare those
 * fields as `z.coerce.number()`. Without running the schema the typed `number`
 * is a lie at runtime and `.toFixed()` throws. See parseResponse usage across
 * the order/invoice/menu/admin/staff API slices.
 */
export const parseWith =
  <T>(schema: ZodType<T>) =>
  (data: unknown): T =>
    schema.parse(data)
