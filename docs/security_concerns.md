Security Note: SlowAPI Rate Limiting Integration

Issue: SlowAPI requires a parameter named `request: Request` to identify the client and apply rate limits. Endpoints that used `request` as the body parameter name had to rename it (e.g., to `body`) so the actual HTTP Request object could be injected.

Concern 1: Rate limiting may not function correctly if the real `Request` object is unavailable, potentially allowing brute-force attacks, credential stuffing, order flooding, and abuse of public endpoints.

Solution: Ensure all rate-limited endpoints include `request: Request` and keep the JSON body as a separate parameter (e.g., `body: LoginRequest`). This preserves the API contract while enabling proper rate limiting.

Concern 2: When deployed behind reverse proxies (Cloudflare, Nginx, Railway, Render, AWS ALB, etc.), the application may see the proxy IP instead of the actual client IP. This can cause all users to share the same rate limit or make rate limiting ineffective.

Solution: Configure trusted proxy handling using ProxyHeadersMiddleware or a secure custom key function that reads `X-Forwarded-For` only from trusted proxies.

Concern 3: IP-based rate limiting alone can be bypassed using VPNs, residential proxies, or distributed botnets.

Solution: Combine IP limits with additional protections such as account-based rate limits, progressive backoff, CAPTCHA challenges after repeated failures, temporary account lockouts, and monitoring of suspicious activity patterns.

Performance Impact: Exposing the FastAPI `Request` object introduces negligible overhead compared to database operations, password hashing, JWT generation, and network latency. No meaningful performance degradation is expected.

Overall Assessment: This change does not alter frontend API contracts, has virtually no speed impact, and improves security by ensuring rate limiting functions as intended when properly configured.
