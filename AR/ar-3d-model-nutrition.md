# Claude Code Build Plan — Optional AR 3D Models + Editable Nutrition Tags

A spec for adding an **optional, per-product** AR feature to the existing
restaurant QR-ordering app: an admin can attach a 3D model to a product, the
system generates it from photos and drafts per-component nutrition tags, the
admin corrects them, and customers view the dish in AR on their table.

---

## 0. Locked decisions (don't re-litigate these)

- Stack: React (frontend) + FastAPI (backend) + Postgres (db), hosted on Vultr.
- 3D generation: **call a hosted API** (no GPU yet). Model: **Hunyuan 3.0**
  (multiview, 4 side views), fallback Hunyuan 2.1.
- Inputs per product: **5 labeled images** — front, back, left, right (→ generation)
  and **top** (→ marking). The API takes named view slots, not arbitrary files.
- Marking: segmentation (LangSAM / GroundingDINO+SAM2) on the **top** image to
  locate + label components, then a VLM to draft per-component nutrition.
- Tag placement: **V2 auto-projection** sets initial hotspot positions, then the
  admin can reposition any dot and edit any nutrition value.
- Viewer: Google `<model-viewer>` for both the admin editor and customer AR.
- Formats: `.glb` (Android/web) + `.usdz` (iOS) per model.
- The feature is **optional per product** — added via an "Add 3D model" form on
  create or edit, never mandatory.
- Generation runs as a **non-blocking, one-after-another pipeline**: uploading 5
  images queues a job, the UI shows "generating", the admin moves on, and the
  product flips to "3D model available" when done.
- Provider is **abstracted** so generation can later move from hosted → serverless
  → own Docker/GPU by swapping an adapter, no app rewrite.

---

## 1. Architecture: two parallel tracks, converging at the editor

Per product with a 3D model, two independent jobs run from the same upload:

- **Generation track:** 4 side images → Hunyuan 3.0 API → GLB → convert to USDZ →
  store on CDN.
- **Marking track:** top image → segmentation → components + 2D spots → VLM
  nutrition draft → annotation list (`ai_estimated`).

Neither waits on the other. When both finish, an optional auto-projection step
places the draft tags onto the model, and the product becomes editable in the
admin editor. Customers only ever see admin-verified tags.

---

## 2. Data model (Postgres)

**products** (existing — add columns)

- `model_status` — enum: `none` (default) | `pending` | `generating` | `ready` | `failed`
- `model_glb_url` — text, nullable
- `model_usdz_url` — text, nullable

**product_view_images** (new)

- `id` (pk)
- `product_id` (fk)
- `view` — enum: `front` | `back` | `left` | `right` | `top`
- `image_url` — text (original upload, on CDN)
- unique(`product_id`, `view`)

**model_annotations** (new)

- `id` (pk)
- `product_id` (fk)
- `label` — text (e.g. "cheese")
- `position_x`, `position_y`, `position_z` — float (point on mesh surface)
- `normal_x`, `normal_y`, `normal_z` — float (hotspot orientation)
- `calories`, `protein_g`, `carbs_g`, `fat_g` — numeric, nullable
- `allergens` — text[] / jsonb
- `source` — enum: `ai` | `manual`
- `status` — enum: `ai_estimated` | `admin_verified`
- `created_at`, `updated_at`

**generation_jobs** (new — drives the pipeline)

- `id` (pk)
- `product_id` (fk)
- `kind` — enum: `generation` | `marking`
- `provider` — text (e.g. `hosted_hunyuan_3_0`)
- `status` — enum: `queued` | `running` | `done` | `failed`
- `external_job_id` — text, nullable (the hosted API's task id)
- `error` — text, nullable
- `created_at`, `updated_at`

---

## 3. Backend (FastAPI)

### Endpoints

- `POST /products/{id}/model/images` — upload the 5 labeled view images
  (multipart, each tagged with its `view`). Stores to CDN + `product_view_images`.
- `POST /products/{id}/model/generate` — enqueue generation + marking jobs for the
  product; sets `model_status = generating`; returns immediately (202). **Non-blocking.**
- `GET /products/{id}/model/status` — poll status (or use SSE/WebSocket for push).
- `GET /products/{id}/annotations` — list annotations.
- `PUT /products/{id}/annotations/{aid}` — edit value, reposition (new position/normal),
  rename; flips `status` to `admin_verified`.
- `POST /products/{id}/annotations` / `DELETE …/{aid}` — add / remove a tag.
- `POST /products/{id}/model/publish` — gate: only allow if a GLB exists and the
  admin has reviewed; this is what exposes it to customers.
- `GET /menu/products/{id}` (customer) — returns `model_glb_url`, `model_usdz_url`,
  and **verified** annotations only, when `model_status = ready` and published.
- Webhook receivers (if the chosen host supports callbacks):
  `POST /webhooks/generation`, `POST /webhooks/marking`.

### Job pipeline

- A worker processes `generation` jobs **single-concurrency, FIFO** (one model at a
  time — the "pipeline one after another" requirement). `marking` jobs may run
  concurrently with generation since they don't share the GPU.
- MVP queue: FastAPI `BackgroundTasks` + a DB-backed queue is acceptable; graduate
  to `arq` / Celery / RQ when volume grows.
- **Generation worker:** call the 3D provider with the 4 side images → poll or await
  webhook → download GLB → convert GLB→USDZ → upload both to CDN → write
  `model_glb_url` / `model_usdz_url`.
- **Marking worker:** segmentation on the top image → labeled components + 2D
  centroids → VLM nutrition draft → insert `model_annotations` (`source=ai`,
  `status=ai_estimated`). Positions left empty here.
- **Converge step:** when both jobs are `done`, run auto-projection (see §4) to fill
  initial annotation positions, then set `model_status = ready`.
- On any failure → `model_status = failed`, store error, surface a retry action.

### Provider adapter (important for the future phases)

- Define a `ThreeDProvider` interface: `generate(images: dict[view,url]) -> glb_bytes`.
- Implementations: `HostedHunyuanProvider` (now), `ServerlessProvider` (future),
  `DockerGpuProvider` (future). Selected by config/env. Same pattern for a
  `MarkingProvider` (segmentation + VLM).
- **Confirm at integration:** the chosen hosted endpoint returns a _textured_ GLB
  from multi-view input (some 2.x multi-view paths are geometry-only).

---

## 4. The 2D→3D combine (auto-projection + manual override)

- The top photo and the model share a top-down framing. Render the model top-down,
  take each component's normalized 2D centroid, ray-cast onto the mesh to get a
  surface point + normal → initial hotspot position. Works well for flat dishes,
  approximate for tall ones — which is why the admin can always override.
- `<model-viewer>` provides `positionAndNormalFromPoint(x, y)`; an admin click
  returns the same `{position, normal}` shape, so AI-placed and hand-placed
  hotspots are identical data.

---

## 5. Frontend (React)

### Add / Edit Product — optional 3D

- On the existing add/edit product form, add an **"Add 3D model"** toggle/button.
  When off, nothing changes (product has no AR). When on, reveal a dynamic sub-form.
- `Model3DForm` (dynamic): **5 labeled image inputs** — Front, Back, Left, Right, Top.
  Each input accepts **file upload OR camera capture** (`getUserMedia`). Label each
  clearly so the right photo lands in the right view slot.
- Submitting the sub-form uploads the images and calls `…/model/generate`.
- **Non-blocking UX:** the form shows "Generating 3D model…" and lets the admin save
  the product and move to the next one immediately. A `ModelStatusBadge`
  (`none` / `generating` / `ready` / `failed`) reflects state, polled or pushed.
- The "Add 3D model" option is available on **edit** too, so a product created
  without a model can get one later.

### Admin 3D editor (`Model3DEditor`)

- Left: `<model-viewer>` showing the GLB with one hotspot per annotation
  (auto-placed by §4).
- Right: `AnnotationPanel` — list of components, each with editable
  calories/protein/carbs/fat/allergens and an "AI estimate / Verified" badge.
- Actions: edit values, click the model to reposition a dot, add a tag, delete a tag.
  Saving an annotation flips it to `admin_verified`.
- A "Publish" action gates customer visibility.

### Customer menu

- On a product that has a published, ready model, show a **"Show 3D view"** button.
- Tapping it opens `ARViewer` (`<model-viewer ar ar-scale="fixed">`) that places the
  dish on the table via camera, lets the user **pinch-to-scale for a closer look**,
  and renders the **verified** nutrition tags as read-only hotspots.
- Where AR isn't supported, degrade to an interactive 3D preview.

---

## 6. Build order (milestones for Claude Code)

- **M1 — Capture.** Data model + product 3D columns + the optional "Add 3D model"
  form with 5 labeled image inputs (upload + camera) + storage. No generation yet —
  just capture and persist the labeled views. (Verifiable on its own.)
- **M2 — Generation pipeline.** Provider adapter + `HostedHunyuanProvider` (3.0, 4
  side views) + the single-concurrency job queue + GLB→USDZ conversion + CDN +
  status transitions. Non-blocking UI + status badge.
- **M3 — Marking pipeline.** `MarkingProvider` (segmentation on top image + VLM
  nutrition draft) + annotations written as `ai_estimated`, running parallel to M2.
- **M4 — Combine + editor.** Auto-projection initial placement + `Model3DEditor`
  with editable/repositionable hotspots + verify + publish gate.
- **M5 — Customer AR.** "Show 3D view" button + `ARViewer` with pinch-to-scale +
  read-only verified tags + non-AR fallback.
- **M6 — Hardening.** Failed-state handling + retries + edge cases (missing views,
  oversized models, scale sanity check ≈30 cm for a pizza).

---

## 7. Future phases (already designed for)

- **Serverless GPU:** swap the provider adapter to a serverless endpoint
  (Modal/RunPod) running the model; the rest of the app is unchanged. The notebook
  generation code becomes the container handler.
- **Own Docker + GPU:** when volume is steady, deploy a pinned Docker image
  (e.g. NVIDIA NIM for TRELLIS, or a Hunyuan container) on a dedicated/rented GPU and
  point the adapter at it. Config swap, not a rewrite.

---

## 8. Open items to confirm during build

- Pick the hosted Hunyuan 3.0 endpoint that accepts the 4 named side-view slots and
  returns a **textured** GLB; wire its task/poll/webhook flow into the generation worker.
- Choose the VLM for the nutrition draft (a hosted vision model is fine to start).
- GLB→USDZ conversion path (Apple USD tools or a library) for iOS AR.
- Confirm CDN serves `.glb` as `model/gltf-binary` and `.usdz` as `model/vnd.usdz+zip`.

## 9. Guardrails (non-negotiable)

- AI nutrition numbers are **drafts** (`ai_estimated`). The recipe is the source of
  truth. Nothing unverified is shown to customers — especially allergens. The
  publish gate enforces this.
- The whole 3D feature is optional; a product with `model_status = none` behaves
  exactly as today.
