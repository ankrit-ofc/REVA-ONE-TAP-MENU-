import { useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { useResetPasswordMutation } from '@/features/auth/authApi'
import { resetPasswordSchema } from '@/lib/schemas/auth'
import { EyeIcon, EyeOffIcon } from './authIcons'
import styles from './Auth.module.css'

export default function ResetPassword() {
  const [searchParams] = useSearchParams()
  const token = searchParams.get('token') ?? ''
  const navigate = useNavigate()
  const [resetPassword, { isLoading }] = useResetPasswordMutation()

  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)

  // No token in the URL → the link is malformed; send them to restart the flow.
  if (!token) {
    return (
      <div className={styles.page}>
        <div className={styles.cardSingle}>
          <h1 className={styles.title}>Reset password</h1>
          <p className={styles.error}>
            This reset link is invalid or incomplete. Please request a new one.
          </p>
          <Link to="/forgot-password" className={styles.link}>Request a new link</Link>
        </div>
      </div>
    )
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setFieldErrors({})
    setFormError(null)

    if (password !== confirm) {
      setFieldErrors({ confirm: 'Passwords do not match.' })
      return
    }

    const parsed = resetPasswordSchema.safeParse({ token, new_password: password })
    if (!parsed.success) {
      const errs: Record<string, string> = {}
      for (const issue of parsed.error.issues) {
        const key = issue.path[0] === 'new_password' ? 'password' : String(issue.path[0] ?? 'form')
        errs[key] = issue.message
      }
      setFieldErrors(errs)
      return
    }

    try {
      await resetPassword(parsed.data).unwrap()
      navigate('/login', { replace: true, state: { resetSuccess: true } })
    } catch {
      setFormError('This reset link is invalid or has expired. Please request a new one.')
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.cardSingle}>
        <h1 className={styles.title}>Set a new password</h1>
        <p className={styles.subtitle}>Choose a new password for your account.</p>

        <form onSubmit={handleSubmit} noValidate>
          <div className={styles.field}>
            <label className={styles.label} htmlFor="password">New Password</label>
            <div className={styles.inputWrap}>
              <input
                id="password"
                className={`${styles.input} ${styles.inputWithIcon} ${fieldErrors['password'] ? styles.inputError : ''}`}
                type={showPassword ? 'text' : 'password'}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="new-password"
                placeholder="At least 8 characters"
              />
              <button
                type="button"
                className={styles.iconBtn}
                onClick={() => setShowPassword((s) => !s)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
              >
                {showPassword ? <EyeOffIcon /> : <EyeIcon />}
              </button>
            </div>
            {fieldErrors['password'] && (
              <span className={styles.fieldError}>{fieldErrors['password']}</span>
            )}
          </div>

          <div className={styles.field}>
            <label className={styles.label} htmlFor="confirm">Confirm Password</label>
            <div className={styles.inputWrap}>
              <input
                id="confirm"
                className={`${styles.input} ${fieldErrors['confirm'] ? styles.inputError : ''}`}
                type={showPassword ? 'text' : 'password'}
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                autoComplete="new-password"
                placeholder="Re-enter your password"
              />
            </div>
            {fieldErrors['confirm'] && (
              <span className={styles.fieldError}>{fieldErrors['confirm']}</span>
            )}
          </div>

          {formError && <p role="alert" className={styles.error}>{formError}</p>}

          <button type="submit" className={styles.submit} disabled={isLoading}>
            {isLoading ? 'Saving…' : 'Reset password'}
          </button>
        </form>

        <Link to="/login" className={`${styles.link} ${styles.backLink}`}>Back to login</Link>
      </div>
    </div>
  )
}
