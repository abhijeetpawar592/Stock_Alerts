import yfinance as yf
import requests
import json
import os
from datetime import datetime, timedelta

# ─────────────────────────────────────────
#  YOUR SETTINGS — fill these in
# ─────────────────────────────────────────
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "8571728915:AAGrp2iMpEpOQ5skjrslln6dwpvX-C_V9io")
TELEGRAM_CHAT_ID   = os.environ.get("TELEGRAM_CHAT_ID",   "892193947")

# How many years back to check for breakout?
BREAKOUT_YEARS = [1, 3, 5]

# Volume must be this many times the 20-day average to count as a real breakout
VOLUME_MULTIPLIER = 1.5

# Alert when a stock is within this % of its 52-week HIGH or LOW
WEEK52_PROXIMITY_PCT = 5

# File to remember which stocks we already alerted today
NOTIFIED_FILE = "notified_today.json"

# ─────────────────────────────────────────
#  READ YOUR WATCHLIST
# ─────────────────────────────────────────
def load_watchlist():
    with open("watchlist.txt", "r") as f:
        stocks = [line.strip() for line in f if line.strip() and not line.startswith("#")]
    return stocks

# ─────────────────────────────────────────
#  SEND TELEGRAM MESSAGE
# ─────────────────────────────────────────
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=10)
        if r.status_code == 200:
            print(f"✅ Telegram sent: {message[:60]}...")
        else:
            print(f"❌ Telegram failed: {r.text}")
    except Exception as e:
        print(f"❌ Telegram error: {e}")

# ─────────────────────────────────────────
#  CHECK ONE STOCK FOR MULTI-YEAR BREAKOUTS
# ─────────────────────────────────────────
def check_stock(ticker):
    alerts = []
    try:
        data = yf.download(ticker, period="6y", interval="1d", progress=False, auto_adjust=True)
        if data.empty or len(data) < 30:
            print(f"  ⚠️  Not enough data for {ticker}")
            return alerts

        today_close  = float(data["Close"].iloc[-1])
        today_volume = float(data["Volume"].iloc[-1])
        avg_volume   = float(data["Volume"].iloc[-21:-1].mean())
        volume_ok    = today_volume >= (avg_volume * VOLUME_MULTIPLIER)
        volume_ratio = today_volume / avg_volume if avg_volume > 0 else 0

        for years in BREAKOUT_YEARS:
            cutoff     = datetime.today() - timedelta(days=365 * years)
            historical = data[data.index < data.index[-1]]
            historical = historical[historical.index >= cutoff]
            if historical.empty:
                continue
            period_high      = float(historical["Close"].max())
            period_high_date = historical["Close"].idxmax().strftime("%b %Y")
            if today_close > period_high and volume_ok:
                pct_above = ((today_close - period_high) / period_high) * 100
                alerts.append({
                    "ticker": ticker, "years": years,
                    "today_close": today_close, "period_high": period_high,
                    "period_high_date": period_high_date,
                    "volume_ratio": volume_ratio, "pct_above": pct_above
                })
                print(f"  🚀 BREAKOUT: {ticker} — {years}yr high! ₹{today_close:.2f}")
    except Exception as e:
        print(f"  ❌ Error checking {ticker}: {e}")
    return alerts

# ─────────────────────────────────────────
#  CHECK ONE STOCK FOR 52-WEEK PROXIMITY
# ─────────────────────────────────────────
def check_52week(ticker):
    alerts = []
    try:
        data = yf.download(ticker, period="13mo", interval="1d", progress=False, auto_adjust=True)
        if data.empty or len(data) < 50:
            return alerts

        today_close  = float(data["Close"].iloc[-1])
        today_volume = float(data["Volume"].iloc[-1])
        avg_volume   = float(data["Volume"].iloc[-21:-1].mean())
        volume_ratio = today_volume / avg_volume if avg_volume > 0 else 0

        past_year        = data.iloc[-253:-1]
        week52_high      = float(past_year["High"].max())
        week52_low       = float(past_year["Low"].min())
        week52_high_date = past_year["High"].idxmax().strftime("%d %b %Y")
        week52_low_date  = past_year["Low"].idxmin().strftime("%d %b %Y")

        pct_from_high = ((week52_high - today_close) / week52_high) * 100
        pct_from_low  = ((today_close - week52_low)  / week52_low)  * 100

        if 0 <= pct_from_high <= WEEK52_PROXIMITY_PCT:
            alerts.append({
                "ticker": ticker, "type": "NEAR_52W_HIGH",
                "today_close": today_close, "week52_high": week52_high,
                "week52_high_date": week52_high_date,
                "pct_from_high": pct_from_high, "volume_ratio": volume_ratio
            })
            print(f"  📈 NEAR 52W HIGH: {ticker} — {pct_from_high:.1f}% below ₹{week52_high:.2f}")

        if 0 <= pct_from_low <= WEEK52_PROXIMITY_PCT:
            alerts.append({
                "ticker": ticker, "type": "NEAR_52W_LOW",
                "today_close": today_close, "week52_low": week52_low,
                "week52_low_date": week52_low_date,
                "pct_from_low": pct_from_low, "volume_ratio": volume_ratio
            })
            print(f"  📉 NEAR 52W LOW: {ticker} — {pct_from_low:.1f}% above ₹{week52_low:.2f}")

    except Exception as e:
        print(f"  ❌ Error in 52w check for {ticker}: {e}")
    return alerts

# ─────────────────────────────────────────
#  COLLECT FULL STOCK DATA FOR DASHBOARD
# ─────────────────────────────────────────
def get_dashboard_row(ticker):
    """Returns a dict of all data needed for one dashboard row."""
    try:
        data = yf.download(ticker, period="6y", interval="1d", progress=False, auto_adjust=True)
        if data.empty or len(data) < 50:
            return None

        today_close  = float(data["Close"].iloc[-1])
        today_volume = float(data["Volume"].iloc[-1])
        avg_volume   = float(data["Volume"].iloc[-21:-1].mean())
        volume_ratio = today_volume / avg_volume if avg_volume > 0 else 0

        past_year    = data.iloc[-253:-1]
        week52_high  = float(past_year["High"].max())
        week52_low   = float(past_year["Low"].min())
        week52_high_date = past_year["High"].idxmax().strftime("%d %b %Y")
        week52_low_date  = past_year["Low"].idxmin().strftime("%d %b %Y")

        pct_from_high = ((week52_high - today_close) / week52_high) * 100
        pct_from_low  = ((today_close - week52_low)  / week52_low)  * 100

        # Check multi-year breakouts
        breakout_signals = []
        volume_ok = today_volume >= (avg_volume * VOLUME_MULTIPLIER)
        for years in BREAKOUT_YEARS:
            cutoff     = datetime.today() - timedelta(days=365 * years)
            historical = data[data.index < data.index[-1]]
            historical = historical[historical.index >= cutoff]
            if historical.empty:
                continue
            period_high = float(historical["Close"].max())
            if today_close > period_high and volume_ok:
                breakout_signals.append(f"{years}yr")

        # Previous close for day change %
        prev_close  = float(data["Close"].iloc[-2]) if len(data) > 1 else today_close
        day_change  = ((today_close - prev_close) / prev_close) * 100

        return {
            "ticker":           ticker,
            "price":            today_close,
            "day_change":       day_change,
            "week52_high":      week52_high,
            "week52_high_date": week52_high_date,
            "week52_low":       week52_low,
            "week52_low_date":  week52_low_date,
            "pct_from_high":    pct_from_high,
            "pct_from_low":     pct_from_low,
            "volume_ratio":     volume_ratio,
            "near_52w_high":    0 <= pct_from_high <= WEEK52_PROXIMITY_PCT,
            "near_52w_low":     0 <= pct_from_low  <= WEEK52_PROXIMITY_PCT,
            "vol_spike":        volume_ratio >= VOLUME_MULTIPLIER,
            "breakouts":        breakout_signals,
        }
    except Exception as e:
        print(f"  ❌ Dashboard row error for {ticker}: {e}")
        return None

# ─────────────────────────────────────────
#  BUILD THE HTML DASHBOARD FILE
# ─────────────────────────────────────────
def build_dashboard(rows):
    now = datetime.now().strftime("%a %d %b %Y, %I:%M %p IST")

    def signal_badges(row):
        badges = []
        if row["near_52w_high"]:
            badges.append('<span class="sig sig-green">&#x25B2; Near 52W high</span>')
        if row["near_52w_low"]:
            badges.append('<span class="sig sig-red">&#x25BC; Near 52W low</span>')
        if row["vol_spike"]:
            badges.append('<span class="sig sig-orange">&#x25CF; Vol spike</span>')
        for b in row["breakouts"]:
            badges.append(f'<span class="sig sig-blue">&#x2B50; {b} breakout</span>')
        if not badges:
            badges.append('<span class="sig sig-none">—</span>')
        return " ".join(badges)

    def fmt_pct(val, invert=False):
        color = "down" if (val > 0 and not invert) or (val < 0 and invert) else "up"
        sign  = "−" if val > 0 else "+"
        return f'<span class="{color}">{sign}{abs(val):.1f}%</span>'

    def fmt_day(val):
        color = "up" if val >= 0 else "down"
        sign  = "+" if val >= 0 else ""
        return f'<span class="{color}">{sign}{val:.2f}%</span>'

    table_rows = ""
    for row in rows:
        table_rows += f"""
        <tr>
          <td class="ticker">{row['ticker'].replace('.NS','').replace('.BO','')}<span class="exchange">{'.NS' if '.NS' in row['ticker'] else '.BO'}</span></td>
          <td>&#8377;{row['price']:,.2f}</td>
          <td>{fmt_day(row['day_change'])}</td>
          <td>&#8377;{row['week52_high']:,.2f}<div class="sub">{row['week52_high_date']}</div></td>
          <td>{fmt_pct(row['pct_from_high'])}</td>
          <td>&#8377;{row['week52_low']:,.2f}<div class="sub">{row['week52_low_date']}</div></td>
          <td>{fmt_pct(row['pct_from_low'], invert=True)}</td>
          <td>{'<span class="vol-high">' if row['vol_spike'] else ''}{row['volume_ratio']:.1f}x{'</span>' if row['vol_spike'] else ''}</td>
          <td>{signal_badges(row)}</td>
        </tr>"""

    alert_count = sum(1 for r in rows if r["near_52w_high"] or r["near_52w_low"] or r["vol_spike"] or r["breakouts"])

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Stock Dashboard</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
  :root {{
    --bg:       #ffffff;
    --bg2:      #f7f6f2;
    --bg3:      #f0ede7;
    --border:   rgba(0,0,0,0.10);
    --border2:  rgba(0,0,0,0.06);
    --text:     #1a1a18;
    --text2:    #5a5a55;
    --text3:    #9a9a94;
    --up:       #27500a;
    --down:     #a32d2d;
    --radius:   10px;
  }}
  @media (prefers-color-scheme: dark) {{
    :root {{
      --bg:     #18181a;
      --bg2:    #222224;
      --bg3:    #2a2a2c;
      --border: rgba(255,255,255,0.10);
      --border2:rgba(255,255,255,0.05);
      --text:   #e8e6df;
      --text2:  #9a9892;
      --text3:  #5a5a55;
      --up:     #7abf44;
      --down:   #e87070;
    }}
  }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: var(--bg); color: var(--text); font-size: 14px; padding: 24px 20px; }}
  .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 20px; flex-wrap: wrap; gap: 12px; }}
  h1 {{ font-size: 20px; font-weight: 600; }}
  .meta {{ font-size: 12px; color: var(--text3); margin-top: 4px; }}
  .stats {{ display: flex; gap: 12px; flex-wrap: wrap; }}
  .stat {{ background: var(--bg2); border: 0.5px solid var(--border); border-radius: var(--radius); padding: 10px 16px; text-align: center; min-width: 90px; }}
  .stat-num {{ font-size: 22px; font-weight: 600; }}
  .stat-label {{ font-size: 11px; color: var(--text3); margin-top: 2px; }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 14px; }}
  .leg {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text2); }}
  .leg-dot {{ width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }}
  .table-wrap {{ overflow-x: auto; border: 0.5px solid var(--border); border-radius: var(--radius); }}
  table {{ width: 100%; border-collapse: collapse; min-width: 750px; }}
  thead tr {{ background: var(--bg2); }}
  th {{ font-size: 11px; font-weight: 600; color: var(--text3); text-align: left; padding: 10px 14px; border-bottom: 0.5px solid var(--border); white-space: nowrap; text-transform: uppercase; letter-spacing: 0.04em; }}
  td {{ padding: 12px 14px; border-bottom: 0.5px solid var(--border2); vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--bg3); }}
  .ticker {{ font-weight: 600; font-size: 14px; white-space: nowrap; }}
  .exchange {{ font-size: 10px; color: var(--text3); font-weight: 400; margin-left: 2px; }}
  .sub {{ font-size: 10px; color: var(--text3); margin-top: 2px; }}
  .up {{ color: var(--up); font-weight: 500; }}
  .down {{ color: var(--down); font-weight: 500; }}
  .vol-high {{ color: #ba7517; font-weight: 600; }}
  .sig {{ display: inline-block; padding: 2px 8px; border-radius: 20px; font-size: 11px; font-weight: 500; margin: 2px 2px 2px 0; white-space: nowrap; }}
  .sig-green {{ background: #eaf3de; color: #27500a; }}
  .sig-red   {{ background: #fcebeb; color: #a32d2d; }}
  .sig-orange{{ background: #faeeda; color: #633806; }}
  .sig-blue  {{ background: #e6f1fb; color: #0c447c; }}
  .sig-none  {{ background: var(--bg2); color: var(--text3); border: 0.5px solid var(--border); }}
  @media (prefers-color-scheme: dark) {{
    .sig-green  {{ background: #1a3008; color: #7abf44; }}
    .sig-red    {{ background: #3a0f0f; color: #e87070; }}
    .sig-orange {{ background: #3a2000; color: #e09040; }}
    .sig-blue   {{ background: #0a2040; color: #60a8e8; }}
  }}
  footer {{ margin-top: 20px; font-size: 11px; color: var(--text3); text-align: center; }}
</style>
</head>
<body>

<div class="header">
  <div>
    <h1>Stock watchlist dashboard</h1>
    <div class="meta">Last updated: {now} &nbsp;·&nbsp; {len(rows)} stocks tracked</div>
  </div>
  <div class="stats">
    <div class="stat">
      <div class="stat-num">{len(rows)}</div>
      <div class="stat-label">Stocks</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:var(--up)">{sum(1 for r in rows if r['near_52w_high'])}</div>
      <div class="stat-label">Near 52W high</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:var(--down)">{sum(1 for r in rows if r['near_52w_low'])}</div>
      <div class="stat-label">Near 52W low</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:#ba7517">{sum(1 for r in rows if r['vol_spike'])}</div>
      <div class="stat-label">Vol spikes</div>
    </div>
    <div class="stat">
      <div class="stat-num" style="color:#0c447c">{sum(1 for r in rows if r['breakouts'])}</div>
      <div class="stat-label">Breakouts</div>
    </div>
  </div>
</div>

<div class="legend">
  <div class="leg"><div class="leg-dot" style="background:#639922"></div> Near 52W high (within {WEEK52_PROXIMITY_PCT}%)</div>
  <div class="leg"><div class="leg-dot" style="background:#e24b4a"></div> Near 52W low (within {WEEK52_PROXIMITY_PCT}%)</div>
  <div class="leg"><div class="leg-dot" style="background:#ef9f27"></div> Volume spike (&gt;{VOLUME_MULTIPLIER}x avg)</div>
  <div class="leg"><div class="leg-dot" style="background:#378add"></div> Multi-year breakout</div>
</div>

<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>Stock</th>
        <th>Price (&#8377;)</th>
        <th>Day change</th>
        <th>52W high</th>
        <th>% from high</th>
        <th>52W low</th>
        <th>% from low</th>
        <th>Volume</th>
        <th>Signals</th>
      </tr>
    </thead>
    <tbody>
      {table_rows}
    </tbody>
  </table>
</div>

<footer>Data from Yahoo Finance via yfinance &nbsp;·&nbsp; Auto-refreshed every weekday at 9:30 AM IST &nbsp;·&nbsp; Not financial advice</footer>

</body>
</html>"""

    with open("dashboard.html", "w", encoding="utf-8") as f:
        f.write(html)
    print(f"\n✅ Dashboard written → dashboard.html  ({len(rows)} stocks, {alert_count} with signals)")

# ─────────────────────────────────────────
#  LOAD / SAVE NOTIFIED LOG
# ─────────────────────────────────────────
def load_notified():
    today = datetime.today().strftime("%Y-%m-%d")
    if os.path.exists(NOTIFIED_FILE):
        with open(NOTIFIED_FILE, "r") as f:
            data = json.load(f)
        if data.get("date") == today:
            return set(data.get("tickers", []))
    return set()

def save_notified(notified_set):
    today = datetime.today().strftime("%Y-%m-%d")
    with open(NOTIFIED_FILE, "w") as f:
        json.dump({"date": today, "tickers": list(notified_set)}, f)

# ─────────────────────────────────────────
#  MAIN RUNNER
# ─────────────────────────────────────────
def main():
    print(f"\n{'='*50}")
    print(f"  Stock Alert Scanner — {datetime.today().strftime('%d %b %Y %H:%M')}")
    print(f"{'='*50}\n")

    stocks = load_watchlist()
    print(f"📋 Watching {len(stocks)} stocks: {', '.join(stocks)}\n")

    notified_today = load_notified()
    all_alerts     = []
    dashboard_rows = []

    for ticker in stocks:
        print(f"🔍 Checking {ticker}...")

        # ── Collect full data for dashboard (always, even if alerted today) ──
        row = get_dashboard_row(ticker)
        if row:
            dashboard_rows.append(row)

        # ── Telegram alerts (skip if already sent today) ──
        if ticker in notified_today:
            print(f"  ⏭️  Already alerted today, skipping Telegram.")
            continue
        alerts = check_stock(ticker)
        all_alerts.extend(alerts)
        week52_alerts = check_52week(ticker)
        all_alerts.extend(week52_alerts)

    # ── Always build the dashboard, even on no-alert days ──
    print("\n📊 Building dashboard...")
    build_dashboard(dashboard_rows)

    if not all_alerts:
        print("\n✅ No Telegram alerts today.")
        send_telegram(
            f"📊 <b>Daily Scan Complete</b>\n\n"
            f"No new alerts today.\n"
            f"Stocks scanned: {len(stocks)}\n\n"
            f"<i>Dashboard updated — check your GitHub Pages link.</i>"
        )
        return

    # ── Send one Telegram message per alert ──
    for alert in all_alerts:

        if "years" in alert:
            msg = (
                f"🚀 <b>BREAKOUT ALERT</b>\n\n"
                f"📌 <b>{alert['ticker']}</b>\n"
                f"📈 Hit a <b>{alert['years']}-year high!</b>\n\n"
                f"💰 Today's close:  ₹{alert['today_close']:.2f}\n"
                f"📊 Previous {alert['years']}yr high: ₹{alert['period_high']:.2f} ({alert['period_high_date']})\n"
                f"⬆️  Breaking out by: {alert['pct_above']:.1f}%\n"
                f"📦 Volume: {alert['volume_ratio']:.1f}x average\n\n"
                f"⚠️ <i>This is data only, not financial advice.</i>"
            )

        elif alert.get("type") == "NEAR_52W_HIGH":
            msg = (
                f"📈 <b>NEAR 52-WEEK HIGH</b>\n\n"
                f"📌 <b>{alert['ticker']}</b>\n"
                f"Only <b>{alert['pct_from_high']:.1f}% below</b> its 52-week high!\n\n"
                f"💰 Today's close:  ₹{alert['today_close']:.2f}\n"
                f"🏔 52-week high:   ₹{alert['week52_high']:.2f} (on {alert['week52_high_date']})\n"
                f"📦 Volume:         {alert['volume_ratio']:.1f}x average\n\n"
                f"💡 <i>Watch for breakout above ₹{alert['week52_high']:.2f}</i>\n"
                f"⚠️ <i>This is data only, not financial advice.</i>"
            )

        elif alert.get("type") == "NEAR_52W_LOW":
            msg = (
                f"📉 <b>NEAR 52-WEEK LOW</b>\n\n"
                f"📌 <b>{alert['ticker']}</b>\n"
                f"Only <b>{alert['pct_from_low']:.1f}% above</b> its 52-week low!\n\n"
                f"💰 Today's close:  ₹{alert['today_close']:.2f}\n"
                f"🪨 52-week low:    ₹{alert['week52_low']:.2f} (on {alert['week52_low_date']})\n"
                f"📦 Volume:         {alert['volume_ratio']:.1f}x average\n\n"
                f"💡 <i>Key support zone — watch for bounce or breakdown</i>\n"
                f"⚠️ <i>This is data only, not financial advice.</i>"
            )

        else:
            continue

        send_telegram(msg)
        notified_today.add(alert["ticker"])

    save_notified(notified_today)
    print(f"\n✅ Done. {len(all_alerts)} Telegram alert(s) sent.")

if __name__ == "__main__":
    main()
