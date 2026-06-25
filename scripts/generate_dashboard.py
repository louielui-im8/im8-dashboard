#!/usr/bin/env python3
"""
IM8 Meta Ads Dashboard Generator
Pulls live data from Meta Ads API and generates im8-dashboard.html
"""

import os
import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta, timezone

# ── Config ────────────────────────────────────────────────────────────────────
TOKEN = os.environ["META_ACCESS_TOKEN"]
AD_ACCOUNT = "act_1000723654649396"
BASE_URL = "https://graph.facebook.com/v19.0"
AOV = 232  # NC AOV from Shopify L30D: $13.16M / 56,599 orders
CAC_TARGET = 300
REVENUE_TARGET_DAILY = 250000
KEY_COUNTRIES = ["US", "GB", "AU", "CA"]

# ── Helpers ───────────────────────────────────────────────────────────────────
def api(path, params):
    params["access_token"] = TOKEN
    url = f"{BASE_URL}/{path}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as r:
        return json.loads(r.read())

def api_all_pages(path, params):
    """Fetch all pages of a paginated API response."""
    result = api(path, params)
    all_data = list(result.get("data", []))
    while True:
        next_url = result.get("paging", {}).get("next")
        if not next_url:
            break
        with urllib.request.urlopen(next_url, timeout=30) as r:
            result = json.loads(r.read())
        all_data.extend(result.get("data", []))
    return {"data": all_data}

def fmt_currency(n):
    if n >= 1_000_000:
        return f"${n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"${n/1_000:.1f}K"
    return f"${n:,.0f}"

def fmt_num(n):
    return f"{n:,.0f}"

def cac_class(cac):
    if cac < CAC_TARGET: return "green"
    if cac <= 350: return "orange"
    return "red"

def roas_class(roas):
    if roas >= 1.0: return "green"
    if roas >= 0.71: return "orange"
    return "red"

def roas_val(spend, purchases):
    if purchases == 0: return 0
    return (purchases * AOV) / spend

# ── Date ranges ───────────────────────────────────────────────────────────────
today = datetime.now(timezone.utc).date()
l7d_end   = today - timedelta(days=1)
l7d_start = l7d_end - timedelta(days=6)
prior_end   = l7d_start - timedelta(days=1)
prior_start = prior_end - timedelta(days=6)
mtd_start = today.replace(day=1)

L7D_SINCE  = l7d_start.strftime("%Y-%m-%d")
L7D_UNTIL  = l7d_end.strftime("%Y-%m-%d")
PRIOR_SINCE = prior_start.strftime("%Y-%m-%d")
PRIOR_UNTIL = prior_end.strftime("%Y-%m-%d")
MTD_SINCE  = mtd_start.strftime("%Y-%m-%d")
MTD_UNTIL  = l7d_end.strftime("%Y-%m-%d")

# ── Fetch data ────────────────────────────────────────────────────────────────
print("Fetching L7D summary...")
l7d = api(f"{AD_ACCOUNT}/insights", {
    "time_range": json.dumps({"since": L7D_SINCE, "until": L7D_UNTIL}),
    "fields": "spend,actions,action_values",
    "level": "account"
})

print("Fetching prior week summary...")
prior = api(f"{AD_ACCOUNT}/insights", {
    "time_range": json.dumps({"since": PRIOR_SINCE, "until": PRIOR_UNTIL}),
    "fields": "spend,actions,action_values",
    "level": "account"
})

print("Fetching daily trend L7D...")
daily_l7d = api(f"{AD_ACCOUNT}/insights", {
    "time_range": json.dumps({"since": L7D_SINCE, "until": L7D_UNTIL}),
    "fields": "spend,actions,date_start",
    "time_increment": 1,
    "level": "account"
})

print("Fetching daily trend prior...")
daily_prior = api(f"{AD_ACCOUNT}/insights", {
    "time_range": json.dumps({"since": PRIOR_SINCE, "until": PRIOR_UNTIL}),
    "fields": "spend,actions,date_start",
    "time_increment": 1,
    "level": "account"
})

print("Fetching country breakdown L7D...")
countries = api_all_pages(f"{AD_ACCOUNT}/insights", {
    "time_range": json.dumps({"since": L7D_SINCE, "until": L7D_UNTIL}),
    "fields": "spend,actions",
    "breakdowns": "country",
    "limit": 100
})

print("Fetching campaign performance L7D...")
campaigns = api(f"{AD_ACCOUNT}/insights", {
    "time_range": json.dumps({"since": L7D_SINCE, "until": L7D_UNTIL}),
    "fields": "campaign_name,spend,actions",
    "level": "campaign",
    "limit": 50
})

print("Fetching MTD summary...")
mtd = api(f"{AD_ACCOUNT}/insights", {
    "time_range": json.dumps({"since": MTD_SINCE, "until": MTD_UNTIL}),
    "fields": "spend,actions",
    "level": "account"
})

# ── Parse helpers ─────────────────────────────────────────────────────────────
def get_purchases(data_item):
    for a in data_item.get("actions", []):
        if a["action_type"] == "omni_purchase":
            return float(a["value"])
    return 0

def parse_summary(data):
    if not data.get("data"): return {"spend": 0, "purchases": 0}
    d = data["data"][0]
    return {"spend": float(d.get("spend", 0)), "purchases": get_purchases(d)}

def parse_daily(data):
    out = {}
    for d in data.get("data", []):
        out[d["date_start"]] = {
            "spend": float(d.get("spend", 0)),
            "purchases": get_purchases(d)
        }
    return out

# ── Compute KPIs ──────────────────────────────────────────────────────────────
s = parse_summary(l7d)
p = parse_summary(prior)

spend_l7d     = s["spend"]
purchases_l7d = s["purchases"]
spend_prior   = p["spend"]
purchases_prior = p["purchases"]

cac_l7d   = spend_l7d / purchases_l7d if purchases_l7d else 0
cac_prior = spend_prior / purchases_prior if purchases_prior else 0
roas_l7d  = roas_val(spend_l7d, purchases_l7d)
rev_l7d   = purchases_l7d * AOV

mtd_s = parse_summary(mtd)
mtd_purchases = mtd_s["purchases"]
mtd_revenue   = mtd_purchases * AOV
days_elapsed  = (today - mtd_start).days
mtd_target    = days_elapsed * REVENUE_TARGET_DAILY
pacing_pct    = (mtd_revenue / mtd_target * 100) if mtd_target else 0

# ── Daily chart data ──────────────────────────────────────────────────────────
dl7d  = parse_daily(daily_l7d)
dprior = parse_daily(daily_prior)

l7d_dates = sorted(dl7d.keys())
prior_dates = sorted(dprior.keys())

chart_labels     = [datetime.strptime(d, "%Y-%m-%d").strftime("%b %d") for d in l7d_dates]
chart_spend_l7d  = [round(dl7d[d]["spend"]) for d in l7d_dates]
chart_spend_prior = [round(dprior[d]["spend"]) for d in prior_dates]
chart_cac_l7d    = [round(dl7d[d]["spend"] / dl7d[d]["purchases"]) if dl7d[d]["purchases"] > 0 else 0 for d in l7d_dates]
chart_purchases_l7d  = [round(dl7d[d]["purchases"]) for d in l7d_dates]
chart_purchases_prior = [round(dprior[d]["purchases"]) for d in prior_dates]
chart_rev_l7d    = [round(dl7d[d]["purchases"] * AOV) for d in l7d_dates]

# ── Country data ──────────────────────────────────────────────────────────────
country_data = {}
for d in countries.get("data", []):
    c = d.get("country", "")
    spend = float(d.get("spend", 0))
    purchases = get_purchases(d)
    country_data[c] = {"spend": spend, "purchases": purchases,
                       "cac": spend / purchases if purchases else 0,
                       "roas": roas_val(spend, purchases)}

# ── Campaign data ─────────────────────────────────────────────────────────────
campaign_list = []
for d in campaigns.get("data", []):
    spend = float(d.get("spend", 0))
    purchases = get_purchases(d)
    cac = spend / purchases if purchases else 0
    campaign_list.append({
        "name": d.get("campaign_name", ""),
        "spend": spend,
        "purchases": purchases,
        "cac": cac,
        "roas": roas_val(spend, purchases)
    })

campaign_list.sort(key=lambda x: x["cac"] if x["cac"] > 0 else 999999)
cut_list   = [c for c in campaign_list if c["cac"] > 600 and c["purchases"] > 0]
watch_list = [c for c in campaign_list if 350 < c["cac"] <= 600 and c["purchases"] > 0]
win_list   = [c for c in campaign_list if 0 < c["cac"] <= 300 and c["purchases"] > 0]

# ── Build HTML ────────────────────────────────────────────────────────────────
updated_at = datetime.now(timezone.utc).strftime("%b %d, %Y %H:%M UTC")

def country_card(code, flag, name):
    cd = country_data.get(code, {"spend": 0, "purchases": 0, "cac": 0, "roas": 0})
    border = cac_class(cd["cac"])
    roas = cd["roas"]
    roas_cls = roas_class(roas)
    cac_display = f"${cd['cac']:,.0f}" if cd["cac"] else "N/A"
    return f"""
    <div class="country-card border-{border}">
      <div class="country-name"><span class="country-flag">{flag}</span>{name}</div>
      <div class="country-stat">
        <span class="stat-label">Spend</span>
        <span class="stat-value">{fmt_currency(cd['spend'])}</span>
      </div>
      <div class="country-stat">
        <span class="stat-label">Purchases</span>
        <span class="stat-value">{fmt_num(cd['purchases'])}</span>
      </div>
      <div class="country-stat">
        <span class="stat-label">CAC</span>
        <span class="stat-value {cac_class(cd['cac'])}">{cac_display}</span>
      </div>
      <div class="country-stat">
        <span class="stat-label">Est. ROAS</span>
        <span class="roas-badge {roas_cls}">{roas:.2f}x</span>
      </div>
    </div>"""

def campaign_rows(items, limit=10):
    rows = ""
    for c in items[:limit]:
        cac_cls = cac_class(c["cac"])
        roas_cls = roas_class(c["roas"])
        rows += f"""
        <tr>
          <td><span class="campaign-name">{c['name']}</span></td>
          <td>{fmt_currency(c['spend'])}</td>
          <td>{fmt_num(c['purchases'])}</td>
          <td><span class="cpp-pill {cac_cls}">${c['cac']:,.0f}</span></td>
          <td><span class="roas-badge {roas_cls}">{c['roas']:.2f}x</span></td>
        </tr>"""
    return rows or "<tr><td colspan='5' class='empty-state'>No campaigns</td></tr>"

pacing_cls = "green" if pacing_pct >= 100 else "orange"
spend_delta = spend_l7d - spend_prior
spend_dir = "up" if spend_delta >= 0 else "down"
spend_arrow = "▲" if spend_delta >= 0 else "▼"
pur_delta = purchases_l7d - purchases_prior
pur_dir = "up" if pur_delta >= 0 else "down"
pur_arrow = "▲" if pur_delta >= 0 else "▼"

html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>IM8 Meta Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #111214; --surface: #1a1c20; --surface2: #22252b;
    --border: #2e3138; --border2: #363a44;
    --text: #f0eeea; --text-muted: #7a7f8c;
    --gold: #d4a843; --gold-dim: #a07c2e; --gold-bg: #1e1810;
    --green: #34d399; --green-bg: #0a2218;
    --orange: #fb923c; --orange-bg: #1e1208;
    --red: #f87171; --red-bg: #200a0a;
  }}
  * {{ margin: 0; padding: 0; box-sizing: border-box; }}
  body {{ background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; font-size: 14px; }}
  .header {{ background: var(--surface); border-bottom: 1px solid var(--border); padding: 14px 24px; display: flex; align-items: center; justify-content: space-between; position: sticky; top: 0; z-index: 100; }}
  .header h1 {{ font-size: 18px; font-weight: 700; color: var(--text); letter-spacing: -0.02em; }}
  .meta-badge {{ background: var(--gold-bg); color: var(--gold); border: 1px solid var(--gold-dim); font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 4px; margin-left: 8px; }}
  .header-right {{ display: flex; align-items: center; gap: 16px; }}
  .period-label, .last-updated {{ color: var(--text-muted); font-size: 12px; }}
  .refresh-btn {{ background: var(--gold-bg); color: var(--gold); border: 1px solid var(--gold-dim); font-size: 12px; font-weight: 600; padding: 5px 12px; border-radius: 6px; cursor: pointer; }}
  .refresh-btn:hover {{ background: var(--gold-dim); color: #fff; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
  .section-title {{ font-size: 11px; font-weight: 700; color: var(--gold); text-transform: uppercase; letter-spacing: 0.1em; margin-bottom: 12px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; margin-bottom: 24px; }}
  .kpi-card {{ background: var(--surface); border: 1px solid var(--border); border-top: 2px solid var(--border2); border-radius: 10px; padding: 16px 20px; }}
  .kpi-label {{ font-size: 11px; color: var(--text-muted); font-weight: 600; text-transform: uppercase; letter-spacing: 0.06em; margin-bottom: 6px; }}
  .kpi-value {{ font-size: 26px; font-weight: 700; color: var(--text); line-height: 1; letter-spacing: -0.02em; }}
  .kpi-value.green {{ color: var(--green); }} .kpi-value.orange {{ color: var(--orange); }} .kpi-value.red {{ color: var(--red); }}
  .kpi-change {{ font-size: 12px; margin-top: 6px; }}
  .kpi-change.up {{ color: var(--green); }} .kpi-change.down {{ color: var(--red); }} .kpi-change.neutral {{ color: var(--text-muted); }}
  .kpi-sub {{ font-size: 11px; color: var(--text-muted); margin-top: 4px; }}
  .charts-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 24px; }}
  .chart-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; }}
  .chart-title {{ font-size: 13px; font-weight: 600; color: var(--text); margin-bottom: 16px; }}
  .chart-container {{ position: relative; height: 220px; }}
  .pacing-card {{ background: var(--surface); border: 1px solid var(--border); border-left: 3px solid var(--gold); border-radius: 10px; padding: 20px; margin-bottom: 24px; }}
  .pacing-header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 12px; }}
  .pacing-title {{ font-size: 14px; font-weight: 600; color: var(--text); }}
  .pacing-numbers {{ font-size: 13px; color: var(--text-muted); }}
  .pacing-numbers span {{ color: var(--text); font-weight: 600; }}
  .progress-bar-bg {{ background: var(--surface2); border-radius: 6px; height: 10px; overflow: hidden; }}
  .progress-bar-fill {{ height: 100%; border-radius: 6px; }}
  .progress-bar-fill.green {{ background: linear-gradient(90deg, #059669, var(--green)); }}
  .progress-bar-fill.orange {{ background: linear-gradient(90deg, var(--gold-dim), var(--gold)); }}
  .progress-meta {{ display: flex; justify-content: space-between; margin-top: 8px; font-size: 12px; color: var(--text-muted); }}
  .country-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin-bottom: 24px; }}
  .country-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }}
  .country-card.border-green {{ border-left: 3px solid var(--green); }}
  .country-card.border-orange {{ border-left: 3px solid var(--orange); }}
  .country-card.border-red {{ border-left: 3px solid var(--red); }}
  .country-name {{ font-size: 16px; font-weight: 700; color: var(--text); margin-bottom: 10px; display: flex; align-items: center; gap: 6px; }}
  .country-flag {{ font-size: 18px; }}
  .country-stat {{ display: flex; justify-content: space-between; align-items: center; padding: 4px 0; border-bottom: 1px solid var(--surface2); }}
  .country-stat:last-child {{ border-bottom: none; }}
  .stat-label {{ font-size: 12px; color: var(--text-muted); }}
  .stat-value {{ font-size: 13px; font-weight: 600; color: var(--text); }}
  .stat-value.green {{ color: var(--green); }} .stat-value.orange {{ color: var(--orange); }} .stat-value.red {{ color: var(--red); }}
  .roas-badge {{ font-size: 11px; font-weight: 600; padding: 1px 6px; border-radius: 4px; }}
  .roas-badge.green {{ background: var(--green-bg); color: var(--green); }}
  .roas-badge.orange {{ background: var(--orange-bg); color: var(--orange); }}
  .roas-badge.red {{ background: var(--red-bg); color: var(--red); }}
  .table-card {{ background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 20px; margin-bottom: 16px; }}
  .table-header {{ display: flex; align-items: center; justify-content: space-between; margin-bottom: 14px; }}
  .table-title {{ font-size: 14px; font-weight: 600; color: var(--text); display: flex; align-items: center; gap: 8px; }}
  .badge {{ font-size: 11px; font-weight: 600; padding: 2px 8px; border-radius: 20px; }}
  .badge.red {{ background: var(--red-bg); color: var(--red); }}
  .badge.orange {{ background: var(--orange-bg); color: var(--orange); }}
  .badge.green {{ background: var(--green-bg); color: var(--green); }}
  table {{ width: 100%; border-collapse: collapse; }}
  th {{ text-align: left; font-size: 11px; font-weight: 700; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.06em; padding: 8px 12px; border-bottom: 1px solid var(--border); }}
  td {{ padding: 10px 12px; border-bottom: 1px solid var(--surface2); font-size: 13px; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: var(--surface2); }}
  .campaign-name {{ color: var(--text); font-weight: 500; max-width: 380px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; display: block; }}
  .cpp-pill {{ font-size: 12px; font-weight: 700; padding: 3px 10px; border-radius: 20px; display: inline-block; }}
  .cpp-pill.green {{ background: var(--green-bg); color: var(--green); }}
  .cpp-pill.orange {{ background: var(--orange-bg); color: var(--orange); }}
  .cpp-pill.red {{ background: var(--red-bg); color: var(--red); }}
  .two-col {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-bottom: 16px; }}
  .section-divider {{ height: 1px; background: var(--border); margin: 28px 0; }}
  .threshold-note {{ font-size: 11px; color: var(--text-muted); margin-top: 6px; }}
  .threshold-note .green {{ color: var(--green); }} .threshold-note .orange {{ color: var(--orange); }} .threshold-note .red {{ color: var(--red); }}
  .legend {{ display: flex; gap: 16px; flex-wrap: wrap; margin-bottom: 8px; }}
  .legend-item {{ display: flex; align-items: center; gap: 6px; font-size: 12px; color: var(--text-muted); }}
  .legend-dot {{ width: 10px; height: 10px; border-radius: 50%; }}
  .legend-line {{ width: 20px; height: 2px; border-radius: 1px; }}
  ::-webkit-scrollbar {{ width: 6px; }}
  ::-webkit-scrollbar-track {{ background: var(--bg); }}
  ::-webkit-scrollbar-thumb {{ background: var(--border2); border-radius: 3px; }}
  .empty-state {{ text-align: center; padding: 24px; color: var(--text-muted); font-size: 13px; }}
</style>
</head>
<body>

<div class="header">
  <div style="display:flex;align-items:center;gap:10px;">
    <h1>IM8 Meta Dashboard</h1>
    <span class="meta-badge">META ADS</span>
  </div>
  <div class="header-right">
    <span class="period-label">📅 L7D: {L7D_SINCE} – {L7D_UNTIL} &nbsp;|&nbsp; Prior: {PRIOR_SINCE} – {PRIOR_UNTIL}</span>
    <span class="last-updated">🕐 {updated_at}</span>
    <button class="refresh-btn" onclick="window.location.reload()">↻ Refresh</button>
  </div>
</div>

<div class="container">

  <div class="section-title">L7D Overview ({L7D_SINCE} – {L7D_UNTIL})</div>
  <div class="kpi-grid">
    <div class="kpi-card">
      <div class="kpi-label">Total Spend</div>
      <div class="kpi-value">{fmt_currency(spend_l7d)}</div>
      <div class="kpi-change {spend_dir}">{spend_arrow} {fmt_currency(abs(spend_delta))} vs prior ({fmt_currency(spend_prior)})</div>
      <div class="kpi-sub">{fmt_currency(spend_l7d/7)}/day avg</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Purchases (NC)</div>
      <div class="kpi-value">{fmt_num(purchases_l7d)}</div>
      <div class="kpi-change {pur_dir}">{pur_arrow} {fmt_num(abs(pur_delta))} vs prior ({fmt_num(purchases_prior)})</div>
      <div class="kpi-sub">{fmt_num(purchases_l7d/7)}/day avg</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Est. NC Revenue</div>
      <div class="kpi-value">{fmt_currency(rev_l7d)}</div>
      <div class="kpi-change neutral">{fmt_currency(rev_l7d/7)} avg/day vs ${REVENUE_TARGET_DAILY:,} target</div>
      <div class="kpi-sub">Based on ${AOV} NC AOV</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Avg CAC (CPP)</div>
      <div class="kpi-value {cac_class(cac_l7d)}">${cac_l7d:,.2f}</div>
      <div class="kpi-change neutral">Prior week avg: ${cac_prior:,.2f}</div>
      <div class="kpi-sub">Target: &lt;${CAC_TARGET}</div>
    </div>
    <div class="kpi-card">
      <div class="kpi-label">Est. ROAS (Meta)</div>
      <div class="kpi-value {roas_class(roas_l7d)}">{roas_l7d:.2f}x</div>
      <div class="kpi-change neutral">Prior week: {roas_val(spend_prior, purchases_prior):.2f}x</div>
      <div class="kpi-sub">${AOV} AOV × purchases ÷ spend</div>
    </div>
  </div>

  <div class="pacing-card">
    <div class="pacing-header">
      <div class="pacing-title">📊 NC Revenue Pacing — {today.strftime('%B %Y')}</div>
      <div class="pacing-numbers">
        MTD Actual: <span>{fmt_currency(mtd_revenue)}</span> &nbsp;|&nbsp;
        MTD Target ({days_elapsed}d × ${REVENUE_TARGET_DAILY:,}): <span>{fmt_currency(mtd_target)}</span> &nbsp;|&nbsp;
        Gap: <span style="color:{'var(--green)' if mtd_revenue >= mtd_target else 'var(--red)'}">{'+' if mtd_revenue >= mtd_target else ''}{fmt_currency(mtd_revenue - mtd_target)}</span> &nbsp;|&nbsp;
        L7D Daily Avg: <span style="color:{'var(--green)' if rev_l7d/7 >= REVENUE_TARGET_DAILY else 'var(--orange)'}">{fmt_currency(rev_l7d/7)}</span>
      </div>
    </div>
    <div class="progress-bar-bg">
      <div class="progress-bar-fill {pacing_cls}" style="width:{min(pacing_pct, 100):.1f}%"></div>
    </div>
    <div class="progress-meta">
      <span>$0</span>
      <span style="color:var(--{'green' if pacing_pct >= 100 else 'orange'});font-weight:600">{pacing_pct:.1f}% of MTD target</span>
      <span>{fmt_currency(mtd_target)} target</span>
    </div>
  </div>

  <div class="charts-grid">
    <div class="chart-card">
      <div class="chart-title">💸 Daily Spend — L7D vs Prior Week</div>
      <div class="legend">
        <div class="legend-item"><div class="legend-line" style="background:#d4a843;height:2px;width:20px"></div> L7D</div>
        <div class="legend-item"><div class="legend-line" style="background:#4b5563;height:2px;width:20px"></div> Prior</div>
      </div>
      <div class="chart-container"><canvas id="spendChart"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🎯 Daily CAC (CPP) — L7D</div>
      <div class="legend">
        <div class="legend-item"><div class="legend-dot" style="background:var(--green)"></div> &lt;$300</div>
        <div class="legend-item"><div class="legend-dot" style="background:var(--orange)"></div> $300–$350</div>
        <div class="legend-item"><div class="legend-dot" style="background:var(--red)"></div> &gt;$350</div>
      </div>
      <div class="chart-container"><canvas id="cacChart"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">🛒 Daily Purchases — L7D vs Prior Week</div>
      <div class="chart-container"><canvas id="purchasesChart"></canvas></div>
    </div>
    <div class="chart-card">
      <div class="chart-title">📈 Est. Daily NC Revenue vs $250K Target</div>
      <div class="chart-container"><canvas id="revenueChart"></canvas></div>
    </div>
  </div>

  <div class="section-title">Key Market Performance — L7D</div>
  <div class="threshold-note" style="margin-bottom:12px;">
    CAC: <span class="green">Green &lt;$300</span> · <span class="orange">Orange $300–$350</span> · <span class="red">Red &gt;$350</span> &nbsp;|&nbsp;
    ROAS: <span class="green">Green &gt;1.0x</span> · <span class="orange">Orange 0.71–0.99x</span> · <span class="red">Red &lt;0.70x</span>
  </div>
  <div class="country-grid">
    {country_card('US', '🇺🇸', 'United States')}
    {country_card('CA', '🇨🇦', 'Canada')}
    {country_card('GB', '🇬🇧', 'United Kingdom')}
    {country_card('AU', '🇦🇺', 'Australia')}
  </div>

  <div class="section-divider"></div>
  <div class="section-title">Campaign Actions</div>

  <div class="table-card">
    <div class="table-header">
      <div class="table-title">🔴 Cut List <span class="badge red">{len(cut_list)} campaigns</span></div>
      <span style="font-size:12px;color:var(--text-muted);">CPP &gt; $600 over L7D — cut immediately</span>
    </div>
    <table>
      <thead><tr><th>Campaign</th><th>Spend</th><th>Purchases</th><th>CAC</th><th>Est. ROAS</th></tr></thead>
      <tbody>{campaign_rows(cut_list)}</tbody>
    </table>
  </div>

  <div class="two-col">
    <div class="table-card">
      <div class="table-header">
        <div class="table-title">🟠 Watch List <span class="badge orange">{len(watch_list)}</span></div>
      </div>
      <table>
        <thead><tr><th>Campaign</th><th>Spend</th><th>CAC</th><th>ROAS</th></tr></thead>
        <tbody>{''.join(f"<tr><td><span class='campaign-name'>{c['name']}</span></td><td>{fmt_currency(c['spend'])}</td><td><span class='cpp-pill orange'>${c['cac']:,.0f}</span></td><td><span class='roas-badge {roas_class(c['roas'])}'>{c['roas']:.2f}x</span></td></tr>" for c in watch_list[:8]) or "<tr><td colspan='4' class='empty-state'>None</td></tr>"}</tbody>
      </table>
    </div>
    <div class="table-card">
      <div class="table-header">
        <div class="table-title">🟢 Top Winners <span class="badge green">{len(win_list)}</span></div>
      </div>
      <table>
        <thead><tr><th>Campaign</th><th>Spend</th><th>CAC</th><th>ROAS</th></tr></thead>
        <tbody>{''.join(f"<tr><td><span class='campaign-name'>{c['name']}</span></td><td>{fmt_currency(c['spend'])}</td><td><span class='cpp-pill green'>${c['cac']:,.0f}</span></td><td><span class='roas-badge {roas_class(c['roas'])}'>{c['roas']:.2f}x</span></td></tr>" for c in win_list[:8]) or "<tr><td colspan='4' class='empty-state'>None</td></tr>"}</tbody>
      </table>
    </div>
  </div>

</div>

<script>
const GOLD = '#d4a843', GOLD_DIM = '#a07c2e';
const GREEN = '#34d399', ORANGE = '#fb923c', RED = '#f87171';
const SURFACE2 = '#22252b', TEXT_MUTED = '#7a7f8c';

Chart.defaults.color = TEXT_MUTED;
Chart.defaults.borderColor = SURFACE2;

const labels = {json.dumps(chart_labels)};
const spendL7D = {json.dumps(chart_spend_l7d)};
const spendPrior = {json.dumps(chart_spend_prior)};
const cacL7D = {json.dumps(chart_cac_l7d)};
const purchasesL7D = {json.dumps(chart_purchases_l7d)};
const purchasesPrior = {json.dumps(chart_purchases_prior)};
const revL7D = {json.dumps(chart_rev_l7d)};

new Chart(document.getElementById('spendChart'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{ label: 'L7D', data: spendL7D, borderColor: GOLD, backgroundColor: GOLD+'22', tension: 0.3, fill: true, pointRadius: 3 }},
      {{ label: 'Prior', data: spendPrior, borderColor: '#4b5563', borderDash: [4,4], tension: 0.3, fill: false, pointRadius: 2 }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ ticks: {{ callback: v => '$'+Math.round(v/1000)+'K' }} }} }} }}
}});

const cacColors = cacL7D.map(v => v < 300 ? GREEN : v <= 350 ? ORANGE : RED);
new Chart(document.getElementById('cacChart'), {{
  type: 'bar',
  data: {{ labels, datasets: [{{ label: 'CAC', data: cacL7D, backgroundColor: cacColors, borderRadius: 4 }}] }},
  options: {{
    responsive: true, maintainAspectRatio: false,
    plugins: {{ legend: {{ display: false }}, annotation: {{ annotations: {{ line1: {{ type: 'line', yMin: 300, yMax: 300, borderColor: GREEN, borderWidth: 1, borderDash: [4,4] }} }} }} }},
    scales: {{ y: {{ ticks: {{ callback: v => '$'+v }} }} }}
  }}
}});

new Chart(document.getElementById('purchasesChart'), {{
  type: 'line',
  data: {{
    labels,
    datasets: [
      {{ label: 'L7D', data: purchasesL7D, borderColor: GOLD, backgroundColor: GOLD+'22', tension: 0.3, fill: true, pointRadius: 3 }},
      {{ label: 'Prior', data: purchasesPrior, borderColor: '#4b5563', borderDash: [4,4], tension: 0.3, fill: false, pointRadius: 2 }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }} }}
}});

new Chart(document.getElementById('revenueChart'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [
      {{ label: 'NC Revenue', data: revL7D, backgroundColor: revL7D.map(v => v >= {REVENUE_TARGET_DAILY} ? GREEN+'88' : GOLD+'88'), borderRadius: 4 }},
      {{ label: 'Target', data: Array(labels.length).fill({REVENUE_TARGET_DAILY}), type: 'line', borderColor: GREEN, borderDash: [4,4], borderWidth: 1.5, fill: false, pointRadius: 0 }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false, plugins: {{ legend: {{ display: false }} }}, scales: {{ y: {{ ticks: {{ callback: v => '$'+Math.round(v/1000)+'K' }} }} }} }}
}});
</script>
</body>
</html>"""

# ── Write output ──────────────────────────────────────────────────────────────
out_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "im8-dashboard.html")
with open(out_path, "w", encoding="utf-8") as f:
    f.write(html)

print(f"Dashboard written to {out_path}")
print(f"L7D Spend: {fmt_currency(spend_l7d)} | Purchases: {fmt_num(purchases_l7d)} | CAC: ${cac_l7d:.2f}")
