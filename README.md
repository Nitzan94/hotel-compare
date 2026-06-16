# hotel-compare

Search hotels around any place, get live per-room prices for your dates, and compare them in a professional HTML dashboard — sortable table, an interactive map, and a price-vs-distance chart.

Data comes from **Google Hotels via [SerpAPI](https://serpapi.com)**. No scraping, no browser automation. Pure-stdlib Python (no pip dependencies).

## What you get

- **Live prices** for your exact check-in/check-out dates and party size.
- **Distance** from one or more start points (an address, a landmark, a station) — straight-line, ranked.
- **Real walking + driving time** from your start point (with `--route`) — routed over the actual street network, free, no key.
- **A dashboard** (`dashboard.html`) — self-contained, opens in any browser:
  - Summary cards: nightly range, cheapest, closest, top-rated.
  - **Map** (Leaflet + OpenStreetMap) — every hotel + your start points, colored by rating, sized by reviews.
  - **Scatter** — price vs. distance, so cheap-and-close hotels sit in the lower-left.
  - **Sortable table** — click any column. Distance, class, rating, room price + total, a value score, and booking links.
- **Booking links** — deep links to each hotel on Google, Booking.com, and Expedia for your dates.
- **Directions** — Google Maps walk/drive links from your device's live location (open on your phone for the exact time you'd see in the app). Free, no key.
- **📍 Use my location** — a button that reads your browser's live position and routes real walk/drive times from where you actually are (OSRM, free, no key), re-sorting the table by walk time. Requires serving over `http://localhost` (browsers block geolocation on `file://`).
- **Hotels only** — vacation-rental / aggregator listings that Google Hotels mixes in are filtered out by default (`--include-rentals` to keep them).
- **A CSV** (`hotels.csv`) — same data, spreadsheet-ready.

## Setup

```bash
cp .env.example .env       # then paste your SerpAPI key into .env
```

Requires [`uv`](https://github.com/astral-sh/uv) (or run with plain `python3` — there are no third-party deps).

## Use

**1. Fetch prices** (one call per party size):

```bash
uv run scripts/hotel_search.py "hotels in downtown Sunnyvale California" \
  --check-in 2026-09-19 --check-out 2026-09-30 \
  --adults 2 --currency USD --max 30 \
  --out runs/sunnyvale/raw.json > runs/sunnyvale/out.json
```

**2. Build the dashboard** (distance from one or more start points):

```bash
uv run scripts/hotel_dashboard.py \
  --out-dir runs/sunnyvale \
  --location "Downtown Sunnyvale, CA" \
  --check-in 2026-09-19 --check-out 2026-09-30 --nights 11 --currency USD \
  --start "240 S Taaffe St" 37.3701 -122.0347 \
  --start "Murphy Ave / Caltrain" 37.3779 -122.0312 \
  --party "Room (2 guests)" runs/sunnyvale/out.json \
  --route
```

Then open `runs/sunnyvale/dashboard.html`.

To use the **📍 Use my location** button (browsers block geolocation on `file://`), serve it over localhost instead:

```bash
cd runs/sunnyvale && python3 -m http.server 8765
# then open http://localhost:8765/dashboard.html
```

- Pass `--party` more than once (e.g. a 1-adult and a 2-adult run) to show multiple price columns side by side.
- The first `--start` is the primary one — it drives sorting, the value score, and routing.
- `--route` adds **real walking + driving time/distance** from the primary start to each hotel, via the free public OSRM server ([routing.openstreetmap.de](https://routing.openstreetmap.de)) — no key. Omit it to skip routing (straight-line distance only).

## Search parameters

`hotel_search.py` sends these to SerpAPI's `google_hotels` engine:

| Param | Flag | Default |
|---|---|---|
| `q` | positional | — (location or landmark) |
| `check_in_date` / `check_out_date` | `--check-in` / `--check-out` | required |
| `adults` / `children` | `--adults` / `--children` | 2 / 0 |
| `currency` | `--currency` | USD |
| `gl` / `hl` | `--gl` / `--hl` | us / en |
| `sort_by` | `--sort` | relevance (3=price, 8=rating, 13=reviews) |
| `min_price` / `max_price` | `--min-price` / `--max-price` | none |

## Notes

- **Prices are per-room.** US hotels rarely price per person, so 1 vs 2 guests is usually identical — the split only matters where a property prices by occupancy.
- **Booking links are deep links, not scraped OTA prices.** Live multi-site prices would require a per-hotel SerpAPI detail call (one credit each).
- **Walk/Drive columns are OSRM estimates** for ranking. For the exact time from where you are, use the **🚶/🚗 Maps** Directions links — they open Google Maps from your device's live location, with no API key (Google's keyless [Maps URLs](https://developers.google.com/maps/documentation/urls/get-started)).
- **Vacation-rental listings are hidden by default.** Google Hotels returns aggregator entries (Bluepillow etc.) with `type: "vacation rental"` and often bad pins; they're filtered unless you pass `--include-rentals`.
- Every script **fails loud** — a missing key or API error stops with a named cause, never a silent empty result.

## License

MIT
