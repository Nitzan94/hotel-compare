# How distance, walk/drive time, and "geolocation" work

Two separate things that often get conflated:

- **Distance + walk/drive time** — computed once, at build time, baked into the dashboard.
- **"Geolocation"** — a *live, in-browser* feature that routes from wherever you physically are when you click.

---

## 1. Distance — straight-line (always on)

Every hotel gets a straight-line ("as the crow flies") distance from each start point.

- Computed in `hotel_dashboard.py` by `haversine_km()` (line 31).
- It's the **haversine formula**: great-circle distance between two lat/lon points on a sphere (Earth radius 6371 km).
- Pure math, no network call — so it's instant and never fails.
- Output is rounded to km and miles per hotel, per start (line 127).

**This is what the map dots, the scatter chart X-axis, and the "Closest" badge use.** Labeled "straight-line" in the UI on purpose — it's a lower bound, real roads are always longer.

---

## 2. Walk / drive time — real road routing (opt-in via `--route`)

Straight-line distance doesn't tell you "20 min on foot." For that we hit a real routing engine.

- Function: `osrm_route()` in `hotel_dashboard.py` (line 19).
- Service: **OSRM** (Open Source Routing Machine) on the public OpenStreetMap server — `routing.openstreetmap.de`.
- **Free, no API key.** That's the whole reason this engine was chosen over Google Directions.

### How it works

- One HTTP request **per hotel, per profile** — `foot` for walking, `car` for driving.
- We pass `overview=false` so it returns only distance + duration, not the route geometry (faster, smaller).
- OSRM returns meters and seconds; we convert → miles (`/1609.34`) and minutes (`/60`), line 28.
- A `time.sleep(0.1)` between calls (line 170) to be polite to the free public server.

### Failure handling (deliberately loud)

- If **every** hotel fails to route → hard exit with a FATAL message telling you to re-run without `--route` (line 171).
- If **some** fail → keep going, print a WARNING per failed hotel to stderr (line 177).
- This matches the "fail loud" principle — a half-broken routing run never silently looks complete.

### Cost of the feature

- N hotels = **2N requests** (walk + drive). 30 hotels = 60 requests, ~6s of sleep alone.
- Skip it with `--no-route` for a fast straight-line-only run.

---

## 3. The geocoding step (don't confuse with geolocation)

Before any of the above, the **start address** has to become coordinates.

- `geocode.py` → `geocode()` (line 16) sends the address to **SerpAPI's Google Maps engine**.
- Returns `(lat, lon, resolved_address)` that matches what Google Maps would show.
- This anchors the dashboard's start point(s). Fails loud if the address can't be resolved.

**Why it matters:** an earlier bug was a *bad start coordinate* feeding the router — every distance was wrong. Commit `c99b613` fixed the root cause here, not in the routing layer.

---

## 4. "Geolocation" — the live, browser-side feature

This is the part that confuses, because there's history.

### What it is NOW (the kept version)

There is **no JavaScript geolocation API call** in the current dashboard. Instead:

- Each hotel has **🚶 Maps** and **🚗 Maps** buttons (table + map popups).
- They build a Google Maps directions URL with `gmapsDir()` (line 381):
  ```
  https://www.google.com/maps/dir/?api=1&destination=LAT,LON&travelmode=walking|driving
  ```
- **The origin is deliberately omitted.** When Google Maps opens with no origin, it routes from *your device's live location*.

### Why this is clever

- On your phone, the link opens the Maps app routed from exactly where you're standing — matches the native app.
- **Free, no API key, no permission prompt in our page, nothing to break.**
- The accurate "from where I am right now" time comes from Google, live — we don't try to compute it.

### The division of labor

| Need | Source | When |
|------|--------|------|
| Rank hotels by approximate walk/drive | OSRM `--route` (§2) | Build time, from the **start address** |
| Exact time from where you are now | Google Maps deep link (§4) | Click time, from your **device location** |

The OSRM numbers are labeled **Walk\* / Drive\* "estimates ... for ranking"** in the footer (line 362) precisely so nobody mistakes them for live turn-by-turn.

### The history (why commits churned)

- `39943c2` — added a **real** browser geolocation routing attempt (live OSRM from `navigator.geolocation`).
- `c99b613` — **reverted** that. The visible symptom looked like a geolocation problem but the root cause was the bad start coordinate (see §3). Reverting the browser-side complexity + fixing the coordinate was the correct, simpler fix.
- The Maps deep-link approach (§4) is what survived: it gives "from my location" routing with zero of the fragility.

---

## 5. How the walk/drive numbers actually get *into* the dashboard

The dashboard is a **single self-contained HTML file with the data baked in** — not a server with an API. Python computes everything, embeds it as a JSON literal, and JavaScript reads it back to render. Insertion happens at two boundaries.

### Step 1 — attach the numbers to each hotel (Python)

`osrm_route()` returns `{"mi":…, "min":…}`. That gets stored on the hotel's row dict (`hotel_dashboard.py:163`):

```python
walk  = osrm_route("foot", ...)
drive = osrm_route("car", ...)
r["route"] = {"walk": walk, "drive": drive}
```

Each hotel now carries its own `route` field, right next to `prices`, `rating`, etc. — so it travels through the same pipe as everything else.

### Step 2 — serialize everything to JSON (Python)

`hotel_dashboard.py:261`:

```python
payload = json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False)
```

`meta.routed = bool(args.route)` (line 258) is the flag that tells the JS whether routing ran at all.

### Step 3 — inject the JSON into the HTML template (the actual "insertion")

`hotel_dashboard.py:262`:

```python
html = HTML_TEMPLATE.replace("/*__DATA__*/", payload)
```

The template has a placeholder (line 343):

```js
const DATA = /*__DATA__*/;
```

After the replace it becomes `const DATA = {"meta":...,"rows":[...]};` — the data is now hard-coded into the file. **This is the boundary where the walk/drive numbers enter the dashboard.** The file is then written to `dashboard.html` (line 265). No fetch, no backend at view time.

### Step 4 — JavaScript reads it back and builds the cells

When the browser opens the file:

- **Columns** appear only if routing ran — `buildCols()` (line 476):
  ```js
  if(M.routed){cols.push({k:'walk_min',label:'Walk (min)'},{k:'drive_min',label:'Drive (min)'});}
  ```
- **Cell values** are pulled via `getVal()` (line 467): `r.route.walk.min` / `r.route.drive.min`.
- **The `<td>` cells** are emitted in `render()` (lines 504–506); the walk cell turns green when ≤15 min.

The same `r.route` field also feeds the **map popups** (lines 425–427), the **CSV export** (lines 238–241), and the **compare panel** (lines 543–546) — one source, four readers.

### The whole flow

```
OSRM  →  r["route"]  →  json.dumps  →  placeholder swap into HTML  →  const DATA  →  JS renders <td>
```

Everything is gated on the single `M.routed` flag, so the same template renders cleanly with or without `--route` — the columns simply don't exist when routing didn't run.

---

## TL;DR

- **Straight-line distance** = haversine math, always on, instant.
- **Walk/drive minutes** = real OSRM road routing, opt-in (`--route`), free, 2 calls/hotel, fails loud.
- **Geocoding** = address → coords via SerpAPI/Google, anchors the start point.
- **"Geolocation"** = not a JS API call — it's Google Maps **directions deep links** that route from your device's live location when tapped. The earlier live-geolocation experiment was reverted in favor of this simpler, sturdier approach.
