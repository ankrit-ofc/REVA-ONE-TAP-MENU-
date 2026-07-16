# Frontend Structure

This adapts the uploaded `react_layout.txt` to the actual app. Three reconciliations
were needed — read these first.

## Reconciliations with the architecture

1. **TypeScript, not JavaScript.** The layout used `.jsx`/`.js`. The architecture
   mandates **React + TypeScript (strict)**. We keep your folder structure exactly
   but use `.tsx` for components and `.ts` for logic. Zod schemas live next to the
   feature API files and are the single source of runtime validation + inferred types.

2. **The backend half of the layout is dropped.** Your layout sketched a Node
   `server.js`/`controllers`/`routes` backend. Our backend is **FastAPI** (already
   planned in Phases 0–8). Ignore the Node backend entirely; `frontend/` is the
   only part of that file we follow.

3. **Generic pages remapped to real surfaces.** `Home/Product/Cart` was an
   e-commerce placeholder. This is a multi-surface POS: one customer surface and
   several staff surfaces, each with its own layout and route guard.

## State management

Your `features/<x>/{xAPI, xSlice, useX}` pattern is kept, using **Redux Toolkit**.
But server data (menu, orders, queue) that must stay live is better as a cache,
so: **RTK Query** for server state + WebSocket-driven cache updates; plain RTK
slices only for client/UI state (cart draft, current session, auth status). The
`useX` hooks wrap RTK Query hooks so components never import the API directly.

## Directory (TypeScript, restaurant-specific)

```
frontend/
  src/
    main.tsx
    App.tsx
    routes/
      AppRoutes.tsx          # public, customer, and role-guarded staff routes
      RequireRole.tsx        # UX guard only — backend is the real authority
    layouts/
      CustomerLayout.tsx     # QR/session header, menu chrome, cart bar
      StaffLayout.tsx        # role-aware sidebar (kitchen/waiter/counter)
      AdminLayout.tsx        # admin/superadmin chrome
    pages/
      customer/
        Scan.tsx             # entry after QR scan -> establishes session
        Menu.tsx             # browse categories/products (images!)
        ProductDetail.tsx    # variants, addons, special instructions
        Cart.tsx             # review before placing/appending
        OrderStatus.tsx      # live item statuses (NEW->...->SERVED)
        BillRequest.tsx      # request bill / pay
      staff/
        Login.tsx
        kitchen/Queue.tsx
        waiter/ReadyItems.tsx
        counter/Billing.tsx
      admin/
        Dashboard.tsx
        Menu.tsx Products.tsx Categories.tsx Tables.tsx Staff.tsx Settings.tsx
      superadmin/
        Restaurants.tsx Subscriptions.tsx Analytics.tsx
    components/
      common/   { Button.tsx + Button.module.css, Input.tsx, Loader.tsx, ... }
      layout/   { Header.tsx, Footer.tsx, StaffSidebar.tsx, AdminSidebar.tsx }
      ui/       { ProductCard.tsx, CartItem.tsx, PriceSummary.tsx,
                  OrderItemStatus.tsx, KitchenTicket.tsx, ... }
    features/
      auth/      { authApi.ts, authSlice.ts, useAuth.ts }
      session/   { sessionApi.ts, sessionSlice.ts, useSession.ts }   # customer table session
      menu/      { menuApi.ts, menuSlice.ts, useMenu.ts }
      cart/      { cartSlice.ts, useCart.ts }                         # client-side draft
      orders/    { ordersApi.ts, ordersSlice.ts, useOrders.ts }
      invoices/  { invoicesApi.ts, useInvoices.ts }
      realtime/  { ws.ts, useRealtime.ts }                           # WS client -> cache updates
    services/
      api.ts        # axios instance: base URL, in-memory access token,
                    # refresh-via-cookie interceptor (Decision D1), 401 retry
    store/
      store.ts
    hooks/    utils/    assets/    types/
```

## Security rules specific to the frontend (also in CLAUDE.md)

- **No JWT in `localStorage`.** Access token lives in memory; refresh token is the
  `HttpOnly` cookie. `api.ts` handles silent refresh.
- **Never `dangerouslySetInnerHTML`** with any data. Let React escape.
- **Zod-validate** every form and every API response shape; cap free-text
  (special instructions ≤ 500 chars) client-side as UX, knowing the backend
  re-enforces it.
- **Role guards are UX only.** A hidden button is not security; the backend
  already rejects unauthorized calls.
- **Authenticate the WebSocket** (staff JWT / customer session token) before
  subscribing; never trust a channel name from the client to choose tenant scope.

## Design priority: the customer surface comes first

The customer never logs in and may be non-technical, on a phone, in a hurry. The
menu/order flow is the product's first impression and gets the most design care:
clear product images, fast category browsing, obvious add-to-cart, live order
status, and an unmistakable "request bill" action. See BUILD_PLAN Phase 9b and
the frontend-design guidance when this phase is built.
