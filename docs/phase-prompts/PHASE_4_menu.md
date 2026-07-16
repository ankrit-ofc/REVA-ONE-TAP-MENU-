PHASE 4 — Menu domain (admin CRUD + product images)

Context:
- Phases 0–3 done: schema, staff auth/RBAC/tenant scope, and customer table
  sessions all work and are tested.
- This phase builds the menu: tenant-scoped admin CRUD for categories, products,
  variants, addons, addon mappings, and restaurant settings; secure product-image
  upload; and a customer-facing menu read that hides unavailable items.
- Done = CRUD is tenant-scoped and role-gated; cross-tenant access fails; disguised
  or oversized image uploads are rejected; the customer menu omits
  unavailable/inactive items.

Read first: CLAUDE.md (§3 Tenancy, File uploads, §5 exclusions),
docs/BUILD_PLAN.md (Phase 4, decision D8). Confirm scope back to me in one line.

Threat model for this phase:
- Assume the attacker: calls admin endpoints without/with a wrong-role token,
  targets another restaurant's category/product IDs, uploads a script renamed
  `.jpg` or a 50 MB / 20000px image, and sends extra fields hoping one is trusted.

Scope — build these files and only these:
- backend/app/schemas/menu.py: Pydantic create/update/response models for Category,
  Product, ProductVariant, ProductAddon, AddonMapping, RestaurantSettings — all
  extra="forbid", with length/numeric bounds; money fields Decimal.
- backend/app/services/menu_service.py: tenant-scoped CRUD; soft delete via
  is_active (never DELETE); validates FKs belong to the same restaurant (e.g. a
  product's category_id is tenant-owned).
- backend/app/services/image_service.py: validate upload by magic bytes (allow
  jpeg/png/webp only), enforce max size and max dimensions, strip EXIF, write
  under a UUID filename in a tenant-scoped path. V1 storage = local volume at
  /media/{restaurant_id}/{uuid}.{ext}; expose a STORAGE interface so object
  storage (D8) can replace it later. Returns the controlled image_url.
- backend/app/api/admin_menu.py: ADMIN-only routers for all CRUD above, plus
  POST /admin/products/{id}/image (multipart) -> sets products.image_url.
- backend/app/api/menu.py: customer (session) read — GET /menu returns active
  categories ordered by display_order, each with available+active products
  (variants, allowed addons, image_url, tax_rate). Hides is_available=false and
  is_active=false.
- backend/app/api/settings.py: ADMIN get/update RestaurantSettings.

Data contracts (enforce bounds):
- ProductCreate{category_id:UUID, name:str(1..120), base_price:Decimal(>=0),
  tax_rate:Decimal(0..100), is_available:bool, has_variants:bool,
  allows_addons:bool} extra="forbid".
- VariantCreate{product_id, name(1..60), price:Decimal(>=0)}.
- AddonCreate{name(1..60), price:Decimal(>=0)}.
- CategoryCreate{name(1..80), display_order:int(>=0)}.
- Image upload limits: <= 5 MB, <= 4000x4000 px (confirm or adjust).

Specifications:
- Every query is tenant-scoped via the Phase 2 dependency; never fetch by id alone.
- Image_url is set ONLY by the backend after a successful upload; the client can
  never set it directly (omit it from create/update schemas).
- Soft delete returns the record marked inactive; it stays referenceable by
  historical orders later (snapshots, Phase 5).

Dependencies to install (pinned): Pillow (image validation/EXIF strip),
python-multipart (FastAPI file uploads). Confirm versions.

Out of scope — do NOT touch / add:
- No orders, invoices, payments, websockets.
- No object-storage SDK yet (local volume V1 behind the storage interface).
- No rate limiting (Phase 10).
- Do not change the Phase 1 schema except nothing should be needed; if you think
  it is, STOP and ask.

Must not break (regression guard):
- /auth/*, /scan, /session/*, /health all still work; migrations still clean.

ASK BEFORE: any schema change; switching image storage to a cloud SDK now;
changing the allowed image types or size/dimension limits. (CLAUDE.md §6 applies.)

Functional acceptance — run these and paste the real output:
1. As ADMIN: create a category, a product under it, a variant, an addon, map it;
   then GET the admin product list. Expected: all present, tenant-scoped.
2. Upload a valid small JPEG to the product; GET /menu as a customer session.
   Expected: product appears with image_url; unavailable product (toggle one off)
   does NOT appear.

Security acceptance — run these and paste the real output:
1. Call an admin endpoint with a WAITER token. Expected: 403.
2. As ADMIN of restaurant A, GET/PUT a product ID owned by restaurant B.
   Expected: 404/403, no data leak.
3. Upload a text file renamed `evil.jpg`. Expected: rejected (magic-byte check).
4. Upload a 10 MB or 8000x8000 image. Expected: rejected.
5. Send ProductCreate with an extra field `{"image_url":"http://attacker"}`.
   Expected: 422 (extra="forbid"); image_url never set from client input.

Definition of done: see CLAUDE.md §8. Then stop — do not start Phase 5.
Stop and ask before deviating from this spec.
