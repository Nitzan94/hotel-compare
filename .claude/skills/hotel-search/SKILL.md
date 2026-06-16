---
name: hotel-search
description: Hotel search and comparison — takes a location, a start address, check-in/check-out dates, and party size; fetches live Google Hotels prices via SerpAPI, geocodes the start point, and builds a professional HTML dashboard (sortable table, map, price-vs-distance chart) with real walk/drive times and booking links. Use when the user wants to find hotels near somewhere, compare prices, or says "find hotels in/near X" / "compare hotel prices for these dates".
---

# Hotel Search & Compare

Input: a search location, one or more start addresses, check-in/check-out dates, party size.
Output: `runs/hotel-search/<YYYY-MM-DD>-<slug>/` with `dashboard.html`, `hotels.csv`, `search.json`, `raw.json`.

## Steps

1. **Gather inputs**, asking only for what's missing:
   - **Location** — where to search (city / neighborhood / landmark), e.g. "downtown Sunnyvale California".
   - **Start address** — the point to measure distance from. A real address ("240 S Taaffe St, Sunnyvale, CA"), geocoded via Google. Repeatable for multiple reference points; the first is primary. Never hand-enter coordinates — a start off by even 0.3 mi corrupts every walk/drive number.
   - **Dates** — check-in and check-out (YYYY-MM-DD). Google Hotels requires both; never guess them.
   - **Party** — adults (default 2), children (default 0). Currency defaults to USD.

2. **Run the pipeline** (deterministic — geocodes start, searches, builds dashboard):
   ```
   uv run scripts/hotel_compare.py \
     --location "<location>" \
     --start "<start address>" \
     --check-in YYYY-MM-DD --check-out YYYY-MM-DD \
     --adults N
   ```
   Pass `--start` again for more reference points, `--no-route` to skip walk/drive routing,
   `--currency` / `--children` / `--max` as needed. It prints the dashboard path.

3. **Open and report.** Open the printed `dashboard.html`. Summarize from `hotels.csv`:
   N hotels for the dates, room-price range, and the top 2-3 picks (cheapest, closest, best value)
   with the one specific reason each wins. Note any non-hotel listings the run hid.

## What the dashboard contains

- Sortable table: distance from each start, walk/drive minutes, class, rating, room price + total, value score, booking + directions links.
- Compare panel: tick 1-3 rows for a side-by-side card (price, total, distance, walk/drive, class, rating, reviews, value, amenities, book links) with the best cell per attribute highlighted.
- Leaflet map (hotels + start points) and a price-vs-distance scatter.
- Booking deep links (Google / Booking.com / Expedia) and 🚶/🚗 Google Maps directions links from the viewer's live location.

## Rules

- **Prices are date-specific and live.** Always echo dates and party size. If dates change, re-run — never reuse prior prices.
- **Geocode start points via Google** (`hotel_compare.py` does this through `geocode.py`). Accuracy of the start coordinate is the single thing that makes walk/drive times match Google Maps.
- **Walk/drive are OSRM estimates** (free), accurate to ~2 min from a correctly geocoded start. The 🚶/🚗 Maps links give the exact Google time on tap.
- **Hotels only by default.** Vacation-rental / aggregator listings are filtered (they carry bad pins); they're named in the dashboard footer. `--include-rentals` (on `hotel_dashboard.py`) keeps them.
- No fabricated hotels, prices, or distances. If SerpAPI returns nothing, report the gap.
