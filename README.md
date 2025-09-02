"""
# Weather App – FastAPI + SQLite

**Covers Tech Assessment 1 fully** and **Tech Assessment 2 (CRUD + optional exports & extra APIs)**.

- Stack: FastAPI (Python), SQLite (SQLAlchemy), HTMX + Vanilla JS frontend served by FastAPI.
- External APIs: Open‑Meteo Forecast API & Geocoding API (no API key required).
- Persistence: SQLite with full CRUD for saved weather requests.
- Exports: JSON, CSV, Markdown.
- Extras: Current‑location (browser geolocation), 5‑day forecast, simple icons, Google Maps & YouTube helper links.

## Quick Start

```bash
# 1) Create & activate virtualenv
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) Install deps
pip install -r requirements.txt

# 3) Run the app
uvicorn app.main:app --reload --port 8000

# 4) Open
http://localhost:8000
```

## What’s Implemented vs. Requirements

- **Tech 1**
  - Enter a location in many forms (city, postal code, landmark string). Fuzzy geocoding via Open‑Meteo.
  - Show **current weather** + **5‑day forecast** with icons.
  - Use **current device location** (browser geolocation).
  - Real data via API calls (no static data).

- **Tech 2**
  - **CRUD with SQLite**
    - **Create**: save a request with location and date range, fetch & store temps for the period.
    - **Read**: list and load any saved record.
    - **Update**: edit saved location/date range; re‑validates & refreshes weather data.
    - **Delete**: remove records.
  - **Validations**: date range sanity checks; geocoding validation; limits to forecastable horizon.
  - **Optional – API Integrations**: one‑click **Google Maps** and **YouTube** search links for the saved location.
  - **Optional – Data Export**: export all (or a single record) as **JSON**, **CSV**, or **Markdown**.

## Notes
- Forecast horizon uses Open‑Meteo up to 16 days. Historical API is omitted for brevity.
- The UI is intentionally minimal; a designer can skin it later.
- Add your name in **app/static/index.html** (`YOUR_NAME_HERE`).

---
"""