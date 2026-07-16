import { useState } from 'react'
import { Navigate, Link, useLocation } from 'react-router-dom'
import { useLoginMutation } from '@/features/auth/authApi'
import { loginRequestSchema } from '@/lib/schemas/auth'
import { useAuth } from '@/features/auth/useAuth'
import { EyeIcon, EyeOffIcon, UserIcon, SocialButtons } from './authIcons'
import styles from './Auth.module.css'

export default function Login() {
  const { isAuthenticated, role, signedOutNotice } = useAuth()
  const location = useLocation()
  const resetSuccess = (location.state as { resetSuccess?: boolean } | null)?.resetSuccess === true
  const [login, { isLoading }] = useLoginMutation()

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [slug, setSlug] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)

  // Declarative redirect — <Navigate> in render is the React Router v6 way.
  if (isAuthenticated && role) {
    const dest =
      role === 'SUPERADMIN'      ? '/superadmin'       :
      role === 'ADMIN'           ? '/admin'            :
      role === 'KITCHEN'         ? '/kitchen'          :
      role === 'WAITER'          ? '/waiter'           :
      role === 'COUNTER_DISPLAY' ? '/counter-display'  :
                                   '/counter'
    return <Navigate to={dest} replace />
  }

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setFieldErrors({})
    setFormError(null)

    const parsed = loginRequestSchema.safeParse({
      email,
      password,
      restaurant_slug: slug,
      remember_me: rememberMe,
    })

    if (!parsed.success) {
      const errs: Record<string, string> = {}
      for (const issue of parsed.error.issues) {
        const key = String(issue.path[0] ?? 'form')
        errs[key] = issue.message
      }
      setFieldErrors(errs)
      return
    }

    try {
      await login(parsed.data).unwrap()
      // Navigation handled above on next render (isAuthenticated becomes true).
    } catch {
      setFormError('Invalid email, password, or restaurant identifier.')
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.panel}>
          <div className={styles.panelText}>
            <h2 className={styles.panelTitle}>Welcome</h2>
            <p className={styles.panelSub}>
              Sign in to manage orders, the kitchen, and billing for your restaurant.
            </p>
          </div>
        </div>

        <div className={styles.form}>
          <h1 className={styles.title}>Login</h1>
          <p className={styles.subtitle}>Welcome back! Please login to your account.</p>

          {resetSuccess && !formError && (
            <p role="status" className={styles.success}>
              Your password has been reset. You can now sign in with your new password.
            </p>
          )}

          {signedOutNotice && !formError && !resetSuccess && (
            <p role="status" className={styles.notice}>
              You were signed out. This account may have signed in on another device,
              or your session expired. Please sign in again.
            </p>
          )}

          <form onSubmit={handleSubmit} noValidate>
            <div className={styles.field}>
              <label className={styles.label} htmlFor="restaurant-slug">Restaurant Identifier</label>
              <div className={styles.inputWrap}>
                <input
                  id="restaurant-slug"
                  className={`${styles.input} ${fieldErrors['restaurant_slug'] ? styles.inputError : ''}`}
                  type="text"
                  value={slug}
                  onChange={(e) => setSlug(e.target.value)}
                  autoComplete="organization"
                  placeholder="e.g. my-restaurant"
                />
              </div>
              {fieldErrors['restaurant_slug'] && (
                <span className={styles.fieldError}>{fieldErrors['restaurant_slug']}</span>
              )}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="email">User Name</label>
              <div className={styles.inputWrap}>
                <input
                  id="email"
                  className={`${styles.input} ${styles.inputWithIcon} ${fieldErrors['email'] ? styles.inputError : ''}`}
                  type="email"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  autoComplete="username"
                  placeholder="username@gmail.com"
                />
                <span className={styles.iconStatic}><UserIcon /></span>
              </div>
              {fieldErrors['email'] && (
                <span className={styles.fieldError}>{fieldErrors['email']}</span>
              )}
            </div>

            <div className={styles.field}>
              <label className={styles.label} htmlFor="password">Password</label>
              <div className={styles.inputWrap}>
                <input
                  id="password"
                  className={`${styles.input} ${styles.inputWithIcon} ${fieldErrors['password'] ? styles.inputError : ''}`}
                  type={showPassword ? 'text' : 'password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  autoComplete="current-password"
                  placeholder="••••••••"
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

            <div className={styles.optionsRow}>
              <label className={styles.remember}>
                <input
                  type="checkbox"
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                />
                Remember Me
              </label>
              <Link to="/forgot-password" className={styles.link}>Forgot Password?</Link>
            </div>

            {formError && (
              <p role="alert" className={styles.error}>{formError}</p>
            )}

            <button type="submit" className={styles.submit} disabled={isLoading}>
              {isLoading ? 'Signing in…' : 'Login'}
            </button>
          </form>

          <div className={styles.divider}>or</div>
          <SocialButtons />
        </div>
      </div>
    </div>
  )
}
