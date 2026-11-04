"""
Ask PayHere what it knows about one donation order, and say whether the
backend would record it.

    cd backend
    python scripts/check_payhere_order.py VFF-XXXXXXXXXXXX 1000

The order id is the "Reference" on the thank-you page (also the gateway_ref
column in donations). The amount is optional; give it to see whether the
backend would accept the payment. Keys are read from backend/.env and are
never printed. Customer and card details in PayHere's answer are masked.
"""

import asyncio
import json
import os
import sys
from decimal import Decimal

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core import config  # noqa: E402
from app.services import payhere  # noqa: E402


def _mask(body):
    for p in body.get("data") or []:
        if isinstance(p, dict):
            p.pop("customer", None)
            p.pop("payment_method", None)
    return body


async def main() -> None:
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    order_id = sys.argv[1]

    print(f"PayHere mode:          {'sandbox' if config.PAYHERE_SANDBOX else 'LIVE'} ({config.PAYHERE_BASE_URL})")
    print(f"Merchant ID set:       {bool(config.PAYHERE_MERCHANT_ID)}")
    print(f"Merchant secret set:   {bool(config.PAYHERE_MERCHANT_SECRET)}")
    print(f"App ID / secret set:   {payhere.can_verify_orders()}")
    print()

    body = await payhere.search_order(order_id)
    print("PayHere answered:")
    print(json.dumps(_mask(body), indent=2, default=str))

    if len(sys.argv) > 2 and "error" not in body:
        amount = Decimal(sys.argv[2])
        ok = payhere.paid_in_full(body, order_id, amount)
        print()
        print(f"Would the backend record LKR {amount} for {order_id}? {'YES' if ok else 'NO'}")


if __name__ == "__main__":
    asyncio.run(main())
