from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    DATABASE_URL: str
    SECRET_KEY: str
    QR_SECRET: str
    ENVIRONMENT: str = "development"

    ACCESS_TOKEN_EXPIRE_MINUTES: int = 5
    # Refresh-token lifetime is role-aware and a sliding window: a short window
    # for staff (re-opening within it resets the clock), and a long one for the
    # always-on counter wall display so it never logs itself out.
    REFRESH_TOKEN_EXPIRE_HOURS: int = 12
    REFRESH_TOKEN_DISPLAY_EXPIRE_HOURS: int = 168  # 7 days, COUNTER_DISPLAY only
    # "Remember me" — when a staff login opts in, the refresh window is extended
    # this far (non-DISPLAY roles), so they stay signed in across browser restarts.
    REMEMBER_ME_REFRESH_TOKEN_EXPIRE_HOURS: int = 720  # 30 days
    TABLE_SESSION_TTL_HOURS: int = 4

    # Forgot-password reset token validity window.
    PASSWORD_RESET_TOKEN_EXPIRE_MINUTES: int = 60

    # URLs for redirects after payment
    BACKEND_BASE_URL: str = "http://localhost:8000"
    FRONTEND_BASE_URL: str = "http://localhost:5173"

    # eSewa ePay v2 — sandbox defaults; override in production via env vars.
    # Secrets MUST NOT be committed. ESEWA_SECRET_KEY goes in .env (gitignored).
    ESEWA_SECRET_KEY: str = "8gBm/:&EnhH.1/q("   # sandbox test key
    ESEWA_PRODUCT_CODE: str = "EPAYTEST"           # use merchant code in prod

    # Khalti — secret key required for server-side lookup call.
    KHALTI_SECRET_KEY: str = ""
    KHALTI_WEBSITE_URL: str = "http://localhost:5173"

    # Fonepay — merchant PID and HMAC secret.
    FONEPAY_MERCHANT_CODE: str = ""
    FONEPAY_SECRET_KEY: str = ""

    # CORS — comma-separated list of allowed origins.
    # In production set to the exact frontend URL; never leave as wildcard with credentials.
    ALLOWED_ORIGINS: str = "http://localhost:5173,http://localhost:3000"

    # Rate limits (slowapi format: "N/period", e.g. "5/minute").
    RATE_LIMIT_LOGIN: str = "5/minute"
    RATE_LIMIT_SCAN: str = "20/minute"
    RATE_LIMIT_ORDERS: str = "30/minute"
    RATE_LIMIT_PASSWORD_RESET: str = "3/minute"
    # Generous: slowapi keys on IP and a venue's diners share one public IP; the
    # real anti-spam guard is the per-device cooldown in the customer UI.
    RATE_LIMIT_CALL_WAITER: str = "20/minute"

    # ── AR / 3D model providers ──────────────────────────────────────────────────
    # Provider adapters are selected by name so generation/marking can move from the
    # dummy stubs → hosted APIs (fal.ai, platform.claude.com) → own GPU by config
    # swap, with no app rewrite. "dummy" performs no external calls and assigns the
    # hardcoded spike model to every product.
    AR_THREED_PROVIDER: str = "dummy"       # 3D generation adapter ("dummy" | "fal")
    AR_MARKING_PROVIDER: str = "dummy"      # nutrition-VLM adapter ("dummy" | "claude")
    AR_USDZ_CONVERTER: str = "dummy"        # GLB → USDZ (iOS AR Quick Look)
    # Hardcoded spike model URLs the dummy providers return (served by Caddy).
    AR_SPIKE_GLB_URL: str = "/models/pizza.glb"
    AR_SPIKE_USDZ_URL: str = "/models/pizza.usdz"

    # Real-provider credentials + model ids (empty keys → keep using "dummy").
    # Both keys stay server-side; never expose them to the browser. Model ids are
    # config so you can downgrade to a cheaper model with the SAME key, no code change.
    FAL_KEY: str = ""                       # fal_client reads this from the env
    ANTHROPIC_API_KEY: str = ""             # passed explicitly to the Anthropic client
    # Default 3D model when the admin doesn't pick one (registry key, not an endpoint).
    # Options: hunyuan3d-v3 | hunyuan3d-v2-multiview | trellis-multi. v2-multiview is
    # ~7x cheaper than v3 and uses the multi-view photos we already capture.
    AR_DEFAULT_THREED_MODEL: str = "hunyuan3d-v2-multiview"
    AR_MARKING_MODEL: str = "claude-sonnet-4-6"

    # After generation the raw fal GLB (~30 MB) is downloaded into our own /media,
    # compressed (quantized geometry + WebP textures) and optionally converted to USDZ.
    AR_COMPRESS_MODELS: bool = True         # False → localize only, skip compression
    AR_MODEL_TEXTURE_SIZE: int = 2048       # max texture dimension when compressing
    # GLB → USDZ runs in the Blender sidecar container (AR_USDZ_CONVERTER="sidecar").
    MODEL_CONVERTER_URL: str = "http://model-converter:9000"

    # ── Email / SMTP ─────────────────────────────────────────────────────────────
    # Used to send password-reset links. When SMTP_HOST is empty (default, dev), the
    # email service logs the message (including the reset link) instead of sending,
    # so the flow is testable without an SMTP server.
    SMTP_HOST: str = ""
    SMTP_PORT: int = 587
    SMTP_USERNAME: str = ""
    SMTP_PASSWORD: str = ""
    SMTP_FROM: str = "no-reply@localhost"
    SMTP_USE_TLS: bool = True

    # ── Push notifications (Expo Push → FCM/APNs) ────────────────────────────────
    # Staff order/waiter-call alerts delivered even when the app is closed. Dark by
    # default; flip EXPO_PUSH_ENABLED=true once FCM credentials are configured in
    # EAS. EXPO_ACCESS_TOKEN is optional (Expo "enhanced security"); keep it in .env.
    EXPO_PUSH_ENABLED: bool = False
    EXPO_PUSH_URL: str = "https://exp.host/--/api/v2/push/send"
    EXPO_ACCESS_TOKEN: str = ""


settings = Settings()
