# 📊 Radar de Acciones LatAm

App personal y automática que analiza ADRs latinoamericanos (Brasil, México,
Chile, Perú, Colombia) que cotizan en NYSE/NASDAQ, calcula valoración, deuda
y flujo de caja descontado (DCF), y te entrega un Top 5 semanal por email +
un dashboard web accesible desde cualquier lugar.

**Costo: $0.** Todo corre con niveles gratuitos (GitHub Actions + Alpha
Vantage + Gmail).

---

## Paso 1 — Consigue tu API key gratuita de datos financieros

1. Ve a: https://www.alphavantage.co/support/#api-key
2. Completa el formulario (nombre, organización = "Personal", email).
3. Te entregan la key al instante en pantalla y por email. Guárdala.

Límite del plan gratuito: 25 consultas/día. El script ya está diseñado para
respetarlo (actualiza 5 empresas por día, en rotación).

## Paso 2 — Crea un repositorio en GitHub

1. Crea una cuenta gratis en https://github.com si no tienes una.
2. Crea un repositorio nuevo, por ejemplo `latam-radar` (puede ser público
   o privado — si es privado, el dashboard necesitará un token para leer los
   datos, así que para simplicidad se recomienda público; los datos que
   expone son solo métricas de empresas públicas, nada sensible tuyo).
3. Sube todos los archivos de esta carpeta al repositorio (arrastrando los
   archivos en la interfaz web de GitHub, o con `git push` si usas la
   terminal).

## Paso 3 — Configura las credenciales (Secrets)

En tu repositorio: **Settings → Secrets and variables → Actions → New
repository secret**. Crea estos 4 secrets:

| Nombre | Valor |
|---|---|
| `ALPHAVANTAGE_API_KEY` | La key del Paso 1 |
| `GMAIL_ADDRESS` | Tu correo de Gmail |
| `GMAIL_APP_PASSWORD` | Ver Paso 4 |
| `RECIPIENT_EMAIL` | El correo donde quieres recibir el Top 5 |

## Paso 4 — Crea una "contraseña de aplicación" de Gmail

Gmail no permite usar tu contraseña normal para enviar correos desde un
script. Necesitas una contraseña de aplicación:

1. Activa la verificación en 2 pasos en tu cuenta de Google (si no la tienes):
   https://myaccount.google.com/security
2. Ve a: https://myaccount.google.com/apppasswords
3. Genera una contraseña para "Correo" / "Otra app" — te da un código de 16
   caracteres. Ese es tu `GMAIL_APP_PASSWORD`.

## Paso 5 — Activa GitHub Actions

1. En tu repo, ve a la pestaña **Actions**.
2. Si aparece un botón para habilitar workflows, actívalo.
3. El workflow `Radar LatAm` correrá automáticamente todos los días a las
   13:00 UTC, y enviará el email los **lunes** una vez que tenga datos
   suficientes acumulados (toma unos 5 días laborales juntar todo el
   universo de 22 empresas la primera vez).
4. Puedes forzar una ejecución manual: pestaña **Actions → Radar LatAm →
   Run workflow**.

## Paso 6 — Activa GitHub Pages para el dashboard (acceso desde cualquier lugar)

1. En tu repo: **Settings → Pages**.
2. En "Source" selecciona la rama `main` y carpeta `/ (root)`.
3. Guarda. GitHub te dará una URL como:
   `https://TU_USUARIO.github.io/latam-radar/dashboard.html`
4. Guarda esa URL en tu celular (agrégala a la pantalla de inicio como si
   fuera una app). Ábrela desde cualquier lugar con internet.
5. Dentro del dashboard, en el campo de configuración, pega esta URL:
   `https://raw.githubusercontent.com/TU_USUARIO/latam-radar/main/data/results.json`
   y presiona "Cargar". Quedará guardada para la próxima vez.

---

## ¿Cómo funciona el análisis?

- **Valoración**: P/E, P/B y EV/EBITDA de cada empresa.
- **Deuda sana**: Deuda/Patrimonio ≤ 1.5 (umbral conservador, ajustable en
  `latam_radar.py` → `MAX_DEBT_TO_EQUITY`).
- **DCF simplificado**: proyecta el flujo de caja libre a 5 años (con
  crecimiento basado en el crecimiento de ingresos reciente, tope 8% anual),
  calcula un valor terminal (crecimiento perpetuo 3%), descuenta todo a una
  tasa del 12% (prima de riesgo típica para mercados emergentes), y lo
  compara con el precio actual para obtener el % de upside.
- **Top 5**: de las empresas con deuda sana y upside DCF positivo, se
  rankean combinando upside DCF, P/E bajo, P/B bajo y ROE alto.

## Limitaciones importantes (léelas)

- Es un modelo **simplificado**, pensado como punto de partida para tu
  propia investigación — no reemplaza un análisis profesional ni
  constituye asesoría financiera.
- Los supuestos del DCF (tasa de descuento, crecimiento) son genéricos para
  todas las empresas; en la realidad cada una merece supuestos propios.
- Se usan ADRs (recibos en USD que cotizan en EE.UU.) en vez de las
  acciones locales, por mejor calidad de datos gratuitos. Esto añade
  exposición al tipo de cambio USD que no está modelada aparte.
- El universo son ~22 empresas grandes/líquidas; no cubre small caps
  locales.

## Personalizar el universo de empresas

Edita la lista `UNIVERSE` en `latam_radar.py` para agregar o quitar
tickers. Cualquier ADR que cotice en NYSE/NASDAQ funciona.
