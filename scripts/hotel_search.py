# ABOUTME: Searches hotels via SerpAPI's Google Hotels engine, prints trimmed JSON to stdout.
# ABOUTME: Used by the hotel-search pipeline to get live, date-specific prices for comparison.
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from envutil import load_env, require

ENDPOINT = "https://serpapi.com/search.json"

# Fields we keep from each property — enough for the Claude session to rank/compare,
# without dumping the full multi-KB SerpAPI payload per hotel.
KEEP_FIELDS = (
    "name",
    "type",
    "description",
    "gps_coordinates",
    "check_in_time",
    "check_out_time",
    "rate_per_night",
    "total_rate",
    "prices",
    "hotel_class",
    "extracted_hotel_class",
    "overall_rating",
    "reviews",
    "location_rating",
    "amenities",
    "nearby_places",
    "link",
)


def trim(prop: dict) -> dict:
    return {k: prop[k] for k in KEEP_FIELDS if k in prop}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Google Hotels search via SerpAPI -> trimmed JSON on stdout"
    )
    parser.add_argument("query", help='e.g. "hotels near Sagrada Familia Barcelona"')
    parser.add_argument("--check-in", required=True, help="YYYY-MM-DD")
    parser.add_argument("--check-out", required=True, help="YYYY-MM-DD")
    parser.add_argument("--adults", type=int, default=2)
    parser.add_argument("--children", type=int, default=0)
    parser.add_argument("--currency", default="USD")
    parser.add_argument("--gl", default="us", help="country code for Google locale")
    parser.add_argument("--hl", default="en", help="language code for Google locale")
    parser.add_argument(
        "--max", type=int, default=20, help="max properties to keep in output"
    )
    parser.add_argument(
        "--sort",
        default=None,
        choices=["3", "8", "13"],
        help="SerpAPI sort_by: 3=lowest price, 8=highest rating, 13=most reviewed",
    )
    parser.add_argument("--min-price", type=int, default=None)
    parser.add_argument("--max-price", type=int, default=None)
    parser.add_argument("--out", default=None, help="also write raw JSON to this path")
    args = parser.parse_args()

    env = load_env()
    api_key = require(env, "SERPAPI_API_KEY")

    params = {
        "engine": "google_hotels",
        "q": args.query,
        "check_in_date": args.check_in,
        "check_out_date": args.check_out,
        "adults": args.adults,
        "children": args.children,
        "currency": args.currency,
        "gl": args.gl,
        "hl": args.hl,
        "api_key": api_key,
    }
    if args.sort:
        params["sort_by"] = args.sort
    if args.min_price is not None:
        params["min_price"] = args.min_price
    if args.max_price is not None:
        params["max_price"] = args.max_price

    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(url, timeout=60) as resp:
            data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        sys.exit(
            f"FATAL: SerpAPI HTTP {e.code}: {e.read().decode(errors='replace')[:500]}"
        )
    except urllib.error.URLError as e:
        sys.exit(f"FATAL: SerpAPI request failed: {e.reason}")

    if "error" in data:
        sys.exit(f"FATAL: SerpAPI error: {data['error']}")

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)

    properties = data.get("properties", [])
    trimmed = [trim(p) for p in properties[: args.max]]
    output = {
        "query": args.query,
        "check_in": args.check_in,
        "check_out": args.check_out,
        "currency": args.currency,
        "total_found": len(properties),
        "returned": len(trimmed),
        "properties": trimmed,
    }
    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
