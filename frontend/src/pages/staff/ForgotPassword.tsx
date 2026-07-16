import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useForgotPasswordMutation } from '@/features/auth/authApi'
import { forgotPasswordSchema } from '@/lib/schemas/auth'
import styles from './Auth.module.css'

export default function ForgotPassword() {
  const [forgotPassword, { isLoading }] = useForgotPasswordMutation()

  const [email, setEmail] = useState('')
  const [slug, setSlug] = useState('')
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [sent, setSent] = useState(false)

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setFieldErrors({})

    const parsed = forgotPasswordSchema.safeParse({ email, restaurant_slug: slug })
    if (!parsed.success) {
      const errs: Record<string, string> = {}
      for (const issue of parsed.error.issues) {
        errs[String(issue.path[0] ?? 'form')] = issue.message
      }
      setFieldErrors(errs)
      return
    }

    try {
      await forgotPassword(parsed.data).unwrap()
    } catch {
      // Intentionally ignored — we always show the same generic confirmation so
      // we never reveal whether an account exists (matches the backend).
    }
    setSent(true)
  }

  return (
    <div className={styles.page}>
      <div className={styles.cardSingle}>
        <h1 className={styles.title}>Forgot password</h1>

        {sent ? (
          <>
            <p className={styles.success}>
              If an account matches those details, we&apos;ve sent a password reset link to
              your email. The link expires soon and can be used only once.
            </p>
            <Link to="/login" className={styles.link}>Back to login</Link>
          </>
        ) : (
          <>
            <p className={styles.subtitle}>
              Enter your restaurant and email and we&apos;ll send you a reset link.
            </p>
            <form onSubmit={handleSubmit} noValidate>
              <div className={styles.field}>
                <label className={styles.label} htmlFor="restaurant-slug">Restaurant Identifier</label>
                <input
                  id="restaurant-slug"
                  className={`${styles.input} ${fieldErrors['restaurant_slug'] ? styles.inputError : ''}`}
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  autoComplete="organization"
                  placeholder="e.g. my-restaurant"
                />
                {fieldErrors['restaurant_slug'] && (
                  <span className={styles.fieldError}>{fieldErrors['restaurant_slug']}</span>
                )}
              </div>

              <div className={styles.field}>
                <label className={styles.label} htmlFor="email">Email</label>
                <input
                  id="email"
                  className={`${styles.input} ${fieldErrors['email'] ? styles.inputError : ''}`}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                  placeholder="username@gmail.com"
                />
                {fieldErrors['email'] && (
                  <span className={styles.fieldError}>{fieldErrors['email']}</span>
                )}
              </div>

              <button type="submit" className={styles.submit} disabled={isLoading}>
                {isLoading ? 'Sending…' : 'Send reset link'}
              </button>
            </form>
            <Link to="/login" className={`${styles.link} ${styles.backLink}`}>Back to login</Link>
          </>
        )}
      </div>
    </div>
  )
}
