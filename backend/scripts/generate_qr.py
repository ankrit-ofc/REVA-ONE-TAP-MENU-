"""
Dev helper — generate a signed QR token for a given restaurant_id + table_id.

Run inside the backend container:
    docker compose exec backend python scripts/generate_qr.py <restaurant_id> <table_id>

Example:
    docker compose exec backend python scripts/generate_qr.py \
        11111111-1111-1111-1111-111111111111 \
        22222222-2222-2222-2222-222222222222

Output:
    QR token  : ImV5Si4uLiJ9.abc123...
    Scan body : {"qr_token": "ImV5Si4uLiJ9.abc123..."}
    curl      : curl -s -X POST http://localhost:8000/scan \
                  -H 'Content-Type: application/json' \
                  -d '{"qr_token":"ImV5Si4uLiJ9.abc123..."}'
"""
import sys

from app.core.qr import sign_qr


def main() -> None:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <restaurant_id> <table_id>", file=sys.stderr)
        sys.exit(1)

    restaurant_id = sys.argv[1]
    table_id = sys.argv[2]

    token = sign_qr(restaurant_id, table_id)

    print(f"QR token  : {token}")
    print(f'Scan body : {{"qr_token": "{token}"}}')
    print(
        f"curl      : curl -s -X POST http://localhost:8000/scan"
        f" -H 'Content-Type: application/json'"
        f" -d '{{\"qr_token\":\"{token}\"}}'"
    )


if __name__ == "__main__":
    main()
