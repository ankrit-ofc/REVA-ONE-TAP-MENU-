from slowapi import Limiter
from slowapi.util import get_remote_address

# In-memory storage (no Redis required).
# All rate limits use the client IP as the key.
limiter = Limiter(key_func=get_remote_address)
