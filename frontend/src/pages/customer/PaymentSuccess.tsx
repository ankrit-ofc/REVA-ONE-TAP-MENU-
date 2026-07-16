/**
 * Landing page after an online-gateway (eSewa/Khalti) payment redirect.
 *
 * The backend has already verified the payment, closed the order, and invalidated
 * the table session before redirecting here. We end the client session (locking
 * the guest out of the menu) and show the terminal "scan again" screen.
 */
import { useEffect } from 'react'
import { useDispatch } from 'react-redux'
import { endCustomerSession } from '@/features/session/endSession'
import SessionEndedScreen from './SessionEndedScreen'
import type { AppDispatch } from '@/store/store'

export default function PaymentSuccess() {
  const dispatch = useDispatch<AppDispatch>()

  useEffect(() => {
    endCustomerSession(dispatch)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return <SessionEndedScreen />
}
