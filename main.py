#!/usr/bin/env python3
"""
Kalshi Last-Second Buyer — BTC 15-min markets, LIVE TRADING.
Watches both YES and NO ask. The moment either hits 98c-99c, buys.
No model, no filters — pure price-based.
"""

import sys
import time
import uuid
import base64
import datetime
import requests
import math
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding

# ── Credentials ───────────────────────────────────────────────────────────────

KALSHI_API_KEY_ID  = "e5affd60-2ed2-47d4-9b6a-f9b8a431ccc9"
KALSHI_PRIVATE_KEY = b"""-----BEGIN RSA PRIVATE KEY-----
MIIEpAIBAAKCAQEAxAQ8fEVq9tVUf8wNkp9itEI4uNApkw5fO2l+RttWgZy8ds4q
NS0vfQVSXMbJ/fPS66UYZpW4D4zXrFmS5LW/QMEe4CQVGcDUUhJsuU6e8JDk3xuy
bKGdn8o3z7L26O06/noa6ZO7qr4j5j1DCuDofKp4S+M0jWVwMdwlPLBA2CaxaQhX
rFkj3dgN6lnGsUnRHPju7hhtRa8XmCvQawQCCECRnqOaN3SPB66pugGz2NjqF7Jr
teiNJ88QIk5ezmcHOojMd1+Y2JDxpr8MCdVuPL30LreZdNvqoDuD/LSsLgFXsdDX
DOhPdC2rpuVhHefcRSIer4WUCiPdh9aCpja9jQIDAQABAoIBAA2cFwWwiDG6iX2/
ZuiERS/WMpFacAM0NJaFHO3B3ZVtktmo4jNY/3rDENSSP4TGFiH4ZOOn3OTE1wCy
I3SFI1IAAVXMtjkDM3q9/sCLCJa+vgq4+0AhpIvArZ6v2AbqLyDAzPePeLCX4m7i
WAenAAgP31RdjSY4IdHEbZgeIL0hK0OzxcGJJH/nPvsNxkl8Abk+AmQmI8QqMBzu
IRslFmf1G99nvdgdCBTDh8ovG/khuPHNiYVa5cKmspvdB4xpWRmNvRx5ZnCIFfEq
ERwsELrKLGP99V3RknD1MuT2zKCbH8TWr06GgNiZoEtajeCOk7tqRU8qE0Naot6f
ghnONp0CgYEA/rdNlK3r1AVaADjc2R7m9eq+TdZTucrNRvrVSGKm6cLgK1t+YWVS
cqjvzKE5x8PqFFMUqlm2WMxtaBOWtPAt/aJMkyVm9+ljposFf664xw9185MAVCLr
v7hL7zfH2tUSTAq14JH2kkeIWYvjbS92JLaDh4cVap9l86JNR1WNOAMCgYEAxQEv
TktIiO2Hb8ZC9iChpiXsViVo2kgx21Dnsql69Nf6mQ322Zmn1DgixLI5sGVAVQkF
AtCcePGub6wrwp3BTpfeiHJd4c4yr7lTg/DnFKXB3osLHW0AoxWQXFTpIKteOx6E
2p6y1qxFtD39qgTPWrERqClREE0PqkCeLQHrJy8CgYEAhkkvLn5OwTWdEFbqH9GJ
5AZBFBo1g9LmTFB7VzEjXEQwGMugokpfoDFuUwyAwM+JvfNbBsBLQR9tYpxJLNUe
+gOxqTXjxjmWHrxWRs1ffxqojaRnXPQYI7hO2CwpQjZo8gwHfQCW5OGvgb4dRXfr
KknKqA3QfajRgBOF+GCjFe8CgYB6IxToDoaG1fSM2Lc1DuAJOSO/+Ot7wRyf4xXy
z146pBhqgZzUJY5GZRMxLWnUscFjtvbTWvBXj0bdVzm+K73n8wH1SCpqT0NfbJ+Z
gmZRh76dMUkP0j993GWmyMHMDlKahn5JZ/BqZV3FtFUq7lZ73KGcxxjJ6WzX2b33
G2Rl4wKBgQDEbWnKIt812mTnezKSMIDckjEwBE2wq91TZPUYiD2gjuKGGbJLUO06
dsMDC6kWKX8LiSU9wZyfxeFPArhlIGhKhowqlUomQasoYta8aERzqz21nO5uz8+q
cRoPtSg0YM0S1OEMespJ/VVfazh8ggpcya3hvrPEYeFaBPcii/Pqog==
-----END RSA PRIVATE KEY-----"""

# ── Config ────────────────────────────────────────────────────────────────────
 
BASE_URL         = "https://api.elections.kalshi.com"
LOG_FILE         = "last_second_live.txt"
 
BUY_MIN_CENTS    = 98     # buy if ask >= this
BUY_MAX_CENTS    = 100    # buy if ask <  this (skip $1.00 — no margin)
BET_DOLLARS      = 30     # dollars to risk per trade
BALANCE_FLOOR    = 140.0  # halt if balance at or below this
 
WATCH_SECS_WEEKDAY  = 420  # 7 minutes on Mon–Fri
WATCH_SECS_WEEKEND  = 300  # 5 minutes on Sat–Sun
MARKET_MIN_SECS     = 60   # ignore markets closing in less than this
POLL_MS             = 0.5  # seconds between price checks
 
# ── State ─────────────────────────────────────────────────────────────────────
 
trades_won  = 0
trades_lost = 0
 
# ── Helpers ───────────────────────────────────────────────────────────────────
 
def get_watch_secs() -> int:
    """Return watch window in seconds: 7 min on weekdays, 5 min on weekends."""
    is_weekday = datetime.datetime.now().weekday() < 5  # 0=Mon, 4=Fri
    return WATCH_SECS_WEEKDAY if is_weekday else WATCH_SECS_WEEKEND
 
def day_mode() -> str:
    return "weekday (7min)" if datetime.datetime.now().weekday() < 5 else "weekend (5min)"
 
# ── Logging ───────────────────────────────────────────────────────────────────
 
def log(msg: str):
    ts   = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a") as f:
        f.write(line + "\n")
 
# ── Auth ──────────────────────────────────────────────────────────────────────
 
def _auth(method: str, path: str) -> dict:
    key = serialization.load_pem_private_key(KALSHI_PRIVATE_KEY, password=None)
    ts  = str(int(time.time() * 1000))
    msg = f"{ts}{method.upper()}{path}".encode()
    sig = base64.b64encode(
        key.sign(msg, asym_padding.PSS(
            mgf=asym_padding.MGF1(hashes.SHA256()),
            salt_length=asym_padding.PSS.MAX_LENGTH,
        ), hashes.SHA256())
    ).decode()
    return {
        "Content-Type":            "application/json",
        "KALSHI-ACCESS-KEY":       KALSHI_API_KEY_ID,
        "KALSHI-ACCESS-TIMESTAMP": ts,
        "KALSHI-ACCESS-SIGNATURE": sig,
    }
 
def api_get(path: str, params: dict = None, auth: bool = False) -> dict:
    headers = _auth("GET", path) if auth else {"accept": "application/json"}
    r = requests.get(f"{BASE_URL}{path}", params=params or {},
                     headers=headers, timeout=8)
    r.raise_for_status()
    return r.json()
 
# ── Balance ───────────────────────────────────────────────────────────────────
 
def get_balance() -> float:
    path = "/trade-api/v2/portfolio/balance"
    return api_get(path, auth=True).get("balance", 0) / 100
 
# ── BTC series + market ───────────────────────────────────────────────────────
 
def find_btc_series() -> str:
    data = api_get("/trade-api/v2/series/", params={"limit": 200})
    for s in (data.get("series") or []):
        if "btc15m" in (s.get("ticker") or "").lower():
            return s["ticker"]
    raise ValueError("BTC 15-min series not found")
 
def get_current_btc_market(series_ticker: str) -> dict | None:
    data    = api_get("/trade-api/v2/markets/",
                      params={"series_ticker": series_ticker,
                              "status": "open", "limit": 100})
    now     = datetime.datetime.now(datetime.timezone.utc)
    valid   = []
    for m in data.get("markets", []):
        ct = m.get("close_time")
        if not ct:
            continue
        close_dt  = datetime.datetime.fromisoformat(ct.replace("Z", "+00:00"))
        secs_left = (close_dt - now).total_seconds()
        if secs_left >= MARKET_MIN_SECS:
            valid.append((secs_left, m))
    if not valid:
        return None
    valid.sort(key=lambda x: x[0])
    return valid[0][1]
 
def secs_to_close(market: dict) -> float:
    ct = datetime.datetime.fromisoformat(
        market["close_time"].replace("Z", "+00:00"))
    return (ct - datetime.datetime.now(datetime.timezone.utc)).total_seconds()
 
def get_prices(ticker: str) -> dict | None:
    try:
        m  = api_get(f"/trade-api/v2/markets/{ticker}").get("market", {})
        ya = m.get("yes_ask_dollars")
        na = m.get("no_ask_dollars")
        if ya is None and na is None:
            return None
        return {
            "yes_ask": float(ya) if ya is not None else None,
            "no_ask":  float(na) if na is not None else None,
        }
    except Exception as e:
        log(f"  price fetch error: {e}")
        return None
 
# ── Order placement ───────────────────────────────────────────────────────────
 
def place_order(ticker: str, side: str, ask: float) -> bool:
    try:
        balance = get_balance()
        log(f"  Balance: ${balance:,.2f}")
        if balance <= BALANCE_FLOOR:
            log(f"  HALT — balance ${balance:.2f} at floor ${BALANCE_FLOOR:.2f}. Shutting down.")
            sys.exit(1)
    except Exception as e:
        log(f"  Could not verify balance: {e} — skipping order")
        return False
 
    price_cents   = round(ask * 100)
    contracts     = (BET_DOLLARS * 100) // price_cents
    cost          = round(contracts * price_cents / 100, 2)
    profit_if_win = round(float(contracts) - cost, 2)
    fee           = math.ceil(0.07 * contracts * ask * (1 - ask) * 100) / 100
 
    if contracts < 1:
        log(f"  SKIP — not enough funds for 1 contract at {price_cents}¢")
        return False
 
    path    = "/trade-api/v2/portfolio/orders"
    payload = {
        "ticker":          ticker,
        "client_order_id": str(uuid.uuid4()),
        "action":          "buy",
        "side":            side,
        "type":            "limit",
        "count":           int(contracts),
        "yes_price":       price_cents if side == "yes" else (100 - price_cents),
    }
 
    try:
        r = requests.post(f"{BASE_URL}{path}",
                          headers=_auth("POST", path),
                          json=payload, timeout=8)
        if r.status_code == 201:
            order = r.json().get("order", {})
            log(f"  ✅ ORDER PLACED — {side.upper()} x{contracts} @ {price_cents}¢  "
                f"cost=${cost:.2f}  fee=${fee:.2f}  "
                f"net profit if win=${profit_if_win - fee:.2f}  "
                f"order_id={order.get('order_id','?')}  "
                f"status={order.get('status','?')}")
            return True
        else:
            log(f"  ❌ ORDER FAILED — HTTP {r.status_code}: {r.text[:200]}")
            return False
    except Exception as e:
        log(f"  ❌ ORDER EXCEPTION — {e}")
        return False
 
# ── Result checker ────────────────────────────────────────────────────────────
 
def _check_result(ticker: str, side: str):
    global trades_won, trades_lost
    log(f"  Waiting for result on {ticker}…")
    for _ in range(24):
        time.sleep(15)
        try:
            m      = api_get(f"/trade-api/v2/markets/{ticker}").get("market", {})
            result = m.get("result", "")
            if result in ("yes", "no"):
                won = (result == side)
                if won:
                    trades_won += 1
                    log(f"  ✅ WIN — result={result}  record={trades_won}W/{trades_lost}L")
                else:
                    trades_lost += 1
                    log(f"  ❌ LOSS — result={result}  record={trades_won}W/{trades_lost}L")
                    log(f"  🛑 STOPPING — auto-stop triggered after first loss.")
                    sys.exit(1)
                return
        except Exception as e:
            log(f"  result fetch error: {e}")
    log(f"  ⚠ Could not determine result for {ticker} after 6 min — continuing")
 
# ── Main ──────────────────────────────────────────────────────────────────────
 
def main():
    log("=" * 60)
    log(f"Last-Second Buyer — BTC 15-min  LIVE TRADING")
    log(f"Buy: {BUY_MIN_CENTS}¢–{BUY_MAX_CENTS-1}¢  |  "
        f"Price-triggered  |  Bet: ${BET_DOLLARS}  |  "
        f"Floor: ${BALANCE_FLOOR}  |  "
        f"Watch: {WATCH_SECS_WEEKDAY}s weekdays / {WATCH_SECS_WEEKEND}s weekends")
    log("=" * 60)
 
    try:
        bal = get_balance()
        log(f"Opening balance: ${bal:,.2f}")
        if bal <= BALANCE_FLOOR:
            log("ABORT — balance already at floor.")
            sys.exit(1)
    except Exception as e:
        log(f"ABORT — could not fetch balance: {e}")
        sys.exit(1)
 
    try:
        series_ticker = find_btc_series()
        log(f"BTC series: {series_ticker}")
    except Exception as e:
        log(f"ABORT — {e}")
        sys.exit(1)
 
    fired_tickers = set()
 
    try:
        while True:
            market = get_current_btc_market(series_ticker)
 
            if market is None:
                log("No open BTC market — retrying in 30s")
                time.sleep(30)
                continue
 
            ticker    = market["ticker"]
            secs_left = secs_to_close(market)
            strike    = market.get("floor_strike", "?")
 
            if ticker in fired_tickers:
                wait = max(secs_left - 5, 5)
                log(f"Already fired {ticker} — sleeping {wait:.0f}s for next market")
                time.sleep(wait)
                continue
 
            log(f"Market: {ticker}  strike=${strike}  closes in {secs_left:.0f}s")
 
            # Determine watch window based on weekday/weekend
            watch_secs = get_watch_secs()
            wait       = secs_left - watch_secs
            if wait > 0:
                log(f"Sleeping {wait:.0f}s until watch window [{day_mode()}]")
                time.sleep(wait)
 
            # Price-triggered loop
            log(f"Watching — trigger: {BUY_MIN_CENTS}¢–{BUY_MAX_CENTS-1}¢ on YES or NO")
            last_logged = None
            while True:
                secs_left = secs_to_close(market)
 
                if secs_left < 0:
                    log("  Market closed without trigger — moving on")
                    fired_tickers.add(ticker)
                    break
 
                prices = get_prices(ticker)
                if prices:
                    ya = prices["yes_ask"]
                    na = prices["no_ask"]
                    ya_cents = round(ya * 100) if ya else None
                    na_cents = round(na * 100) if na else None
                    display  = f"YES={ya_cents}¢  NO={na_cents}¢"
 
                    if display != last_logged:
                        log(f"  👁 T-{secs_left:.0f}s — {display}")
                        last_logged = display
 
                    if ya_cents and BUY_MIN_CENTS <= ya_cents < BUY_MAX_CENTS:
                        log(f"  ⚡ TRIGGER YES — {ya_cents}¢ at T-{secs_left:.0f}s")
                        place_order(ticker, "yes", ya)
                        fired_tickers.add(ticker)
                        _check_result(ticker, "yes")
                        break
 
                    if na_cents and BUY_MIN_CENTS <= na_cents < BUY_MAX_CENTS:
                        log(f"  ⚡ TRIGGER NO — {na_cents}¢ at T-{secs_left:.0f}s")
                        place_order(ticker, "no", na)
                        fired_tickers.add(ticker)
                        _check_result(ticker, "no")
                        break
 
                    if (ya_cents and ya_cents >= BUY_MAX_CENTS) or \
                       (na_cents and na_cents >= BUY_MAX_CENTS):
                        log(f"  ⚡ MISSED — jumped to 100¢, no fill")
                        fired_tickers.add(ticker)
                        break
 
                time.sleep(POLL_MS)
 
    except KeyboardInterrupt:
        log("Stopped by user.")
 
if __name__ == "__main__":
    main()
