# ABOUTME: Merges hotel_search JSON runs, computes distance from one or more start
# ABOUTME: points, and emits a self-contained HTML dashboard (table + scatter + map) + CSV.
from __future__ import annotations

import argparse
import csv
import json
import math
import sys
import time
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

OSRM_BASE = "https://routing.openstreetmap.de/routed-{profile}/route/v1/driving"


def osrm_route(profile: str, slon, slat, hlon, hlat) -> dict | None:
    """Real road distance/duration from (slon,slat) to (hlon,hlat). profile: foot|car."""
    url = f"{OSRM_BASE.format(profile=profile)}/{slon},{slat};{hlon},{hlat}?overview=false"
    req = urllib.request.Request(url, headers={"User-Agent": "hotel-compare/1.0"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    rt = data["routes"][0]
    return {"mi": round(rt["distance"] / 1609.34, 2), "min": round(rt["duration"] / 60)}


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return r * 2 * math.asin(math.sqrt(a))


def best_walk(nearby: list) -> str:
    for place in nearby or []:
        for t in place.get("transportations", []):
            if t.get("type") == "Walking":
                return f"{t.get('duration','')} to {place.get('name','')}"
    return ""


AMENITY_KEYS = (
    "Free Wi-Fi", "Free wifi", "Free parking", "Free breakfast", "Breakfast",
    "Pool", "Fitness", "Air conditioning", "Pet-friendly", "Hot tub", "Spa",
    "Restaurant", "Airport shuttle", "Kitchen", "Bar",
)


def amenity_chips(amenities: list) -> list[str]:
    out: list[str] = []
    for a in amenities or []:
        for key in AMENITY_KEYS:
            if key.lower() in a.lower() and a not in out:
                out.append(a)
                break
    return out[:6]


def load_party(path: Path) -> dict[str, dict]:
    data = json.loads(path.read_text())
    return {p["name"]: p for p in data.get("properties", [])}


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Build an HTML hotel comparison dashboard from hotel_search runs."
    )
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--location", required=True, help="e.g. Downtown Sunnyvale")
    ap.add_argument("--check-in", required=True)
    ap.add_argument("--check-out", required=True)
    ap.add_argument("--nights", type=int, required=True)
    ap.add_argument("--currency", default="USD")
    # repeated: --start "Label" LAT LON   (first one is primary: drives sort + value)
    ap.add_argument(
        "--start", action="append", nargs=3, metavar=("LABEL", "LAT", "LON"),
        required=True,
    )
    # repeated: --party "Label" path.json  (use one for by-room pricing)
    ap.add_argument(
        "--party", action="append", nargs=2, metavar=("LABEL", "FILE"), required=True,
    )
    ap.add_argument(
        "--route", action="store_true",
        help="fetch walking + driving time estimates from the primary start (OSRM, free, no key)",
    )
    ap.add_argument(
        "--include-rentals", action="store_true",
        help="keep vacation-rental / aggregator listings (default: hotels only)",
    )
    args = ap.parse_args()

    starts = [
        {"label": lb, "lat": float(la), "lon": float(lo)} for lb, la, lo in args.start
    ]
    primary_start = starts[0]

    parties = [(label, load_party(Path(f))) for label, f in args.party]
    party_labels = [label for label, _ in parties]
    primary_party = party_labels[-1]

    names: list[str] = []
    for _, m in parties:
        for n in m:
            if n not in names:
                names.append(n)

    rows = []
    hidden = []
    for name in names:
        base = next((m[name] for _, m in parties if name in m), None)
        if not args.include_rentals and base.get("type") != "hotel":
            hidden.append({"name": name, "type": base.get("type", "?")})
            continue
        gps = base.get("gps_coordinates") or {}
        lat, lon = gps.get("latitude"), gps.get("longitude")

        distances = {}
        for s in starts:
            if lat is not None and lon is not None:
                km = haversine_km(s["lat"], s["lon"], lat, lon)
                distances[s["label"]] = {"km": round(km, 2), "mi": round(km * 0.621371, 2)}
            else:
                distances[s["label"]] = {"km": None, "mi": None}

        prices = {}
        for label, m in parties:
            p = m.get(name)
            prices[label] = {
                "per_night": (p.get("rate_per_night") or {}).get("extracted_lowest") if p else None,
                "total": (p.get("total_rate") or {}).get("extracted_lowest") if p else None,
            }

        rows.append({
            "name": name,
            "stars": base.get("extracted_hotel_class"),
            "rating": base.get("overall_rating"),
            "reviews": base.get("reviews"),
            "lat": lat,
            "lon": lon,
            "distances": distances,
            "walk": best_walk(base.get("nearby_places")),
            "amenities": amenity_chips(base.get("amenities")),
            "link": base.get("link", ""),
            "type": base.get("type", ""),
            "prices": prices,
        })

    # --- optional real walking/driving routes from the primary start (free OSRM) ---
    if args.route:
        ok, failures = 0, []
        for r in rows:
            if r["lat"] is None or r["lon"] is None:
                r["route"] = None
                continue
            try:
                walk = osrm_route("foot", primary_start["lon"], primary_start["lat"], r["lon"], r["lat"])
                drive = osrm_route("car", primary_start["lon"], primary_start["lat"], r["lon"], r["lat"])
                r["route"] = {"walk": walk, "drive": drive}
                ok += 1
            except (urllib.error.URLError, TimeoutError, OSError) as e:
                r["route"] = None
                failures.append(f"{r['name']}: {e}")
            time.sleep(0.1)  # be polite to the public routing server
        if ok == 0:
            sys.exit(
                "FATAL: routing server unreachable for every hotel "
                f"({OSRM_BASE}). First error: {failures[0] if failures else 'unknown'}. "
                "Re-run without --route to skip routing."
            )
        if failures:
            print(f"WARNING: routing failed for {len(failures)} hotel(s):", file=sys.stderr)
            for f in failures:
                print(f"  - {f}", file=sys.stderr)
    else:
        for r in rows:
            r["route"] = None

    def pn(r):
        return r["prices"].get(primary_party, {}).get("per_night")

    def pdist(r):
        return r["distances"].get(primary_start["label"], {}).get("km")

    # value score: rating per $100/night, lightly distance-penalized
    for r in rows:
        p, rt, d = pn(r), r["rating"], pdist(r)
        r["value_score"] = round((rt / (p / 100.0)) - (d or 0) * 0.15, 2) if p and rt else None

    badges = {r["name"]: [] for r in rows}
    priced = [r for r in rows if pn(r)]
    if priced:
        badges[min(priced, key=pn)["name"]].append("cheapest")
    mappable = [r for r in rows if pdist(r) is not None]
    if mappable:
        badges[min(mappable, key=pdist)["name"]].append("closest")
    rated = [r for r in rows if r["rating"]]
    if rated:
        badges[max(rated, key=lambda r: (r["rating"], r["reviews"] or 0))["name"]].append("top-rated")
    valued = [r for r in rows if r["value_score"] is not None]
    if valued:
        badges[max(valued, key=lambda r: r["value_score"])["name"]].append("best-value")
    for r in rows:
        r["badges"] = badges[r["name"]]

    rows.sort(key=lambda r: (pdist(r) if pdist(r) is not None else 1e9, pn(r) or 1e9))

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # --- CSV ---
    csv_path = out_dir / "hotels.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        header = ["name", "stars", "rating", "reviews"]
        for s in starts:
            header.append(f"dist_mi ({s['label']})")
        if args.route:
            header += [
                f"walk_min (from {primary_start['label']})",
                f"walk_mi (from {primary_start['label']})",
                f"drive_min (from {primary_start['label']})",
            ]
        for label in party_labels:
            header += [f"{label} $/night", f"{label} total ({args.nights}n)"]
        header += ["value_score", "badges", "lat", "lon", "link"]
        w.writerow(header)
        for r in rows:
            row = [r["name"], r["stars"], r["rating"], r["reviews"]]
            for s in starts:
                row.append(r["distances"][s["label"]]["mi"])
            if args.route:
                rt = r.get("route") or {}
                walk, drive = rt.get("walk") or {}, rt.get("drive") or {}
                row += [walk.get("min"), walk.get("mi"), drive.get("min")]
            for label in party_labels:
                row += [r["prices"][label]["per_night"], r["prices"][label]["total"]]
            row += [r["value_score"], "|".join(r["badges"]), r["lat"], r["lon"], r["link"]]
            w.writerow(row)

    # --- HTML ---
    meta = {
        "location": args.location,
        "starts": starts,
        "check_in": args.check_in,
        "check_out": args.check_out,
        "nights": args.nights,
        "currency": args.currency,
        "party_labels": party_labels,
        "primary_party": primary_party,
        "primary_start": primary_start["label"],
        "routed": bool(args.route),
        "hidden": hidden,
    }
    payload = json.dumps({"meta": meta, "rows": rows}, ensure_ascii=False)
    html = HTML_TEMPLATE.replace("/*__DATA__*/", payload)
    html = html.replace("__TITLE__", escape(f"Hotels — {args.location}"))
    (out_dir / "dashboard.html").write_text(html, encoding="utf-8")

    print(f"Wrote {csv_path}")
    print(f"Wrote {out_dir / 'dashboard.html'}")
    print(f"{len(rows)} hotels | starts: {', '.join(s['label'] for s in starts)} "
          f"| parties: {', '.join(party_labels)}")
    if hidden:
        print(f"Hid {len(hidden)} non-hotel listing(s): "
              f"{', '.join(h['name'] + ' [' + h['type'] + ']' for h in hidden)}")


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__TITLE__</title>
<script src="https://cdn.tailwindcss.com"></script>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
  body { font-feature-settings:"tnum"; }
  th.sortable { cursor:pointer; user-select:none; }
  th.sortable:hover { color:#2563eb; }
  .badge { font-size:10px; font-weight:600; padding:1px 6px; border-radius:9999px; }
  #map { height:420px; border-radius:0.5rem; z-index:0; }
  .ota { font-size:11px; padding:2px 6px; border-radius:4px; white-space:nowrap; }
</style>
</head>
<body class="bg-slate-50 text-slate-800">
<div class="max-w-7xl mx-auto px-4 py-8">
  <header class="mb-6">
    <h1 id="h-title" class="text-2xl font-bold text-slate-900"></h1>
    <p id="h-sub" class="text-sm text-slate-500 mt-1"></p>
  </header>

  <section id="cards" class="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6"></section>

  <div class="grid lg:grid-cols-2 gap-4 mb-6">
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
      <h2 class="font-semibold text-slate-700 mb-2">Map</h2>
      <div id="map"></div>
      <p class="text-xs text-slate-400 mt-1">★ = start points · dots = hotels (color = rating, size = reviews). Click a marker for price + booking links.</p>
    </section>
    <section class="bg-white rounded-xl shadow-sm border border-slate-200 p-4">
      <h2 class="font-semibold text-slate-700 mb-2">Price vs. distance</h2>
      <div id="scatter"></div>
      <p class="text-xs text-slate-400 mt-1">X = miles from primary start · Y = room/night · dot size = reviews · color = rating (red→green)</p>
    </section>
  </div>

  <section class="bg-white rounded-xl shadow-sm border border-slate-200 overflow-hidden">
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead id="thead" class="bg-slate-100 text-slate-600 text-xs uppercase tracking-wide"></thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </section>

  <footer class="text-xs text-slate-400 mt-4 leading-relaxed">
    <p><b>Room price</b> is per room for the stated dates (rates are per-room, so 1 vs 2 guests is usually identical).</p>
    <p><b>Booking links</b> open each hotel's page on Google / Booking.com / Expedia for these dates — they are deep links, not scraped live OTA prices.</p>
    <p><b>Value score</b> = guest rating per $100/night, lightly penalized by distance. A heuristic, not gospel.</p>
    <p id="params" class="mt-1"></p>
    <p class="mt-1">Source: Google Hotels via SerpAPI · map © OpenStreetMap contributors.</p>
  </footer>
</div>

<script>
const DATA = /*__DATA__*/;
const M = DATA.meta, ROWS = DATA.rows;
const cur = M.currency === 'USD' ? '$' : (M.currency + ' ');
const fmt = n => n==null ? '—' : cur + n.toLocaleString();
const enc = encodeURIComponent;
const primary = M.primary_party;
const pStart = M.primary_start;
const pn = r => (r.prices[primary]||{}).per_night;
const tot = r => (r.prices[primary]||{}).total;
const distMi = (r,label) => ((r.distances[label]||{}).mi);
const pdistMi = r => distMi(r, pStart);

document.getElementById('h-title').textContent = 'Hotels — ' + M.location;
document.getElementById('h-sub').textContent =
  `${M.check_in} → ${M.check_out} (${M.nights} nights) · ${ROWS.length} hotels · room price · start: ${pStart}`;
document.getElementById('params').textContent =
  `Search: engine=google_hotels · q="hotels in ${M.location}" · check_in=${M.check_in} · check_out=${M.check_out} · adults=2 · currency=${M.currency} · gl=us · hl=en`;
if(M.routed){const rn=document.createElement('p');rn.className='mt-1';
  rn.innerHTML=`<b>Walk* / Drive*</b> = <i>estimates</i> from <b>${pStart}</b> via OpenStreetMap (OSRM) — approximate, for ranking. For the exact time from where you are now, tap a <b>🚶/🚗 Maps</b> Directions link: it opens Google Maps routed from your device's live location (matches your phone).`;
  document.getElementById('params').after(rn);}
if(M.hidden&&M.hidden.length){const hn=document.createElement('p');hn.className='mt-1 text-amber-600';
  hn.innerHTML=`<b>${M.hidden.length} non-hotel listing(s) hidden</b> (vacation-rental / aggregator entries from Google Hotels): ${M.hidden.map(h=>h.name+' ['+h.type+']').join(', ')}. Re-run with --include-rentals to show them.`;
  document.getElementById('params').after(hn);}

// ---- OTA deep links ----
function ota(r){
  const ci=M.check_in, co=M.check_out, q=enc(r.name+' '+M.location);
  return {
    Google: r.link || `https://www.google.com/travel/search?q=${q}`,
    Booking: `https://www.booking.com/searchresults.html?ss=${enc(r.name)}&checkin=${ci}&checkout=${co}&group_adults=2&no_rooms=1`,
    Expedia: `https://www.expedia.com/Hotel-Search?destination=${enc(r.name)}&startDate=${ci}&endDate=${co}&adults=2`,
  };
}
const otaColor = {Google:'bg-blue-600', Booking:'bg-indigo-600', Expedia:'bg-amber-600'};

// Google Maps directions from YOUR live location (origin omitted -> device location).
// On a phone this matches the app exactly. Free, no API key.
function gmapsDir(r, mode){
  return `https://www.google.com/maps/dir/?api=1&destination=${r.lat},${r.lon}&travelmode=${mode}`;
}

// ---- summary cards ----
const priced = ROWS.filter(r => pn(r)!=null);
const cheapest = priced.length ? priced.reduce((a,b)=> pn(a)<pn(b)?a:b) : null;
const mappable = ROWS.filter(r=>pdistMi(r)!=null);
const closest = mappable.length ? mappable.reduce((a,b)=> pdistMi(a)<pdistMi(b)?a:b) : null;
const rated = ROWS.filter(r=>r.rating);
const topRated = rated.length ? rated.reduce((a,b)=> (a.rating>b.rating||(a.rating===b.rating&&(a.reviews||0)>(b.reviews||0)))?a:b) : null;
const lo = priced.length ? Math.min(...priced.map(pn)) : null;
const hi = priced.length ? Math.max(...priced.map(pn)) : null;
const card = (label,val,sub,color)=>`<div class="bg-white rounded-xl shadow-sm border border-slate-200 p-3">
  <div class="text-[11px] uppercase tracking-wide text-slate-400">${label}</div>
  <div class="text-lg font-bold ${color||'text-slate-900'} leading-tight mt-0.5">${val}</div>
  <div class="text-xs text-slate-500 truncate">${sub||''}</div></div>`;
document.getElementById('cards').innerHTML = [
  card('Room/night range', lo!=null? fmt(lo)+'–'+fmt(hi):'—', priced.length+' priced'),
  card('Cheapest', cheapest?fmt(pn(cheapest)):'—', cheapest?cheapest.name:'', 'text-emerald-600'),
  card('Closest', closest?pdistMi(closest)+' mi':'—', closest?closest.name:'', 'text-blue-600'),
  card('Top rated', topRated?topRated.rating+'★':'—', topRated?topRated.name:'', 'text-amber-600'),
].join('');

function ratingColor(r){
  if(r==null) return '#94a3b8';
  const t=Math.max(0,Math.min(1,(r-3.5)/1.5));
  return `hsl(${t*120},70%,45%)`;
}

// ---- map ----
(function(){
  const pts = ROWS.filter(r=>r.lat!=null && r.lon!=null);
  const allLat=[...pts.map(p=>p.lat), ...M.starts.map(s=>s.lat)];
  const allLon=[...pts.map(p=>p.lon), ...M.starts.map(s=>s.lon)];
  const map=L.map('map');
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
    {maxZoom:19, attribution:'© OpenStreetMap'}).addTo(map);
  const rMax=Math.max(...pts.map(p=>p.reviews||0),1);
  pts.forEach(p=>{
    const radius=6+Math.sqrt((p.reviews||0)/rMax)*16;
    const links=ota(p);
    const linkHtml=Object.entries(links).map(([k,u])=>`<a href="${u}" target="_blank" style="color:#2563eb">${k}</a>`).join(' · ');
    const dirHtml=`<a href="${gmapsDir(p,'walking')}" target="_blank" style="color:#059669">🚶 Maps</a> · <a href="${gmapsDir(p,'driving')}" target="_blank" style="color:#475569">🚗 Maps</a>`;
    const wk=(p.route&&p.route.walk)||{}, dv=(p.route&&p.route.drive)||{};
    const routeHtml=M.routed&&(wk.min!=null||dv.min!=null)
      ? `<br>🚶 ${wk.min!=null?wk.min+' min':'—'}${wk.mi!=null?` (${wk.mi} mi)`:''} · 🚗 ${dv.min!=null?dv.min+' min':'—'}` : '';
    L.circleMarker([p.lat,p.lon],{radius,color:'#fff',weight:1,fillColor:ratingColor(p.rating),fillOpacity:0.8})
     .addTo(map)
     .bindPopup(`<b>${p.name}</b><br>${p.rating||'?'}★ (${(p.reviews||0).toLocaleString()})<br>${fmt(pn(p))}/night · ${pdistMi(p)??'?'} mi straight-line${routeHtml}<br>Directions: ${dirHtml}<br>Book: ${linkHtml}`);
  });
  M.starts.forEach((s,i)=>{
    L.marker([s.lat,s.lon],{title:s.label,
      icon:L.divIcon({className:'',html:`<div style="font-size:22px;line-height:22px;color:${i===0?'#dc2626':'#7c3aed'}">★</div>`,iconSize:[22,22],iconAnchor:[11,11]})})
     .addTo(map).bindPopup(`<b>Start:</b> ${s.label}`);
  });
  if(allLat.length){
    map.fitBounds([[Math.min(...allLat),Math.min(...allLon)],[Math.max(...allLat),Math.max(...allLon)]],{padding:[30,30]});
  }
})();

// ---- scatter ----
(function(){
  const W=620,H=320,pad={l:55,r:20,t:15,b:40};
  const pts=ROWS.filter(r=>pdistMi(r)!=null && pn(r)!=null);
  if(!pts.length){document.getElementById('scatter').innerHTML='<p class="text-sm text-slate-400">No mappable points.</p>';return;}
  const xs=pts.map(p=>pdistMi(p)), ys=pts.map(p=>pn(p));
  const xMax=Math.max(...xs)*1.05||1, yMin=Math.min(...ys)*0.9, yMax=Math.max(...ys)*1.05;
  const rMax=Math.max(...pts.map(p=>p.reviews||0),1);
  const X=v=>pad.l+(v/xMax)*(W-pad.l-pad.r);
  const Y=v=>H-pad.b-((v-yMin)/(yMax-yMin))*(H-pad.t-pad.b);
  const R=v=>4+Math.sqrt(v/rMax)*13;
  let g=`<svg viewBox="0 0 ${W} ${H}" class="w-full" style="max-height:340px">`;
  for(let i=0;i<=4;i++){const gy=pad.t+i*(H-pad.t-pad.b)/4, val=yMax-(i/4)*(yMax-yMin);
    g+=`<line x1="${pad.l}" y1="${gy}" x2="${W-pad.r}" y2="${gy}" stroke="#eef2f7"/><text x="${pad.l-8}" y="${gy+4}" text-anchor="end" font-size="10" fill="#94a3b8">${cur}${Math.round(val)}</text>`;}
  for(let i=0;i<=5;i++){const gx=pad.l+i*(W-pad.l-pad.r)/5, val=(i/5)*xMax;
    g+=`<line x1="${gx}" y1="${pad.t}" x2="${gx}" y2="${H-pad.b}" stroke="#f4f6fa"/><text x="${gx}" y="${H-pad.b+16}" text-anchor="middle" font-size="10" fill="#94a3b8">${val.toFixed(1)}mi</text>`;}
  pts.forEach(p=>{g+=`<circle cx="${X(pdistMi(p))}" cy="${Y(pn(p))}" r="${R(p.reviews||0)}" fill="${ratingColor(p.rating)}" fill-opacity="0.7" stroke="#fff" stroke-width="1"><title>${p.name}\n${p.rating||'?'}★ (${p.reviews||0})\n${fmt(pn(p))}/night · ${pdistMi(p)} mi</title></circle>`;});
  g+=`</svg>`;
  document.getElementById('scatter').innerHTML=g;
})();

// ---- table ----
const cols=[{k:'name',label:'Hotel',align:'left'}];
M.starts.forEach(s=>cols.push({k:'dist:'+s.label,label:s.label.split('(')[0].trim()+' (mi)',num:true}));
if(M.routed){cols.push({k:'walk_min',label:'Walk* (min)',num:true},{k:'drive_min',label:'Drive* (min)',num:true});}
cols.push({k:'stars',label:'Class',num:true},{k:'rating',label:'Rating',num:true},{k:'reviews',label:'Reviews',num:true});
M.party_labels.forEach(lb=>{cols.push({k:'pn:'+lb,label:'Room /night',num:true});cols.push({k:'tot:'+lb,label:'Total',num:true});});
cols.push({k:'value_score',label:'Value',num:true},{k:'directions',label:'Directions',align:'left'},{k:'book',label:'Book',align:'left'});

const getVal=(r,k)=>{
  if(k.startsWith('dist:')) return distMi(r,k.slice(5));
  if(k==='walk_min') return (r.route&&r.route.walk||{}).min;
  if(k==='drive_min') return (r.route&&r.route.drive||{}).min;
  if(k.startsWith('pn:')) return (r.prices[k.slice(3)]||{}).per_night;
  if(k.startsWith('tot:')) return (r.prices[k.slice(4)]||{}).total;
  return r[k];
};
let sortKey='dist:'+M.starts[0].label, sortDir=1;
function render(){
  const thead=document.getElementById('thead');
  thead.innerHTML='<tr>'+cols.map(c=>{const arrow=sortKey===c.k?(sortDir>0?' ▲':' ▼'):'';
    return `<th class="sortable px-3 py-2 ${c.align==='left'?'text-left':'text-right'}" data-k="${c.k}">${c.label}${arrow}</th>`;}).join('')+'</tr>';
  thead.querySelectorAll('th').forEach(th=>th.onclick=()=>{const k=th.dataset.k;
    if(sortKey===k) sortDir*=-1; else {sortKey=k;sortDir=1;} render();});
  const sorted=[...ROWS].sort((a,b)=>{let va=getVal(a,sortKey),vb=getVal(b,sortKey);
    if(typeof va==='string'||typeof vb==='string'){return ((va||'')+'').localeCompare((vb||'')+'')*sortDir;}
    va=va==null?Infinity*sortDir:va; vb=vb==null?Infinity*sortDir:vb; return (va-vb)*sortDir;});
  const badgeColor={cheapest:'bg-emerald-100 text-emerald-700','best-value':'bg-indigo-100 text-indigo-700',closest:'bg-blue-100 text-blue-700','top-rated':'bg-amber-100 text-amber-700'};
  document.getElementById('tbody').innerHTML=sorted.map((r,i)=>{
    const badges=(r.badges||[]).map(b=>`<span class="badge ${badgeColor[b]||'bg-slate-100 text-slate-600'}">${b}</span>`).join(' ');
    const am=(r.amenities||[]).slice(0,4).map(a=>`<span class="text-[10px] text-slate-400">${a}</span>`).join(' · ');
    let cells=`<td class="px-3 py-2 text-left"><div class="font-medium text-slate-800">${r.name} ${badges}</div>
      <div class="text-[11px] text-slate-400">${r.type||''}</div>${am?`<div class="mt-0.5">${am}</div>`:''}</td>`;
    M.starts.forEach(s=>{const d=distMi(r,s.label);
      cells+=`<td class="px-3 py-2 text-right ${d!=null&&d<0.6?'text-blue-600 font-semibold':''}">${d??'—'}</td>`;});
    if(M.routed){const wk=(r.route&&r.route.walk)||{}, dv=(r.route&&r.route.drive)||{};
      cells+=`<td class="px-3 py-2 text-right ${wk.min!=null&&wk.min<=15?'text-emerald-600 font-semibold':''}">${wk.min!=null?wk.min+(wk.mi!=null?` <span class="text-[10px] text-slate-400">${wk.mi}mi</span>`:''):'—'}</td>`;
      cells+=`<td class="px-3 py-2 text-right">${dv.min!=null?dv.min:'—'}</td>`;}
    cells+=`<td class="px-3 py-2 text-right">${r.stars?r.stars+'★':'—'}</td>`;
    cells+=`<td class="px-3 py-2 text-right">${r.rating??'—'}</td>`;
    cells+=`<td class="px-3 py-2 text-right text-slate-400">${r.reviews?r.reviews.toLocaleString():'—'}</td>`;
    M.party_labels.forEach(lb=>{const p=(r.prices[lb]||{});
      cells+=`<td class="px-3 py-2 text-right font-semibold">${fmt(p.per_night)}</td><td class="px-3 py-2 text-right text-slate-500">${fmt(p.total)}</td>`;});
    cells+=`<td class="px-3 py-2 text-right ${r.value_score!=null?'text-indigo-600 font-medium':''}">${r.value_score??'—'}</td>`;
    const dirBtns = `<a href="${gmapsDir(r,'walking')}" target="_blank" rel="noopener" class="ota bg-emerald-600 text-white hover:opacity-80" title="Walking directions from your location">🚶 Maps</a> `
      + `<a href="${gmapsDir(r,'driving')}" target="_blank" rel="noopener" class="ota bg-slate-600 text-white hover:opacity-80" title="Driving directions from your location">🚗 Maps</a>`;
    cells+=`<td class="px-3 py-2 text-left whitespace-nowrap">${dirBtns}</td>`;
    const links=ota(r); const linkBtns=Object.entries(links).map(([k,u])=>`<a href="${u}" target="_blank" rel="noopener" class="ota ${otaColor[k]} text-white hover:opacity-80">${k} ↗</a>`).join(' ');
    cells+=`<td class="px-3 py-2 text-left whitespace-nowrap">${linkBtns}</td>`;
    return `<tr class="border-t border-slate-100 ${i%2?'bg-slate-50/40':''} hover:bg-blue-50/40">${cells}</tr>`;
  }).join('');
}
render();
</script>
</body>
</html>"""


if __name__ == "__main__":
    main()
