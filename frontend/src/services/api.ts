/**
 * Axios instance with:
 * - In-memory access token (Decision D1 — never in localStorage/sessionStorage).
 * - In-memory customer session token (X-Session-Token header).
 * - Automatic 401 → /auth/refresh retry.  On refresh failure, calls the
 *   registered onRefreshFailed callback so the auth slice can clear state.
 *
 * The refresh token is an HttpOnly cookie set by the backend; the client
 * never reads it — it is sent automatically by the browser on /auth/* paths.
 */
import axios from 'axios'
import type { AxiosError, InternalAxiosRequestConfig } from 'axios'

// ── In-memory token store ─────────────────────────────────────────────────────

let _accessToken: string | null = null
let _sessionToken: string | null = null
let _onRefreshFailed: (() => void) | null = null
let _onSessionInvalid: (() => void) | null = null

export const getAccessToken = (): string | null => _accessToken
export const setAccessToken = (t: string | null): void => { _accessToken = t }

export const getSessionToken = (): string | null => _sessionToken
export const setSessionToken = (t: string | null): void => { _sessionToken = t }

/** Called by App bootstrap to wire up the logout action on refresh failure. */
export const setOnRefreshFailed = (cb: () => void): void => { _onRefreshFailed = cb }

/**
 * Called by App bootstrap. Fires when a customer (table-session) request gets a
 * 401 — i.e. the table session was terminated server-side (e.g. after payment).
 */
export const setOnSessionInvalid = (cb: () => void): void => { _onSessionInvalid = cb }

// ── RTK Query base query helper ───────────────────────────────────────────────

import type { BaseQueryFn } from '@reduxjs/toolkit/query'
import type { AxiosRequestConfig } from 'axios'

export const axiosBaseQuery: BaseQueryFn<
  AxiosRequestConfig,
  unknown,
  { status?: number; data?: unknown; message?: string }
> = async (config) => {
  try {
    const result = await api(config)
    return { data: result.data as unknown }
  } catch (e) {
    const err = e as AxiosError
    return {
      error: {
        status: err.response?.status,
        data: err.response?.data,
        message: err.message,
      },
    }
  }
}

// ── Axios instance ────────────────────────────────────────────────────────────

// Empty base URL → Vite dev proxy handles routing; set VITE_API_BASE_URL in prod.
export const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL ?? '',
  withCredentials: true, // needed for HttpOnly refresh cookie on /auth paths
})

// Attach auth headers on every outgoing request.
// Both are sent when both are set: staff endpoints read Authorization,
// customer endpoints read X-Session-Token, each ignores the other.
// This handles the case where an admin tests the customer flow in the
// same browser session (both tokens are set simultaneously).
api.interceptors.request.use((config) => {
  if (_accessToken) {
    config.headers.Authorization = `Bearer ${_accessToken}`
  }
  if (_sessionToken) {
    config.headers['X-Session-Token'] = _sessionToken
  }
  return config
})

// ── 401 → refresh → retry ────────────────────────────────────────────────────

interface RetryConfig extends InternalAxiosRequestConfig {
  _retry?: boolean
}

// Single in-flight refresh promise so concurrent 401s don't race.
let _refreshPromise: Promise<string> | null = null

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const config = error.config as RetryConfig | undefined

    // Customer-session 401 → the table session was terminated (e.g. after payment).
    // A pure-customer request carries the session token but no access token; there
    // is nothing to refresh, so end the session and let the guard show the terminal
    // "scan again" screen instead of running the staff refresh path below.
    if (
      error.response?.status === 401 &&
      config?.url !== '/auth/refresh' &&
      _sessionToken &&
      !_accessToken
    ) {
      setSessionToken(null)
      _onSessionInvalid?.()
      return Promise.reject(error)
    }

    // Don't retry if: not a 401, already retried, or this IS the refresh call.
    if (
      error.response?.status !== 401 ||
      config?._retry ||
      config?.url === '/auth/refresh'
    ) {
      return Promise.reject(error)
    }

    if (config) config._retry = true

    if (!_refreshPromise) {
      _refreshPromise = api
        .post<{ access_token: string }>('/auth/refresh')
        .then((res) => {
          setAccessToken(res.data.access_token)
          return res.data.access_token
        })
        .catch((refreshErr: unknown) => {
          setAccessToken(null)
          _onRefreshFailed?.()
          return Promise.reject(refreshErr)
        })
        .finally(() => { _refreshPromise = null })
    }

    try {
      const newToken = await _refreshPromise
      if (config) {
        config.headers.Authorization = `Bearer ${newToken}`
        return api(config)
      }
    } catch {
      // refresh failed; already handled above
    }
    return Promise.reject(error)
  },
)
