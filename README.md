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
  - **Compare panel** — tick 1-3 rows to get a side-by-side card (price, distance, walk/drive, rating, value, amenities, booking links) with the best cell per attribute highlighted.
- **Booking links** — deep links to each hotel on Google, Booking.com, and Expedia for your dates.
- **Directions** — Google Maps walk/drive links from your device's live location (open on your phone for the exact time you'd see in the app). Free, no key.
- **Hotels only** — vacation-rental / aggregator listings that Google Hotels mixes in are filtered out by default (`--include-rentals` to keep them).
- **A CSV** (`hotels.csv`) — same data, spreadsheet-ready.

## Setup

```bash
cp .env.example .env       # then paste your SerpAPI key into .env
```

Requires [`uv`](https://github.com/astral-sh/uv) (or run with plain `python3` — there are no third-party deps).

## Use

One command — pass your **own start address** (any address, anywhere) and your dates. It geocodes the start via Google (so distances are accurate), searches hotels, and builds the dashboard:

```bash
uv run scripts/hotel_compare.py \
  --location "downtown Sunnyvale California" \
  --start "240 S Taaffe St, Sunnyvale, CA 94086" \
  --check-in 2026-09-19 --check-out 2026-09-30 \
  --adults 2
```

It prints the output path; open the `dashboard.html` it names.

- **`--start` is just an address** — it's geocoded for you via Google, so you don't hand-enter coordinates (that was the #1 source of wrong distances). Pass `--start` more than once to compare distance from several points; the first is primary (drives sorting + the value score).
- `--location` is where to search for hotels (city / neighborhood / landmark).
- `--adults` / `--children` / `--currency` / `--max` are optional (defaults: 2 / 0 / USD / 30).
- `--no-route` skips walk/drive routing (faster; straight-line distance only).

The dashboard's walk/drive times come from the free OSRM server and, from an accurately geocoded start, match Google Maps within a couple of minutes. For the exact Google time from where you are *right now*, tap a 🚶/🚗 **Maps** link in any row.

<details>
<summary>Run the steps manually (geocode → search → dashboard)</summary>

```bash
# geocode a start address -> {lat, lon}
uv run scripts/geocode.py "240 S Taaffe St, Sunnyvale, CA 94086"

# fetch prices
uv run scripts/hotel_search.py "hotels in downtown Sunnyvale California" \
  --check-in 2026-09-19 --check-out 2026-09-30 --adults 2 --max 30 \
  --out runs/sunnyvale/raw.json > runs/sunnyvale/out.json

# build the dashboard (coords from the geocode step)
uv run scripts/hotel_dashboard.py --out-dir runs/sunnyvale \
  --location "Downtown Sunnyvale, CA" \
  --check-in 2026-09-19 --check-out 2026-09-30 --nights 11 \
  --start "240 S Taaffe St" 37.3747265 -122.0313455 \
  --party "Room (2 guests)" runs/sunnyvale/out.json --route
```
</details>

## Claude Code skill

This repo ships a [Claude Code](https://claude.com/claude-code) skill at `.claude/skills/hotel-search/`. Open the repo in Claude Code and ask in plain language — "find hotels near 240 S Taaffe St for Sep 19-30, 2 adults" — and it gathers the inputs, runs the pipeline, and summarizes the picks. The skill is optional; the CLI above works on its own.

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
