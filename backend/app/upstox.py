import os, httpx, urllib.parse
from .config import (
    UPSTOX_CLIENT_ID, UPSTOX_CLIENT_SECRET, UPSTOX_REDIRECT_URI,
    UPSTOX_ACCESS_TOKEN, UPSTOX_MODE, UPSTOX_SANDBOX_TOKEN
)

class UpstoxClient:
    AUTH = "https://api.upstox.com/v2"
    LIVE_ORDERS = "https://api-hft.upstox.com/v3"
    SANDBOX_ORDERS = "https://sandbox.upstox.com/v3"

    def login_url(self, state: str):
        if not UPSTOX_CLIENT_ID:
            raise RuntimeError("Set UPSTOX_CLIENT_ID first.")
        params = {
            "client_id": UPSTOX_CLIENT_ID,
            "redirect_uri": UPSTOX_REDIRECT_URI,
            "response_type": "code",
            "state": state,
        }
        return "https://api.upstox.com/v2/login/authorization/dialog?" + urllib.parse.urlencode(params)

    async def exchange_code(self, code: str):
        data = {
            "code": code, "client_id": UPSTOX_CLIENT_ID,
            "client_secret": UPSTOX_CLIENT_SECRET,
            "redirect_uri": UPSTOX_REDIRECT_URI,
            "grant_type": "authorization_code",
        }
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(f"{self.AUTH}/login/authorization/token", data=data,
                                  headers={"Accept":"application/json"})
            r.raise_for_status()
            return r.json()

    def token(self):
        if UPSTOX_MODE == "sandbox":
            if not UPSTOX_SANDBOX_TOKEN:
                raise RuntimeError("Set UPSTOX_SANDBOX_TOKEN for sandbox API calls.")
            return UPSTOX_SANDBOX_TOKEN
        if not UPSTOX_ACCESS_TOKEN:
            raise RuntimeError("Set UPSTOX_ACCESS_TOKEN. Do not paste it into chat.")
        return UPSTOX_ACCESS_TOKEN

    async def place_order(self, order: dict, sandbox: bool = True):
        base = self.SANDBOX_ORDERS if sandbox else self.LIVE_ORDERS
        payload = {
            "quantity": order["quantity"],
            "product": order["product"],
            "validity": "DAY",
            "price": order.get("limit_price", 0),
            "tag": order["tag"][:20],
            "instrument_token": order["instrument_token"],
            "order_type": order.get("order_type", "LIMIT"),
            "transaction_type": order["side"],
            "disclosed_quantity": 0,
            "trigger_price": order.get("trigger_price", 0),
            "is_amo": False,
            "slice": False,
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(f"{base}/order/place", json=payload,
                headers={"Authorization": f"Bearer {self.token()}",
                         "Accept":"application/json","Content-Type":"application/json"})
            r.raise_for_status()
            return r.json()
