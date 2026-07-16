import { useEffect, useState } from 'react'
import { BrowserRouter } from 'react-router-dom'
import { Provider, useDispatch } from 'react-redux'
import { store } from '@/store/store'
import AppRoutes from '@/routes/AppRoutes'
import ErrorBoundary from '@/components/common/ErrorBoundary'
import Loader from '@/components/common/Loader'
import { api, setAccessToken, setOnRefreshFailed, setOnSessionInvalid } from '@/services/api'
import { _applyToken } from '@/features/auth/authApi'
import { sessionEnded } from '@/features/auth/authSlice'
import { endCustomerSession } from '@/features/session/endSession'
import type { AppDispatch } from '@/store/store'

export default function App() {
  return (
    <Provider store={store}>
      <BrowserRouter>
        <ErrorBoundary>
          <AppBootstrap />
        </ErrorBoundary>
      </BrowserRouter>
    </Provider>
  )
}

/**
 * Runs once on mount:
 * 1. Wires the "refresh failed" callback so any 401 retry that fails triggers logout.
 * 2. Attempts a silent /auth/refresh using the HttpOnly cookie.
 *    - Success → sets the access token in memory and marks the user authenticated.
 *    - Failure → no prior session; user must log in explicitly.
 */
function AppBootstrap() {
  const dispatch = useDispatch<AppDispatch>()
  const [ready, setReady] = useState(false)

  useEffect(() => {
    setOnRefreshFailed(() => {
      setAccessToken(null)
      dispatch(sessionEnded())
    })

    // A customer (table-session) request that 401s means the session was
    // terminated (e.g. after payment) — end it so the guard locks the customer out.
    setOnSessionInvalid(() => {
      endCustomerSession(dispatch)
    })

    api
      .post<{ access_token: string }>('/auth/refresh')
      .then((res) => {
        _applyToken(res.data.access_token, dispatch)
      })
      .catch(() => {
        // No valid session cookie — user will see the login page.
      })
      .finally(() => setReady(true))
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  if (!ready) return <Loader fullscreen message="Initialising…" />

  return <AppRoutes />
}
