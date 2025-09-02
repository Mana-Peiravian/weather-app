from __future__ import annotations

import csv
import io
import json
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any

import httpx
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from pydantic import BaseModel, field_validator
from sqlalchemy import create_engine, select, func
from sqlalchemy.orm import DeclarativeBase, mapped_column, Mapped, Session
from sqlalchemy import String, Integer, Float, Date, DateTime, Text

OPEN_METEO_FORECAST = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODE = "https://geocoding-api.open-meteo.com/v1/search"

DB_URL = "sqlite:///./weather.db"
engine = create_engine(DB_URL, echo=False)

class Base(DeclarativeBase):
    pass

class WeatherQuery(Base):
    __tablename__ = "queries"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    location_input: Mapped[str] = mapped_column(String(255))
    resolved_name: Mapped[str] = mapped_column(String(255))
    country: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    lat: Mapped[float] = mapped_column(Float)
    lon: Mapped[float] = mapped_column(Float)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    weather_json: Mapped[str] = mapped_column(Text)  # stored forecast slice

Base.metadata.create_all(engine)

def get_session():
    with Session(engine) as s:
        yield s

# ── Pydantic Schemas ────────────────────────────────────────────────────────

class CreateQueryIn(BaseModel):
    location: str
    date_from: date
    date_to: date

    @field_validator("date_to")
    @classmethod
    def check_range(cls, v, info):
        # ensure date_to >= date_from handled in endpoint with both fields
        return v

class UpdateQueryIn(BaseModel):
    location: Optional[str] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None

# ── App & Static ────────────────────────────────────────────────────────────

app = FastAPI(title="Weather App – FastAPI + SQLite")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/static")

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# ── Helpers ────────────────────────────────────────────────────────────────

async def geocode_location(q: str) -> Dict[str, Any]:
    params = {"name": q, "count": 1, "language": "en", "format": "json"}
    async with httpx.AsyncClient(timeout=15) as client:
        r = await client.get(OPEN_METEO_GEOCODE, params=params)
        r.raise_for_status()
        data = r.json()
        if not data.get("results"):
            raise HTTPException(status_code=404, detail="Location not found")
        top = data["results"][0]
        return {
            "name": top.get("name"),
            "country": top.get("country"),
            "lat": top["latitude"],
            "lon": top["longitude"],
        }

WEATHERCODE_EMOJI = {
    # WMO weather codes mapping – minimal set for demo
    0: "☀️ Clear",
    1: "🌤️ Mainly clear",
    2: "⛅ Partly cloudy",
    3: "☁️ Overcast",
    45: "🌫️ Fog",
    48: "🌫️ Depositing rime fog",
    51: "🌦️ Drizzle (light)",
    53: "🌦️ Drizzle (moderate)",
    55: "🌧️ Drizzle (dense)",
    61: "🌦️ Rain (slight)",
    63: "🌧️ Rain (moderate)",
    65: "🌧️ Rain (heavy)",
    71: "🌨️ Snow (slight)",
    73: "🌨️ Snow (moderate)",
    75: "❄️ Snow (heavy)",
    80: "🌦️ Rain showers (slight)",
    81: "🌧️ Rain showers (moderate)",
    82: "⛈️ Rain showers (violent)",
    95: "⛈️ Thunderstorm",
    96: "⛈️ Thunderstorm (hail)",
    99: "⛈️ Thunderstorm (heavy hail)",
}

async def fetch_current(lat: float, lon: float) -> Dict[str, Any]:
    params = {
        "latitude": lat,
        "longitude": lon,
        "current": ["temperature_2m", "relative_humidity_2m", "wind_speed_10m", "weather_code"],
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(OPEN_METEO_FORECAST, params=params)
        r.raise_for_status()
        return r.json()

async def fetch_daily(lat: float, lon: float, days: int) -> Dict[str, Any]:
    days = max(1, min(days, 16))
    params = {
        "latitude": lat,
        "longitude": lon,
        "daily": [
            "temperature_2m_max",
            "temperature_2m_min",
            "precipitation_sum",
            "sunrise",
            "sunset",
            "weather_code",
        ],
        "forecast_days": days,
        "timezone": "auto",
    }
    async with httpx.AsyncClient(timeout=20) as client:
        r = await client.get(OPEN_METEO_FORECAST, params=params)
        r.raise_for_status()
        return r.json()

# ── API: Current & Forecast ────────────────────────────────────────────────

@app.get("/api/resolve_location")
async def resolve_location(q: str = Query(..., min_length=1)):
    return await geocode_location(q)

@app.get("/api/weather/current")
async def api_current(q: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None):
    if q:
        loc = await geocode_location(q)
        lat, lon = loc["lat"], loc["lon"]
    if lat is None or lon is None:
        raise HTTPException(400, "Provide q or lat/lon")
    data = await fetch_current(lat, lon)
    return data

@app.get("/api/weather/forecast")
async def api_forecast(q: Optional[str] = None, lat: Optional[float] = None, lon: Optional[float] = None, days: int = 5):
    if q:
        loc = await geocode_location(q)
        lat, lon = loc["lat"], loc["lon"]
    if lat is None or lon is None:
        raise HTTPException(400, "Provide q or lat/lon")
    data = await fetch_daily(lat, lon, days)
    return data

# ── API: CRUD for persisted queries ────────────────────────────────────────

@app.post("/api/queries")
async def create_query(payload: CreateQueryIn, session: Session = Depends(get_session)):
    if payload.date_to < payload.date_from:
        raise HTTPException(400, "date_to must be same or after date_from")

    loc = await geocode_location(payload.location)

    # Limit to forecast window: today .. today+16
    today = date.today()
    max_end = today + timedelta(days=16)
    if payload.date_from < today:
        raise HTTPException(400, "date_from must be today or later (demo app uses forecast only)")
    if payload.date_to > max_end:
        raise HTTPException(400, "date_to exceeds forecast horizon (max 16 days)")

    # days requested
    days = (payload.date_to - payload.date_from).days + 1
    fc = await fetch_daily(loc["lat"], loc["lon"], days)

    # filter to date window (Open‑Meteo starts at today 00:00)
    wanted = set(
        (payload.date_from + timedelta(days=i)).isoformat() for i in range(days)
    )
    idx = [i for i, t in enumerate(fc["daily"]["time"]) if t in wanted]

    def slice_list(lst):
        return [lst[i] for i in idx]

    sliced = {
        "latitude": fc.get("latitude"),
        "longitude": fc.get("longitude"),
        "timezone": fc.get("timezone"),
        "daily": {
            "time": slice_list(fc["daily"]["time"]),
            "temperature_2m_max": slice_list(fc["daily"]["temperature_2m_max"]),
            "temperature_2m_min": slice_list(fc["daily"]["temperature_2m_min"]),
            "precipitation_sum": slice_list(fc["daily"]["precipitation_sum"]),
            "sunrise": slice_list(fc["daily"]["sunrise"]),
            "sunset": slice_list(fc["daily"]["sunset"]),
            "weather_code": slice_list(fc["daily"]["weather_code"]),
        },
    }

    rec = WeatherQuery(
        location_input=payload.location,
        resolved_name=loc["name"],
        country=loc.get("country"),
        lat=loc["lat"],
        lon=loc["lon"],
        date_from=payload.date_from,
        date_to=payload.date_to,
        weather_json=json.dumps(sliced),
    )
    session.add(rec)
    session.commit()
    session.refresh(rec)
    return {"id": rec.id}

@app.get("/api/queries")
async def list_queries(session: Session = Depends(get_session)):
    rows = session.scalars(select(WeatherQuery).order_by(WeatherQuery.created_at.desc())).all()
    return [
        {
            "id": r.id,
            "location_input": r.location_input,
            "resolved_name": r.resolved_name,
            "country": r.country,
            "lat": r.lat,
            "lon": r.lon,
            "date_from": r.date_from.isoformat(),
            "date_to": r.date_to.isoformat(),
            "created_at": r.created_at.isoformat() + "Z",
        }
        for r in rows
    ]

@app.get("/api/queries/{qid}")
async def get_query(qid: int, session: Session = Depends(get_session)):
    r = session.get(WeatherQuery, qid)
    if not r:
        raise HTTPException(404, "record not found")
    return {
        "id": r.id,
        "meta": {
            "resolved_name": r.resolved_name,
            "country": r.country,
            "lat": r.lat,
            "lon": r.lon,
            "date_from": r.date_from.isoformat(),
            "date_to": r.date_to.isoformat(),
        },
        "data": json.loads(r.weather_json),
    }

@app.put("/api/queries/{qid}")
async def update_query(qid: int, payload: UpdateQueryIn, session: Session = Depends(get_session)):
    r = session.get(WeatherQuery, qid)
    if not r:
        raise HTTPException(404, "record not found")

    new_loc = None
    if payload.location:
        new_loc = await geocode_location(payload.location)
    loc = {
        "name": r.resolved_name,
        "country": r.country,
        "lat": r.lat,
        "lon": r.lon,
    }
    if new_loc:
        loc = {"name": new_loc["name"], "country": new_loc.get("country"), "lat": new_loc["lat"], "lon": new_loc["lon"]}
        r.location_input = payload.location
        r.resolved_name = loc["name"]
        r.country = loc.get("country")
        r.lat = loc["lat"]
        r.lon = loc["lon"]

    df = payload.date_from or r.date_from
    dt = payload.date_to or r.date_to
    if dt < df:
        raise HTTPException(400, "date_to must be same or after date_from")

    # Validate horizon
    today = date.today()
    max_end = today + timedelta(days=16)
    if df < today:
        raise HTTPException(400, "date_from must be today or later (demo app uses forecast only)")
    if dt > max_end:
        raise HTTPException(400, "date_to exceeds forecast horizon (max 16 days)")

    days = (dt - df).days + 1
    fc = await fetch_daily(loc["lat"], loc["lon"], days)

    wanted = set((df + timedelta(days=i)).isoformat() for i in range(days))
    idx = [i for i, t in enumerate(fc["daily"]["time"]) if t in wanted]

    def slice_list(lst):
        return [lst[i] for i in idx]

    sliced = {
        "latitude": fc.get("latitude"),
        "longitude": fc.get("longitude"),
        "timezone": fc.get("timezone"),
        "daily": {
            "time": slice_list(fc["daily"]["time"]),
            "temperature_2m_max": slice_list(fc["daily"]["temperature_2m_max"]),
            "temperature_2m_min": slice_list(fc["daily"]["temperature_2m_min"]),
            "precipitation_sum": slice_list(fc["daily"]["precipitation_sum"]),
            "sunrise": slice_list(fc["daily"]["sunrise"]),
            "sunset": slice_list(fc["daily"]["sunset"]),
            "weather_code": slice_list(fc["daily"]["weather_code"]),
        },
    }

    r.date_from = df
    r.date_to = dt
    r.weather_json = json.dumps(sliced)

    session.commit()
    return {"ok": True}

@app.delete("/api/queries/{qid}")
async def delete_query(qid: int, session: Session = Depends(get_session)):
    r = session.get(WeatherQuery, qid)
    if not r:
        raise HTTPException(404, "record not found")
    session.delete(r)
    session.commit()
    return {"ok": True}

# ── API: Export ────────────────────────────────────────────────────────────

@app.get("/api/export")
async def export_all(format: str = Query("json", pattern="^(json|csv|md)$"), qid: Optional[int] = None, session: Session = Depends(get_session)):
    rows = []
    if qid is None:
        rows = session.scalars(select(WeatherQuery).order_by(WeatherQuery.created_at.desc())).all()
    else:
        row = session.get(WeatherQuery, qid)
        if not row:
            raise HTTPException(404, "record not found")
        rows = [row]

    parsed = [
        {
            "id": r.id,
            "location_input": r.location_input,
            "resolved_name": r.resolved_name,
            "country": r.country,
            "lat": r.lat,
            "lon": r.lon,
            "date_from": r.date_from.isoformat(),
            "date_to": r.date_to.isoformat(),
            "created_at": r.created_at.isoformat() + "Z",
            "data": json.loads(r.weather_json),
        }
        for r in rows
    ]

    if format == "json":
        return JSONResponse(parsed)

    if format == "csv":
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["id","resolved_name","country","lat","lon","date","t_max","t_min","precip","weather_code"]) 
        for rec in parsed:
            d = rec["data"]["daily"]
            for i, t in enumerate(d["time"]):
                writer.writerow([
                    rec["id"], rec["resolved_name"], rec["country"], rec["lat"], rec["lon"],
                    t,
                    d["temperature_2m_max"][i],
                    d["temperature_2m_min"][i],
                    d["precipitation_sum"][i],
                    d["weather_code"][i],
                ])
        return PlainTextResponse(buf.getvalue(), media_type="text/csv")

    if format == "md":
        lines = ["# Weather Export\n"]
        for rec in parsed:
            lines.append(f"## {rec['resolved_name']}, {rec.get('country','')} (id={rec['id']})\n")
            lines.append("")
            lines.append("| Date | Max °C | Min °C | Precip (mm) | Code |\n|---|---:|---:|---:|---:|")
            d = rec["data"]["daily"]
            for i, t in enumerate(d["time"]):
                lines.append(f"| {t} | {d['temperature_2m_max'][i]} | {d['temperature_2m_min'][i]} | {d['precipitation_sum'][i]} | {d['weather_code'][i]} |")
            lines.append("")
        return PlainTextResponse("\n".join(lines), media_type="text/markdown")