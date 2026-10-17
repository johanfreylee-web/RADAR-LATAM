"""
Radar de Acciones LatAm
========================
Obtiene datos fundamentales (via Alpha Vantage) de ADRs latinoamericanos
que cotizan en NYSE/NASDAQ, calcula:
  - Múltiplos de valoración (P/E, P/B, EV/EBITDA)
  - Salud de deuda (Deuda/Patrimonio)
  - Valor intrínseco vía DCF simplificado (Flujo de Caja Descontado)
Y arma un ranking Top 5 de oportunidades infravaloradas con deuda sana.

Diseñado para correr automáticamente vía GitHub Actions.
Respeta el límite gratuito de Alpha Vantage (25 requests/día) actualizando
solo un subconjunto de tickers cada día (rotación), y usando el cache
(data/cache.json) para el ranking semanal.
"""

import os
import json
import time
import smtplib
import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import requests

# ---------------------------------------------------------------------------
# Configuración
# ---------------------------------------------------------------------------

API_KEY = os.environ.get("ALPHAVANTAGE_API_KEY", "demo")
BASE_URL = "https://www.alphavantage.co/query"

CACHE_PATH = os.path.join(os.path.dirname(__file__), "data", "cache.json")
RESULTS_PATH = os.path.join(os.path.dirname(__file__), "data", "results.json")

# Tickers ADR de empresas latinoamericanas que cotizan en EE.UU.
# (mejor cobertura de datos fundamentales que las bolsas locales en el tier gratuito)
UNIVERSE = [
    {"ticker": "VALE", "name": "Vale S.A.", "pais": "Brasil", "sector": "Minería"},
    {"ticker": "PBR", "name": "Petrobras", "pais": "Brasil", "sector": "Energía"},
    {"ticker": "ITUB", "name": "Itaú Unibanco", "pais": "Brasil", "sector": "Banca"},
    {"ticker": "BBD", "name": "Bradesco", "pais": "Brasil", "sector": "Banca"},
    {"ticker": "ABEV", "name": "Ambev", "pais": "Brasil", "sector": "Consumo"},
    {"ticker": "SUZ", "name": "Suzano", "pais": "Brasil", "sector": "Materiales"},
    {"ticker": "GGB", "name": "Gerdau", "pais": "Brasil", "sector": "Materiales"},
    {"ticker": "ERJ", "name": "Embraer", "pais": "Brasil", "sector": "Industrial"},
    {"ticker": "BSBR", "name": "Santander Brasil", "pais": "Brasil", "sector": "Banca"},
    {"ticker": "AMX", "name": "América Móvil", "pais": "México", "sector": "Telecom"},
    {"ticker": "FMX", "name": "FEMSA", "pais": "México", "sector": "Consumo"},
    {"ticker": "CX", "name": "Cemex", "pais": "México", "sector": "Materiales"},
    {"ticker": "TV", "name": "Grupo Televisa", "pais": "México", "sector": "Media"},
    {"ticker": "BCH", "name": "Banco de Chile", "pais": "Chile", "sector": "Banca"},
    {"ticker": "BSAC", "name": "Santander Chile", "pais": "Chile", "sector": "Banca"},
    {"ticker": "CCU", "name": "CCU", "pais": "Chile", "sector": "Consumo"},
    {"ticker": "BAP", "name": "Credicorp", "pais": "Perú", "sector": "Banca"},
    {"ticker": "BVN", "name": "Buenaventura", "pais": "Perú", "sector": "Minería"},
    {"ticker": "SCCO", "name": "Southern Copper", "pais": "Perú/México", "sector": "Minería"},
    {"ticker": "CIB", "name": "Bancolombia", "pais": "Colombia", "sector": "Banca"},
    {"ticker": "EC", "name": "Ecopetrol", "pais": "Colombia", "sector": "Energía"},
    {"ticker": "AVAL", "name": "Grupo Aval", "pais": "Colombia", "sector": "Banca"},
]

TICKERS_PER_DAY = 5          # 5 tickers x 4 llamadas = 20 requests/día (límite: 25)
MAX_DEBT_TO_EQUITY = 1.5     # umbral de "deuda sana"
DISCOUNT_RATE = 0.12         # tasa de descuento para el DCF (prima por riesgo EM)
TERMINAL_GROWTH = 0.03
PROJECTION_YEARS = 5
DEFAULT_GROWTH = 0.05
MAX_GROWTH = 0.08


# ---------------------------------------------------------------------------
# Utilidades de datos
# ---------------------------------------------------------------------------

def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, "r") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    os.makedirs(os.path.dirname(CACHE_PATH), exist_ok=True)
    with open(CACHE_PATH, "w") as f:
        json.dump(cache, f, indent=2)


def av_call(function, symbol):
    params = {"function": function, "symbol": symbol, "apikey": API_KEY}
    r = requests.get(BASE_URL, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def safe_float(value, default=None):
    try:
        if value in (None, "None", "-", ""):
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def fetch_ticker_data(symbol):
    """Trae Overview, Balance Sheet, Cash Flow y Quote para un ticker."""
    overview = av_call("OVERVIEW", symbol)
    time.sleep(13)  # respeta 5 req/min
    balance = av_call("BALANCE_SHEET", symbol)
    time.sleep(13)
    cashflow = av_call("CASH_FLOW", symbol)
    time.sleep(13)
    quote = av_call("GLOBAL_QUOTE", symbol)
    time.sleep(13)
    return overview, balance, cashflow, quote


def compute_metrics(meta, overview, balance, cashflow, quote):
    result = {**meta, "actualizado": datetime.date.today().isoformat()}

    price = safe_float((quote.get("Global Quote") or {}).get("05. price"))
    shares_out = safe_float(overview.get("SharesOutstanding"))
    pe = safe_float(overview.get("PERatio"))
    pb = safe_float(overview.get("PriceToBookRatio"))
    ev_ebitda = safe_float(overview.get("EVToEBITDA"))
    roe = safe_float(overview.get("ReturnOnEquityTTM"))
    rev_growth = safe_float(overview.get("QuarterlyRevenueGrowthYOY"))

    # --- Deuda ---
    try:
        bs = balance["annualReports"][0]
        total_debt = safe_float(bs.get("shortLongTermDebtTotal")) or 0
        equity = safe_float(bs.get("totalShareholderEquity"))
        debt_to_equity = (total_debt / equity) if equity else None
    except (KeyError, IndexError, ZeroDivisionError):
        debt_to_equity = None

    # --- DCF simplificado ---
    intrinsic_value = None
    upside_pct = None
    try:
        cf = cashflow["annualReports"][0]
        op_cf = safe_float(cf.get("operatingCashflow"))
        capex = safe_float(cf.get("capitalExpenditures")) or 0
        fcf = op_cf - abs(capex) if op_cf is not None else None

        growth = rev_growth if rev_growth is not None else DEFAULT_GROWTH
        growth = max(0.0, min(growth, MAX_GROWTH))

        if fcf and shares_out:
            pv_sum = 0.0
            projected_fcf = fcf
            for year in range(1, PROJECTION_YEARS + 1):
                projected_fcf *= (1 + growth)
                pv_sum += projected_fcf / ((1 + DISCOUNT_RATE) ** year)
            terminal_value = (projected_fcf * (1 + TERMINAL_GROWTH)) / (
                DISCOUNT_RATE - TERMINAL_GROWTH
            )
            pv_terminal = terminal_value / ((1 + DISCOUNT_RATE) ** PROJECTION_YEARS)
            enterprise_value = pv_sum + pv_terminal
            intrinsic_value = enterprise_value / shares_out
            if price:
                upside_pct = ((intrinsic_value - price) / price) * 100
    except (KeyError, IndexError, ZeroDivisionError, TypeError):
        pass

    result.update({
        "precio": price,
        "pe_ratio": pe,
        "pb_ratio": pb,
        "ev_ebitda": ev_ebitda,
        "roe": roe,
        "debt_to_equity": debt_to_equity,
        "valor_intrinseco_dcf": round(intrinsic_value, 2) if intrinsic_value else None,
        "upside_dcf_pct": round(upside_pct, 1) if upside_pct is not None else None,
        "deuda_sana": (debt_to_equity is not None and debt_to_equity <= MAX_DEBT_TO_EQUITY),
    })
    return result


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------

def score_entry(e):
    """Score compuesto: mayor es mejor. Penaliza datos faltantes."""
    score = 0.0
    n = 0
    if e.get("upside_dcf_pct") is not None:
        score += e["upside_dcf_pct"]
        n += 1
    if e.get("pe_ratio"):
        score += max(0, 25 - e["pe_ratio"])  # PE bajo = mejor
        n += 1
    if e.get("pb_ratio"):
        score += max(0, 3 - e["pb_ratio"]) * 10
        n += 1
    if e.get("roe"):
        score += e["roe"] * 50
        n += 1
    return score / n if n else -999


def build_ranking(cache):
    entries = list(cache.values())
    qualified = [
        e for e in entries
        if e.get("deuda_sana") and e.get("upside_dcf_pct") is not None and e["upside_dcf_pct"] > 0
    ]
    qualified.sort(key=score_entry, reverse=True)
    return qualified[:5]


# ---------------------------------------------------------------------------
# Email
# ---------------------------------------------------------------------------

def send_email(top5):
    gmail_user = os.environ.get("GMAIL_ADDRESS")
    gmail_pass = os.environ.get("GMAIL_APP_PASSWORD")
    recipient = os.environ.get("RECIPIENT_EMAIL")
    if not (gmail_user and gmail_pass and recipient):
        print("Faltan credenciales de email; se omite el envío.")
        return

    rows = ""
    for i, e in enumerate(top5, 1):
        rows += f"""
        <tr>
          <td>{i}</td>
          <td><b>{e['ticker']}</b><br>{e['name']}</td>
          <td>{e['pais']}</td>
          <td>${e.get('precio', 'N/D')}</td>
          <td>{e.get('pe_ratio', 'N/D')}</td>
          <td>{round(e.get('debt_to_equity', 0), 2) if e.get('debt_to_equity') else 'N/D'}</td>
          <td style="color:green"><b>+{e.get('upside_dcf_pct', 'N/D')}%</b></td>
        </tr>"""

    html = f"""
    <h2>📊 Radar LatAm — Top 5 de la semana</h2>
    <p>Empresas infravaloradas con deuda sana (Deuda/Patrimonio ≤ {MAX_DEBT_TO_EQUITY}):</p>
    <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse">
      <tr style="background:#f0f0f0">
        <th>#</th><th>Empresa</th><th>País</th><th>Precio</th>
        <th>P/E</th><th>Deuda/Patrim.</th><th>Upside DCF</th>
      </tr>
      {rows}
    </table>
    <p style="color:#888;font-size:12px">Análisis automático, no constituye asesoría financiera.</p>
    """

    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"Radar LatAm — Top 5 oportunidades ({datetime.date.today()})"
    msg["From"] = gmail_user
    msg["To"] = recipient
    msg.attach(MIMEText(html, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_user, gmail_pass)
        server.sendmail(gmail_user, recipient, msg.as_string())
    print(f"Email enviado a {recipient}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    cache = load_cache()

    # Rotación: qué tickers tocan hoy
    day_index = datetime.date.today().toordinal()
    start = (day_index * TICKERS_PER_DAY) % len(UNIVERSE)
    todays = [UNIVERSE[(start + i) % len(UNIVERSE)] for i in range(TICKERS_PER_DAY)]

    for meta in todays:
        symbol = meta["ticker"]
        print(f"Actualizando {symbol}...")
        try:
            overview, balance, cashflow, quote = fetch_ticker_data(symbol)
            cache[symbol] = compute_metrics(meta, overview, balance, cashflow, quote)
        except Exception as exc:
            print(f"Error con {symbol}: {exc}")

    save_cache(cache)

    top5 = build_ranking(cache)
    os.makedirs(os.path.dirname(RESULTS_PATH), exist_ok=True)
    with open(RESULTS_PATH, "w") as f:
        json.dump({
            "generado": datetime.date.today().isoformat(),
            "top5": top5,
            "universo_completo": list(cache.values()),
        }, f, indent=2)

    # Enviar email solo los lunes (o si se fuerza vía variable de entorno)
    is_monday = datetime.date.today().weekday() == 0
    if is_monday or os.environ.get("FORCE_EMAIL") == "true":
        if top5:
            send_email(top5)
        else:
            print("Aún no hay suficientes datos para armar el Top 5 (cache incompleto).")


if __name__ == "__main__":
    main()
