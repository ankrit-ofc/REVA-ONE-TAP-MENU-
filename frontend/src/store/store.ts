import { configureStore } from '@reduxjs/toolkit'
import { authApi } from '@/features/auth/authApi'
import authReducer from '@/features/auth/authSlice'
import { sessionApi } from '@/features/session/sessionApi'
import sessionReducer from '@/features/session/sessionSlice'
import { menuApi } from '@/features/menu/menuApi'
import { ordersApi } from '@/features/orders/ordersApi'
import { invoicesApi } from '@/features/invoices/invoicesApi'
import cartReducer from '@/features/cart/cartSlice'
import uiReducer from '@/features/ui/uiSlice'
import { kitchenApi } from '@/features/kitchen/kitchenApi'
import { waiterApi } from '@/features/waiter/waiterApi'
import { counterApi } from '@/features/counter/counterApi'
import { counterDisplayApi } from '@/features/counterDisplay/counterDisplayApi'
import { adminApi } from '@/features/admin/adminApi'
import { superadminApi } from '@/features/superadmin/superadminApi'

export const store = configureStore({
  reducer: {
    auth: authReducer,
    session: sessionReducer,
    cart: cartReducer,
    ui: uiReducer,
    [authApi.reducerPath]: authApi.reducer,
    [sessionApi.reducerPath]: sessionApi.reducer,
    [menuApi.reducerPath]: menuApi.reducer,
    [ordersApi.reducerPath]: ordersApi.reducer,
    [invoicesApi.reducerPath]: invoicesApi.reducer,
    [kitchenApi.reducerPath]: kitchenApi.reducer,
    [waiterApi.reducerPath]: waiterApi.reducer,
    [counterApi.reducerPath]: counterApi.reducer,
    [counterDisplayApi.reducerPath]: counterDisplayApi.reducer,
    [adminApi.reducerPath]: adminApi.reducer,
    [superadminApi.reducerPath]: superadminApi.reducer,
  },
  middleware: (getDefaultMiddleware) =>
    getDefaultMiddleware()
      .concat(authApi.middleware)
      .concat(sessionApi.middleware)
      .concat(menuApi.middleware)
      .concat(ordersApi.middleware)
      .concat(invoicesApi.middleware)
      .concat(kitchenApi.middleware)
      .concat(waiterApi.middleware)
      .concat(counterApi.middleware)
      .concat(counterDisplayApi.middleware)
      .concat(adminApi.middleware)
      .concat(superadminApi.middleware),
})

export type RootState = ReturnType<typeof store.getState>
export type AppDispatch = typeof store.dispatch
