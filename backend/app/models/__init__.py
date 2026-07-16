# Import all models here so Base.metadata is fully populated when alembic env.py
# imports this package.  Order matters: parents before children.
from app.models.restaurant import Restaurant, RestaurantSettings  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.product import Product, ProductVariant, ProductAddon, ProductAddonMapping  # noqa: F401
from app.models.ar import GenerationJob, ModelAnnotation, ProductViewImage  # noqa: F401
from app.models.table import Table, TableSession  # noqa: F401
from app.models.waiter_call import WaiterCall  # noqa: F401
from app.models.order import Order, OrderItem, OrderItemAddon  # noqa: F401
from app.models.invoice import Invoice  # noqa: F401
from app.models.audit_log import AuditLog  # noqa: F401
from app.models.restaurant_counter import RestaurantCounter  # noqa: F401
from app.models.refresh_token import RefreshToken  # noqa: F401
from app.models.kot_print_job import KotPrintJob  # noqa: F401
from app.models.device_token import DeviceToken  # noqa: F401
