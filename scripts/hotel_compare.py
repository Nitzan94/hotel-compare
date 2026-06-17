# ABOUTME: One command: geocode start address(es), search hotels, build the dashboard.
# ABOUTME: The global entry point — anyone passes their own start address and dates.
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path

from envutil import load_env, require
from geocode import geocode

SCRIPTS = Path(__file__).resolve().parent
REPO_ROOT = SCRIPTS.parent


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")[:40] or "run"


def build_dashboard(out_dir, location, check_in, check_out, nights, currency,
                    starts, party, route, search_json):
    """Invoke hotel_dashboard.py. Local work + free OSRM routing only — no paid API calls."""
    cmd = [sys.executable, str(SCRIPTS / "hotel_dashboard.py"),
           "--out-dir", str(out_dir), "--location", location,
           "--check-in", check_in, "--check-out", check_out,
           "--nights", str(nights), "--currency", currency]
    for label, lat, lon in starts:
        cmd += ["--start", label, str(lat), str(lon)]
    cmd += ["--party", party, str(search_json)]
    if route:
        cmd += ["--route"]
    subprocess.run(cmd, check=True)


def rebuild_from(run_dir: Path) -> None:
    """Regenerate the dashboard from a saved run (run.json + search.json). No API credits."""
    recipe = run_dir / "run.json"
    if not recipe.exists():
        sys.exit(f"FATAL: no run.json in {run_dir} — only runs created with the current "
                 "hotel_compare.py can be rebuilt. Run a fresh search once to create it.")
    r = json.loads(recipe.read_text())
    search_json = run_dir / r.get("search_json", "search.json")
    if not search_json.exists():
        sys.exit(f"FATAL: saved search data missing: {search_json}")
    print(f"Rebuilding from {run_dir} (no API calls)...")
    build_dashboard(run_dir, r["location"], r["check_in"], r["check_out"], r["nights"],
                    r["currency"], [tuple(s) for s in r["starts"]], r["party"],
                    r["route"], search_json)
    print(f"\nDone. Open: {run_dir / 'dashboard.html'}")


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Search hotels near a place and build a comparison dashboard, "
        "anchored to one or more start addresses (geocoded via Google)."
    )
    ap.add_argument("--rebuild", metavar="DIR",
                    help="rebuild the dashboard from a saved run dir (reads run.json + "
                    "search.json; no API calls). Skips all search flags below.")
    ap.add_argument("--location",
                    help='where to search, e.g. "downtown Sunnyvale California"')
    ap.add_argument("--start", action="append", metavar="ADDRESS",
                    help="start address (repeatable; first is primary). e.g. \"240 S Taaffe St, Sunnyvale, CA\"")
    ap.add_argument("--check-in", help="YYYY-MM-DD")
    ap.add_argument("--check-out", help="YYYY-MM-DD")
    ap.add_argument("--adults", type=int, default=2)
    ap.add_argument("--children", type=int, default=0)
    ap.add_argument("--currency", default="USD")
    ap.add_argument("--max", type=int, default=30, help="max hotels to fetch")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--no-route", action="store_true",
                    help="skip walk/drive routing (faster, straight-line distance only)")
    args = ap.parse_args()

    # Free path: rebuild a saved run, no geocode/search calls.
    if args.rebuild:
        rebuild_from(Path(args.rebuild))
        return

    missing = [n for n, v in (("--location", args.location), ("--start", args.start),
               ("--check-in", args.check_in), ("--check-out", args.check_out)) if not v]
    if missing:
        ap.error("required (unless --rebuild): " + ", ".join(missing))

    try:
        ci = dt.date.fromisoformat(args.check_in)
        co = dt.date.fromisoformat(args.check_out)
    except ValueError:
        sys.exit("FATAL: --check-in/--check-out must be YYYY-MM-DD")
    nights = (co - ci).days
    if nights < 1:
        sys.exit(f"FATAL: check-out must be after check-in (got {nights} nights)")

    key = require(load_env(), "SERPAPI_API_KEY")

    out_dir = Path(args.out_dir) if args.out_dir else (
        REPO_ROOT / "runs" / "hotel-search" / f"{dt.date.today().isoformat()}-{slugify(args.location)}"
    )
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1) geocode every start address (accurate, matches Google Maps)
    print("Geocoding start point(s):")
    starts: list[tuple[str, float, float]] = []
    for addr in args.start:
        lat, lon, resolved = geocode(addr, key)
        label = addr.split(",")[0].strip() or resolved
        starts.append((label, lat, lon))
        print(f"  {label}: {lat}, {lon}  ({resolved})")

    # 2) search hotels (stdout -> search.json, raw payload -> raw.json)
    # Google Hotels returns a tighter, more local set when the query names "hotels".
    # Without it, "downtown Sunnyvale" pulls in a broader regional set (even other cities).
    query = args.location if "hotel" in args.location.lower() else f"hotels in {args.location}"
    search_json = out_dir / "search.json"
    print(f"\nSearching hotels: {query} | {args.check_in}..{args.check_out} | "
          f"{args.adults} adults")
    with search_json.open("w") as f:
        subprocess.run(
            [sys.executable, str(SCRIPTS / "hotel_search.py"), query,
             "--check-in", args.check_in, "--check-out", args.check_out,
             "--adults", str(args.adults), "--children", str(args.children),
             "--currency", args.currency, "--max", str(args.max),
             "--out", str(out_dir / "raw.json")],
            stdout=f, check=True,
        )

    # 3) save the rebuild recipe so the dashboard can be regenerated later for free
    party = f"Room ({args.adults} guests)" if not args.children else \
        f"Room ({args.adults}a+{args.children}c)"
    route = not args.no_route
    (out_dir / "run.json").write_text(json.dumps({
        "location": args.location, "check_in": args.check_in, "check_out": args.check_out,
        "nights": nights, "currency": args.currency, "party": party, "route": route,
        "starts": [[label, lat, lon] for label, lat, lon in starts],
        "search_json": "search.json",
    }, indent=2, ensure_ascii=False), encoding="utf-8")

    # 4) build the dashboard, anchored to the geocoded start(s)
    print("\nBuilding dashboard...")
    build_dashboard(out_dir, args.location, args.check_in, args.check_out, nights,
                    args.currency, starts, party, route, search_json)

    print(f"\nDone. Open: {out_dir / 'dashboard.html'}")


if __name__ == "__main__":
    main()
