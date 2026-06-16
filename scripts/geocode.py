# ABOUTME: Geocode an address to coordinates via SerpAPI's Google Maps engine.
# ABOUTME: Accurate (matches Google Maps), used to anchor dashboard start points.
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.parse
import urllib.request

from envutil import load_env, require

ENDPOINT = "https://serpapi.com/search.json"


def geocode(address: str, api_key: str) -> tuple[float, float, str]:
    """Return (lat, lon, resolved_address) for an address. Fails loud if not found."""
    params = {"engine": "google_maps", "q": address, "type": "search", "api_key": api_key}
    url = ENDPOINT + "?" + urllib.parse.urlencode(params)
    try:
        data = json.loads(urllib.request.urlopen(url, timeout=60).read())
    except urllib.error.HTTPError as e:
        sys.exit(f"FATAL: SerpAPI HTTP {e.code} geocoding '{address}': {e.read().decode(errors='replace')[:300]}")
    except urllib.error.URLError as e:
        sys.exit(f"FATAL: SerpAPI request failed geocoding '{address}': {e.reason}")

    pr = data.get("place_results")
    if pr and pr.get("gps_coordinates"):
        g = pr["gps_coordinates"]
        return g["latitude"], g["longitude"], pr.get("address", address)
    lr = data.get("local_results") or []
    if lr and lr[0].get("gps_coordinates"):
        g = lr[0]["gps_coordinates"]
        return g["latitude"], g["longitude"], lr[0].get("address", address)
    sys.exit(
        f"FATAL: could not geocode '{address}' — no coordinates returned. "
        "Try a more specific address (include city + state/country)."
    )


def main() -> None:
    import argparse

    ap = argparse.ArgumentParser(description="Geocode an address via Google/SerpAPI -> JSON")
    ap.add_argument("address")
    args = ap.parse_args()
    key = require(load_env(), "SERPAPI_API_KEY")
    lat, lon, addr = geocode(args.address, key)
    print(json.dumps({"address": addr, "lat": lat, "lon": lon}, ensure_ascii=False))


if __name__ == "__main__":
    main()
