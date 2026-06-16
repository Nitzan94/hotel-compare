# ABOUTME: One command: geocode start address(es), search hotels, build the dashboard.
# ABOUTME: The global entry point — anyone passes their own start address and dates.
from __future__ import annotations

import argparse
import datetime as dt
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


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Search hotels near a place and build a comparison dashboard, "
        "anchored to one or more start addresses (geocoded via Google)."
    )
    ap.add_argument("--location", required=True,
                    help='where to search, e.g. "downtown Sunnyvale California"')
    ap.add_argument("--start", action="append", required=True, metavar="ADDRESS",
                    help="start address (repeatable; first is primary). e.g. \"240 S Taaffe St, Sunnyvale, CA\"")
    ap.add_argument("--check-in", required=True, help="YYYY-MM-DD")
    ap.add_argument("--check-out", required=True, help="YYYY-MM-DD")
    ap.add_argument("--adults", type=int, default=2)
    ap.add_argument("--children", type=int, default=0)
    ap.add_argument("--currency", default="USD")
    ap.add_argument("--max", type=int, default=30, help="max hotels to fetch")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--no-route", action="store_true",
                    help="skip walk/drive routing (faster, straight-line distance only)")
    args = ap.parse_args()

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
    search_json = out_dir / "search.json"
    print(f"\nSearching hotels: {args.location} | {args.check_in}..{args.check_out} | "
          f"{args.adults} adults")
    with search_json.open("w") as f:
        subprocess.run(
            [sys.executable, str(SCRIPTS / "hotel_search.py"), args.location,
             "--check-in", args.check_in, "--check-out", args.check_out,
             "--adults", str(args.adults), "--children", str(args.children),
             "--currency", args.currency, "--max", str(args.max),
             "--out", str(out_dir / "raw.json")],
            stdout=f, check=True,
        )

    # 3) build the dashboard, anchored to the geocoded start(s)
    party = f"Room ({args.adults} guests)" if not args.children else \
        f"Room ({args.adults}a+{args.children}c)"
    cmd = [sys.executable, str(SCRIPTS / "hotel_dashboard.py"),
           "--out-dir", str(out_dir), "--location", args.location,
           "--check-in", args.check_in, "--check-out", args.check_out,
           "--nights", str(nights), "--currency", args.currency]
    for label, lat, lon in starts:
        cmd += ["--start", label, str(lat), str(lon)]
    cmd += ["--party", party, str(search_json)]
    if not args.no_route:
        cmd += ["--route"]
    print("\nBuilding dashboard...")
    subprocess.run(cmd, check=True)

    print(f"\nDone. Open: {out_dir / 'dashboard.html'}")


if __name__ == "__main__":
    main()
