import { Routes, Route, Navigate } from 'react-router-dom'
import RequireRole from './RequireRole'
import RequireSession from './RequireSession'

// Layouts
import StaffLayout from '@/layouts/StaffLayout'
import AdminLayout from '@/layouts/AdminLayout'
import SuperadminLayout from '@/layouts/SuperadminLayout'
import CustomerLayout from '@/layouts/CustomerLayout'

// Public landing site (single-page REVA TAP marketing, shared chrome)
import LandingLayout from '@/pages/landing/LandingLayout'
import LandingHome from '@/pages/landing/Home'

// Auth
import Login from '@/pages/staff/Login'
import ForgotPassword from '@/pages/staff/ForgotPassword'
import ResetPassword from '@/pages/staff/ResetPassword'

// Customer surface (9b)
import Scan from '@/pages/customer/Scan'
import Menu from '@/pages/customer/Menu'
import ProductDetail from '@/pages/customer/ProductDetail'
import Cart from '@/pages/customer/Cart'
import OrderStatus from '@/pages/customer/OrderStatus'
import BillRequest from '@/pages/customer/BillRequest'
import PaymentSuccess from '@/pages/customer/PaymentSuccess'
import PaymentFailure from '@/pages/customer/PaymentFailure'

// Kitchen surface (9c)
import KitchenQueue from '@/pages/staff/kitchen/Queue'

// Waiter surface (9d)
import WaiterReadyItems from '@/pages/staff/waiter/ReadyItems'
import WaiterOrders from '@/pages/staff/waiter/WaiterOrders'
import WaiterBilling from '@/pages/staff/waiter/WaiterBilling'

// Counter surface (9e)
import CounterBilling from '@/pages/staff/counter/Billing'

// Printer devices (counter + admin)
import Devices from '@/pages/staff/Devices'

// Counter display surface (passive wall board)
import CounterDisplay from '@/pages/staff/counter/CounterDisplay'

// Admin surface (9f)
import AdminDashboard from '@/pages/admin/Dashboard'
import AdminCategories from '@/pages/admin/Categories'
import AdminProducts from '@/pages/admin/Products'
import AdminAddons from '@/pages/admin/Addons'
import AdminStaff from '@/pages/admin/Staff'
import AdminTables from '@/pages/admin/Tables'
import AdminSettings from '@/pages/admin/Settings'

// Superadmin surface (9g — placeholder; backend endpoints not yet built)
import SuperadminRestaurants from '@/pages/superadmin/Restaurants'

export default function AppRoutes() {
  return (
    <Routes>
      {/* ── Public ─────────────────────────────────────────────────────────── */}
      <Route path="/login" element={<Login />} />
      <Route path="/forgot-password" element={<ForgotPassword />} />
      <Route path="/reset-password" element={<ResetPassword />} />

      {/* QR scan — no session required yet */}
      <Route path="/scan" element={<Scan />} />

      {/* Gateway payment redirects (public — the session is already ended on success) */}
      <Route path="/payment/success" element={<PaymentSuccess />} />
      <Route path="/payment/failure" element={<PaymentFailure />} />

      {/* ── Customer (session-gated: UX guard + transparent re-scan) ──────── */}
      <Route element={<RequireSession />}>
        <Route element={<CustomerLayout />}>
          <Route path="/menu" element={<Menu />} />
          <Route path="/product/:productId" element={<ProductDetail />} />
          <Route path="/cart" element={<Cart />} />
          <Route path="/order-status" element={<OrderStatus />} />
          <Route path="/bill" element={<BillRequest />} />
        </Route>
      </Route>

      {/* ── Kitchen (KITCHEN or ADMIN) ───────────────────────────────────── */}
      <Route element={<RequireRole roles={['KITCHEN', 'ADMIN']} />}>
        <Route element={<StaffLayout />}>
          <Route path="/kitchen" element={<KitchenQueue />} />
        </Route>
      </Route>

      {/* ── Waiter (WAITER or ADMIN) ─────────────────────────────────────── */}
      <Route element={<RequireRole roles={['WAITER', 'ADMIN']} />}>
        <Route element={<StaffLayout />}>
          <Route path="/waiter" element={<WaiterReadyItems />} />
          <Route path="/waiter/orders" element={<WaiterOrders />} />
          <Route path="/waiter/billing" element={<WaiterBilling />} />
        </Route>
      </Route>

      {/* ── Counter (COUNTER or ADMIN) ───────────────────────────────────── */}
      <Route element={<RequireRole roles={['COUNTER', 'ADMIN']} />}>
        <Route element={<StaffLayout />}>
          <Route path="/counter" element={<CounterBilling />} />
          <Route path="/counter/devices" element={<Devices />} />
        </Route>
      </Route>

      {/* ── Counter Display (passive board: COUNTER_DISPLAY, COUNTER or ADMIN) ─ */}
      <Route element={<RequireRole roles={['COUNTER_DISPLAY', 'COUNTER', 'ADMIN']} />}>
        <Route element={<StaffLayout />}>
          <Route path="/counter-display" element={<CounterDisplay />} />
        </Route>
      </Route>

      {/* ── Admin (ADMIN only) ───────────────────────────────────────────── */}
      <Route element={<RequireRole roles={['ADMIN']} />}>
        <Route element={<AdminLayout />}>
          <Route path="/admin" element={<AdminDashboard />} />
          <Route path="/admin/categories" element={<AdminCategories />} />
          <Route path="/admin/products" element={<AdminProducts />} />
          <Route path="/admin/addons" element={<AdminAddons />} />
          <Route path="/admin/staff" element={<AdminStaff />} />
          <Route path="/admin/tables" element={<AdminTables />} />
          <Route path="/admin/devices" element={<Devices />} />
          <Route path="/admin/settings" element={<AdminSettings />} />
        </Route>
      </Route>

      {/* ── Superadmin (SUPERADMIN only) ─────────────────────────────────── */}
      <Route element={<RequireRole roles={['SUPERADMIN']} />}>
        <Route element={<SuperadminLayout />}>
          <Route path="/superadmin" element={<SuperadminRestaurants />} />
        </Route>
      </Route>

      {/* Public landing site (single page) */}
      <Route element={<LandingLayout />}>
        <Route path="/" element={<LandingHome />} />
      </Route>

      {/* Fallback */}
      <Route path="*" element={<Navigate to="/login" replace />} />
    </Routes>
  )
}
