/**
 * "Get your receipt by email" sheet — ONE component, two entry points.
 *
 *   1. OrderStatus, when the guest taps Request Bill.
 *   2. BillRequest, on the payment-received screen.
 *
 * Hard rule: this must never gate a core action. The caller fires the bill
 * request BEFORE this opens, and Skip is a first-class, prominent control —
 * skipping (or a submit that fails) still lets the guest through.
 *
 * Shown at most once per visit: on success we set the sessionStorage marker,
 * and both call sites check it before rendering.
 */
import { useState, type FormEvent } from 'react'
import { useSubmitContactMutation } from '@/features/customer/customerApi'
import { markContactCaptured } from '@/features/session/qrStorage'
import Button from '@/components/common/Button'
import styles from './ReceiptContactSheet.module.css'

interface Props {
  /** Label for the dismiss control — the wording differs per entry point. */
  skipLabel?: string
  /** Called after a successful submit, and when the guest skips. */
  onDone: () => void
  /**
   * Explicit session token for the post-payment entry point, where the
   * in-memory token has already been cleared. See customerApi.submitContact.
   */
  sessionToken?: string | null
}

// Deliberately permissive: the backend's EmailStr is the authority (never trust
// the frontend). This only catches obvious typos before a round trip.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/

export default function ReceiptContactSheet({
  skipLabel = 'Skip',
  onDone,
  sessionToken,
}: Props) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [phone, setPhone] = useState('')
  const [emailError, setEmailError] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState(false)

  const [submitContact, { isLoading, isError }] = useSubmitContactMutation()

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()

    const trimmed = email.trim()
    if (!trimmed) {
      setEmailError('Please enter your email address.')
      return
    }
    if (!EMAIL_RE.test(trimmed)) {
      setEmailError('Please enter a valid email address.')
      return
    }
    setEmailError(null)

    try {
      await submitContact({
        body: {
          email: trimmed,
          // Empty strings are normalised to undefined here and to NULL server-side.
          name: name.trim() || undefined,
          phone: phone.trim() || undefined,
        },
        sessionToken,
      }).unwrap()
      markContactCaptured()
      setSubmitted(true)
    } catch {
      // Rendered inline below; the guest can still skip past it.
    }
  }

  if (submitted) {
    return (
      <div className={styles.sheet}>
        <div className={styles.confirmation}>
          <span className={styles.confirmIcon} aria-hidden>
            ✓
          </span>
          <h2 className={styles.title}>Receipt on its way</h2>
          <p className={styles.subtitle}>
            We&apos;ll email your receipt to {email.trim()}.
          </p>
          <Button variant="primary" onClick={onDone} style={{ width: '100%' }}>
            Done
          </Button>
        </div>
      </div>
    )
  }

  return (
    <div className={styles.sheet}>
      <h2 className={styles.title}>Get your receipt by email</h2>
      <p className={styles.subtitle}>
        We&apos;ll email your receipt. We may occasionally send offers — you can
        unsubscribe anytime.
      </p>

      <form className={styles.form} onSubmit={(e) => void handleSubmit(e)} noValidate>
        <label className={styles.label} htmlFor="receipt-email">
          Email
        </label>
        <input
          id="receipt-email"
          className={`${styles.input} ${emailError ? styles.inputError : ''}`.trim()}
          type="email"
          inputMode="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value)
            if (emailError) setEmailError(null)
          }}
          aria-invalid={emailError ? true : undefined}
          aria-describedby={emailError ? 'receipt-email-error' : undefined}
        />
        {emailError && (
          <p className={styles.fieldError} id="receipt-email-error" role="alert">
            {emailError}
          </p>
        )}

        <label className={styles.label} htmlFor="receipt-name">
          Name <span className={styles.optional}>(optional)</span>
        </label>
        <input
          id="receipt-name"
          className={styles.input}
          type="text"
          autoComplete="name"
          value={name}
          onChange={(e) => setName(e.target.value)}
        />

        <label className={styles.label} htmlFor="receipt-phone">
          Phone <span className={styles.optional}>(optional)</span>
        </label>
        <input
          id="receipt-phone"
          className={styles.input}
          type="tel"
          inputMode="tel"
          autoComplete="tel"
          value={phone}
          onChange={(e) => setPhone(e.target.value)}
        />

        {isError && (
          <p className={styles.fieldError} role="alert">
            Sorry — we couldn&apos;t save that. You can skip and still get your bill.
          </p>
        )}

        <div className={styles.actions}>
          <Button type="submit" variant="primary" disabled={isLoading} style={{ width: '100%' }}>
            {isLoading ? 'Sending…' : 'Email me the receipt'}
          </Button>
          <button type="button" className={styles.skip} onClick={onDone}>
            {skipLabel}
          </button>
        </div>
      </form>
    </div>
  )
}
