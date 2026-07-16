import enum


class Role(str, enum.Enum):
    SUPERADMIN = "SUPERADMIN"
    ADMIN = "ADMIN"
    KITCHEN = "KITCHEN"
    WAITER = "WAITER"
    COUNTER = "COUNTER"
    # Passive wall display at the counter — read-only food-status board.
    COUNTER_DISPLAY = "COUNTER_DISPLAY"


class OrderStatus(str, enum.Enum):
    OPEN = "OPEN"
    MEAL_FINISHED = "MEAL_FINISHED"
    CLOSED = "CLOSED"


class OrderItemStatus(str, enum.Enum):
    # Present only when the restaurant requires waiter approval: the batch is
    # invisible to the kitchen and unprinted until a waiter approves (-> NEW)
    # or rejects (-> CANCELLED) it.
    PENDING_APPROVAL = "PENDING_APPROVAL"
    NEW = "NEW"
    PREPARING = "PREPARING"
    READY = "READY"
    SERVED = "SERVED"
    CANCELLED = "CANCELLED"


class InvoiceStatus(str, enum.Enum):
    DRAFT = "DRAFT"
    PENDING_PAYMENT = "PENDING_PAYMENT"
    PAID = "PAID"
    FAILED = "FAILED"
    VOID = "VOID"
    REFUNDED = "REFUNDED"


class PaymentMethod(str, enum.Enum):
    CASH = "CASH"
    CARD = "CARD"
    COUNTER_WALLET = "COUNTER_WALLET"   # eSewa / Khalti at counter (Nepal)
    QR_GATEWAY = "QR_GATEWAY"           # Fonepay / online QR
    MANUAL_OVERRIDE = "MANUAL_OVERRIDE"


class SessionStatus(str, enum.Enum):
    ACTIVE = "ACTIVE"
    EXPIRED = "EXPIRED"
    INVALIDATED = "INVALIDATED"


class WaiterCallStatus(str, enum.Enum):
    PENDING = "PENDING"      # customer called; no waiter has attended yet
    ATTENDED = "ATTENDED"    # a waiter confirmed they attended the table


class FoodType(str, enum.Enum):
    VEG = "VEG"
    NON_VEG = "NON_VEG"
    EGG = "EGG"
    BEVERAGE = "BEVERAGE"
    SMOKE = "SMOKE"


# ── AR / 3D model feature (optional, per-product) ───────────────────────────────

class ArModelStatus(str, enum.Enum):
    NONE = "NONE"              # default — product has no 3D model, behaves as today
    PENDING = "PENDING"       # views captured, generation not yet started
    GENERATING = "GENERATING"  # generation + marking jobs running
    READY = "READY"           # model + annotations ready for the admin editor
    FAILED = "FAILED"         # a job failed; retry available


class ProductView(str, enum.Enum):
    FRONT = "FRONT"
    BACK = "BACK"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    TOP = "TOP"


class ThreeDModelKey(str, enum.Enum):
    """Selectable fal 3D-generation models (admin dropdown). Values are the registry keys."""
    HUNYUAN3D_V3 = "hunyuan3d-v3"                    # single image, best quality, $0.375
    HUNYUAN3D_V2_MULTIVIEW = "hunyuan3d-v2-multiview"  # front/back/left, ~$0.05 textured
    TRELLIS_MULTI = "trellis-multi"                  # multi-image, ~$0.02


class AnnotationSource(str, enum.Enum):
    AI = "AI"
    MANUAL = "MANUAL"


class AnnotationStatus(str, enum.Enum):
    AI_ESTIMATED = "AI_ESTIMATED"      # draft (renders white to admin)
    ADMIN_VERIFIED = "ADMIN_VERIFIED"  # human-confirmed (renders green)


class GenerationJobKind(str, enum.Enum):
    GENERATION = "GENERATION"  # 4 side views → 3D provider → GLB/USDZ
    MARKING = "MARKING"        # top view → segmentation + VLM → annotations


class GenerationJobStatus(str, enum.Enum):
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    DONE = "DONE"
    FAILED = "FAILED"
