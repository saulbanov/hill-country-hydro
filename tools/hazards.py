#!/usr/bin/env python3
"""
hazards.py — Storm and floodwater layer (official sources only).

Answers, per place and per hour: is there an official storm or flood notice
that should block or caution an outdoor or swimming plan? Two sources, both
free, keyless, and government-run:

  NWS alerts      https://api.weather.gov/alerts/active?area=TX
                  Warnings, watches, advisories with county codes and windows.
  NWS flood gauges https://api.water.noaa.gov/nwps/v1/gauges/{lid}
                  Observed stage vs. the official action/minor/moderate/major
                  flood categories at forecast points on Austin-area creeks.

Chain, in the austin-swim-map sense: raw capture (URL, time, sha256 kept) ->
normalize -> deterministic assess -> one JSON sidecar in the map's envelope.
No LLM, no inference of waterway connections: a gauge links to a place only
through the USGS station id the map already records for that place, and a
county links through the NWS points lookup of the place's own coordinates.

Commands (from the project directory):

  python3 hazards.py links   --holes ../../austin-swim-map/data/holes.json \
                             --gauges ../../austin-swim-map/data/gauges.json \
                             --out hazard-links.json        # rebuild link table
  python3 hazards.py assess  [--links hazard-links.json] [--out hazards-status.json]
                             [--fixture f.json | --save-fixture f.json] [--raw-dir DIR]
                             [--at 2026-09-28T20:00:00Z]

What this is NOT: a water-quality, access, or safety claim; a substitute for
the City's own closure pages; a forecast of creek flow. A "none found" result
means none found in the checked sources at the checked time.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UA = "austin-swim-map/0.1 (saul.elbein@gmail.com)"
NWS_ALERTS = "https://api.weather.gov/alerts/active"
NWS_POINTS = "https://api.weather.gov/points/{lat:.4f},{lon:.4f}"
NWPS_GAUGES = "https://api.water.noaa.gov/nwps/v1/gauges"
NWPS_GAUGE = "https://api.water.noaa.gov/nwps/v1/gauges/{lid}"

# Event classes. Anything not listed is recorded but does not change a status.
BLOCKING = {
    "Flash Flood Warning", "Flash Flood Emergency", "Flood Warning",
    "Severe Thunderstorm Warning", "Tornado Warning",
}
CAUTION = {
    "Flash Flood Watch", "Flood Watch", "Flood Advisory", "Flood Statement",
    "Hydrologic Outlook", "Severe Thunderstorm Watch", "Tornado Watch",
    "Special Weather Statement",
}
HEAT = {
    "Excessive Heat Warning", "Extreme Heat Warning", "Heat Advisory",
    "Excessive Heat Watch", "Extreme Heat Watch",
}
FLOODING = {"action", "minor", "moderate", "major"}
GAUGE_FRESH_HOURS = 3
STATUS_HOURS = 2

# Upstream drainage, by basin. County names only; the links command resolves
# each name to an official NWS county code through a probe coordinate in that
# county. "approximate" notes where the headwater county is from general
# geography rather than a mapped basin boundary.
COUNTY_PROBES = {
    "Travis": (30.27, -97.74), "Hays": (29.88, -97.94), "Williamson": (30.63, -97.68),
    "Blanco": (30.10, -98.42), "Comal": (29.70, -98.12), "Kendall": (29.79, -98.73),
    "Kerr": (30.05, -99.14), "Real": (29.73, -99.76), "Uvalde": (29.49, -99.70),
    "Kimble": (30.49, -99.77), "Gillespie": (30.27, -98.87), "Burnet": (30.76, -98.23),
    "Llano": (30.75, -98.68), "Edwards": (29.98, -100.30),
}
UPSTREAM = {  # place id -> (county names, note)
    **{p: (["Hays"], "Barton Creek rises in Hays County near Dripping Springs") for p in
       ("twin-falls", "hill-of-life", "sculpture-falls", "gus-fruh", "campbells-hole", "the-flats", "barton-springs")},
    "bull-creek-district": ([], "Bull Creek basin lies within Travis County"),
    "st-edwards": ([], "Bull Creek basin lies within Travis County"),
    "shoal-creek": ([], "urban creek within Travis County"),
    "blunn-big-stacey": ([], "urban creek within Travis County"),
    "blunn-little-stacey": ([], "urban creek within Travis County"),
    "walnut-domain": ([], "urban creek within Travis County"),
    "williamson-creek": ([], "Williamson Creek rises near Oak Hill in Travis County"),
    "mckinney-upper": (["Hays", "Blanco"], "Onion Creek rises in Blanco County and crosses Hays (approximate)"),
    "mckinney-lower": (["Hays", "Blanco"], "Onion Creek rises in Blanco County and crosses Hays (approximate)"),
    "commons-ford": ([], "Lake Austin is dam-controlled; LCRA floodgate operations are not checked here"),
    "emma-long": ([], "Lake Austin is dam-controlled; LCRA floodgate operations are not checked here"),
    "blue-hole-georgetown": (["Burnet"], "South San Gabriel headwaters toward Burnet County (approximate)"),
    "blue-hole-wimberley": ([], "Cypress Creek is spring-fed within Hays County"),
    "jacobs-well": ([], "spring within Hays County"),
    "san-marcos-city": ([], "spring-fed reach within Hays County"),
    "blanco-state-park": (["Kendall"], "Blanco River rises in Kendall County"),
    "pedernales-designated-swim": (["Gillespie", "Kimble"], "Pedernales rises in Kimble County and crosses Gillespie (approximate)"),
    "south-llano": (["Edwards"], "South Llano rises in Edwards County"),
    "guadalupe-river": (["Kerr", "Comal"], "Guadalupe headwaters in Kerr County; park is in Kendall/Comal"),
    "garner-frio": (["Real"], "Frio River rises in Real County"),
    "comal-prince-solms": ([], "spring-fed; Dry Comal drains Comal County"),
    "guadalupe-cypress-bend": (["Kendall", "Kerr"], "below Canyon Lake dam; releases are not checked here"),
    "guadalupe-river-acres": (["Kendall", "Kerr"], "below Canyon Lake dam; releases are not checked here"),
    "inks-devils-waterhole": (["Llano"], "Highland Lakes chain; LCRA operations are not checked here"),
}

# ---------------------------------------------------------------------------
# Raw capture
# ---------------------------------------------------------------------------

def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get(url: str, raw_dir: Path | None, kind: str, tries: int = 3) -> dict:
    """GET JSON, keep the raw body with its metadata when raw_dir is given."""
    delay = 3
    for attempt in range(1, tries + 1):
        req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/geo+json, application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                status = r.status
            break
        except urllib.error.HTTPError as e:
            body, status = e.read() or b"", e.code
            if status == 404:
                break
            if attempt == tries:
                raise
            time.sleep(delay); delay *= 2
        except (urllib.error.URLError, TimeoutError):
            if attempt == tries:
                raise
            time.sleep(delay); delay *= 2
    retrieved = now_utc().isoformat()
    if raw_dir:
        raw_dir.mkdir(parents=True, exist_ok=True)
        stamp = now_utc().strftime("%Y%m%dT%H%M%S%fZ")
        p = raw_dir / f"{stamp}-{kind}.json"
        p.write_bytes(body)
        p.with_suffix(".meta.json").write_text(json.dumps({
            "url": url, "retrieved_at": retrieved, "status": status,
            "sha256": hashlib.sha256(body).hexdigest(), "bytes": len(body)}, indent=2))
    if status != 200:
        raise RuntimeError(f"HTTP {status} for {url}")
    return {"url": url, "retrieved_at": retrieved, "sha256": hashlib.sha256(body).hexdigest(),
            "body": json.loads(body.decode("utf-8"))}

# ---------------------------------------------------------------------------
# links: build the place -> county / gauge table from official lookups
# ---------------------------------------------------------------------------

def _km(lat1, lon1, lat2, lon2):
    p = math.pi / 180
    a = 0.5 - math.cos((lat2 - lat1) * p) / 2 + math.cos(lat1 * p) * math.cos(lat2 * p) * (1 - math.cos((lon2 - lon1) * p)) / 2
    return 12742 * math.asin(math.sqrt(a))


def build_links(holes: list[dict], gauges: list[dict], raw_dir: Path | None, pause: float = 0.3) -> dict:
    counties = {}
    for name, (lat, lon) in COUNTY_PROBES.items():
        p = get(NWS_POINTS.format(lat=lat, lon=lon), raw_dir, f"points-{name}")["body"]["properties"]
        counties[name] = p["county"].split("/")[-1]
        time.sleep(pause)

    # NWS flood-forecast points near the inventory, matched to USGS ids.
    lats = [h["lat"] for h in holes] + [g["lat"] for g in gauges]
    lons = [h["lon"] for h in holes] + [g["lon"] for g in gauges]
    bbox = {"bbox.xmin": min(lons) - 0.3, "bbox.ymin": min(lats) - 0.3,
            "bbox.xmax": max(lons) + 0.3, "bbox.ymax": max(lats) + 0.3, "srid": "EPSG_4326"}
    listing = get(NWPS_GAUGES + "?" + urllib.parse.urlencode(bbox), raw_dir, "nwps-list")["body"]["gauges"]
    near = [g for g in listing if any(_km(g["latitude"], g["longitude"], la, lo) < 25 for la, lo in zip(lats, lons))]
    by_usgs = {}
    for g in near:
        d = get(NWPS_GAUGE.format(lid=g["lid"]), raw_dir, f"nwps-{g['lid']}")["body"]
        usgs = str(d.get("usgsId") or "")
        cats = {k: v.get("stage") for k, v in (d.get("flood", {}).get("categories") or {}).items()}
        cats = {k: v for k, v in cats.items() if v not in (None, -9999)}
        if usgs:
            by_usgs[usgs] = {"lid": d["lid"], "nwps_name": d["name"], "usgs_id": usgs,
                             "categories_ft": cats, "has_forecast": bool(d["pedts"].get("forecast"))}
        time.sleep(pause)

    station_names = {g["id"]: g["name"] for g in gauges}
    places = []
    for h in holes:
        p = get(NWS_POINTS.format(lat=h["lat"], lon=h["lon"]), raw_dir, f"points-{h['id']}")["body"]["properties"]
        up_names, note = UPSTREAM.get(h["id"], ([], "no upstream table entry; destination county only"))
        gauge = h.get("gauge")
        link = by_usgs.get(str(gauge)) if gauge else None
        places.append({
            "id": h["id"], "name": h["name"], "kind": h.get("kind"), "place_role": h.get("place_role"),
            "county_ugc": p["county"].split("/")[-1], "zone_ugc": p["forecastZone"].split("/")[-1],
            "upstream_ugc": [counties[n] for n in up_names], "upstream_note": note,
            "upstream_applies": h.get("place_role") == "water_place" and "lake" not in (h.get("kind") or "").lower(),
            "usgs_station": gauge, "usgs_station_name": station_names.get(gauge),
            "flood_gauge": link,
            "flood_gauge_note": (None if not gauge else
                                 "NWS forecast point matched by USGS station id" if link else
                                 "no NWS forecast point carries this USGS station id"),
        })
        time.sleep(pause)
    stations = [{"usgs_id": g["id"], "usgs_name": g["name"], **by_usgs[g["id"]]} for g in gauges if g["id"] in by_usgs]
    return {
        "generated_at": now_utc().isoformat(),
        "stations": stations,
        "method": "county/zone from NWS points lookup of each place's recorded coordinates; flood gauge linked only by USGS station id equality; upstream counties from the basin table in hazards.py resolved through probe coordinates",
        "counties": counties,
        "places": places,
    }

# ---------------------------------------------------------------------------
# assess
# ---------------------------------------------------------------------------

def parse_time(s):
    if not s:
        return None
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def classify(event: str) -> str:
    if event in BLOCKING:
        return "blocking"
    if event in CAUTION:
        return "caution"
    if event in HEAT:
        return "heat"
    return "other"


def normalize_alert(feature: dict) -> dict:
    p = feature["properties"]
    geo = p.get("geocode") or {}
    return {
        "id": p.get("id") or feature.get("id"),
        "event": p.get("event"),
        "class": classify(p.get("event", "")),
        "severity": p.get("severity"), "urgency": p.get("urgency"), "certainty": p.get("certainty"),
        "headline": p.get("headline"),
        "area": p.get("areaDesc"),
        "ugc": list(geo.get("UGC") or []),
        "onset": p.get("onset") or p.get("effective"),
        "ends": p.get("ends") or p.get("expires"),
        "sender": p.get("senderName"),
        "url": p.get("@id") or feature.get("id"),
        "description": (p.get("description") or "")[:600],
    }


def alert_window(a: dict, at: datetime, horizon_h: int = 24) -> str | None:
    """'active', 'upcoming' (starts within horizon), or None (past / far)."""
    start, end = parse_time(a["onset"]), parse_time(a["ends"])
    if end and end <= at:
        return None
    if start and start > at:
        return "upcoming" if start <= at + timedelta(hours=horizon_h) else None
    return "active"


def gauge_state(detail: dict, at: datetime) -> dict:
    obs = (detail.get("status") or {}).get("observed") or {}
    fc = (detail.get("status") or {}).get("forecast") or {}
    cats = {k: v.get("stage") for k, v in (detail.get("flood", {}).get("categories") or {}).items()}
    cats = {k: v for k, v in cats.items() if v not in (None, -9999)}
    valid = parse_time(obs.get("validTime")) if obs.get("validTime", "").startswith("2") else None
    fresh = valid is not None and abs((at - valid).total_seconds()) <= GAUGE_FRESH_HOURS * 3600
    ocat = obs.get("floodCategory")
    fcat = fc.get("floodCategory")
    if not cats:
        signal = "unknown"; why = "no official flood categories published for this gauge"
    elif not fresh:
        signal = "unknown"; why = f"observation not fresh ({obs.get('validTime')})"
    elif ocat in FLOODING:
        signal = "flooding"; why = f"observed {obs.get('primary')} {obs.get('primaryUnit')} is in the {ocat} flood category"
    elif fcat in FLOODING:
        signal = "forecast-flooding"; why = f"forecast reaches the {fcat} flood category"
    else:
        signal = "none"; why = f"observed {obs.get('primary')} {obs.get('primaryUnit')}, below action stage" if cats.get("action") else f"observed {obs.get('primary')} {obs.get('primaryUnit')}, below minor flood stage"
    return {"lid": detail.get("lid"), "name": detail.get("name"), "usgs_id": detail.get("usgsId"),
            "observed_stage": obs.get("primary"), "unit": obs.get("primaryUnit"), "observed_at": obs.get("validTime"),
            "observed_category": ocat, "forecast_category": fcat, "categories_ft": cats,
            "signal": signal, "reason": why,
            "source": f"https://water.noaa.gov/gauges/{detail.get('lid')}"}


def assess(links: dict, alerts_body: dict, gauge_details: dict[str, dict], at: datetime,
           sources: list[dict]) -> dict:
    alerts = [normalize_alert(f) for f in alerts_body.get("features", [])]
    all_ugc = set()
    for pl in links["places"]:
        all_ugc.update([pl["county_ugc"], pl["zone_ugc"], *pl["upstream_ugc"]])
    relevant = []
    for a in alerts:
        w = alert_window(a, at)
        if w and set(a["ugc"]) & all_ugc:
            relevant.append({**a, "window": w})

    gauges = {lid: gauge_state(d, at) for lid, d in gauge_details.items()}

    places = []
    for pl in links["places"]:
        dest = {pl["county_ugc"], pl["zone_ugc"]}
        up = set(pl["upstream_ugc"]) if pl["upstream_applies"] else set()
        hits = []
        for a in relevant:
            codes = set(a["ugc"])
            if codes & dest:
                hits.append({**a, "scope": "destination"})
            elif codes & up:
                hits.append({**a, "scope": "upstream"})
        g = gauges.get((pl.get("flood_gauge") or {}).get("lid"))

        reasons, status = [], "none"
        for h in hits:
            tag = f"NWS {h['event']} ({h['scope']}, {h['window']}, until {h['ends']})"
            if h["class"] == "blocking" and h["window"] == "active":
                status = "active"; reasons.append(tag)
            elif h["class"] in ("blocking", "caution"):
                status = "caution" if status != "active" else status; reasons.append(tag)
            elif h["class"] == "heat":
                reasons.append(tag)
        if g:
            if g["signal"] == "flooding":
                status = "active"; reasons.append(f"{g['lid']} {g['reason']}")
            elif g["signal"] == "forecast-flooding":
                status = "caution" if status != "active" else status; reasons.append(f"{g['lid']} {g['reason']}")
            elif g["signal"] == "unknown":
                reasons.append(f"{g['lid']}: {g['reason']}")
        if status == "none":
            status = "none found in checked sources"

        ends = [parse_time(h["ends"]) for h in hits if h["window"] == "active" and h["ends"]]
        valid_until = min([at + timedelta(hours=STATUS_HOURS)] + [e for e in ends if e]).isoformat()
        places.append({
            "id": pl["id"], "name": pl["name"],
            "hazard_notice": status,
            "reason": "; ".join(reasons) if reasons else
                      f"no active NWS warning, watch, or advisory for {pl['county_ugc']}"
                      + (f" or upstream {', '.join(pl['upstream_ugc'])}" if up else "")
                      + (f"; {g['lid']} {g['reason']}" if g and g["signal"] == "none" else ""),
            "evidence": "Official notice check · NWS alerts by county code"
                        + (" + NWS flood-stage category" if g else " (no linked flood forecast point)"),
            "checked_at": at.isoformat(),
            "valid_until": valid_until,
            "alerts": [{"event": h["event"], "class": h["class"], "scope": h["scope"], "window": h["window"],
                        "onset": h["onset"], "ends": h["ends"], "url": h["url"]} for h in hits],
            "flood_gauge": g,
            "source": "https://www.weather.gov/documentation/services-web-alerts",
        })

    return {
        "generated_at": at.isoformat(),
        "meaning": "official NWS alerts and NWS flood-stage categories checked for each place's county, upstream counties, and linked forecast gauge; not a water-quality, access, or safety claim; 'none found' means none in the checked sources at the checked time",
        "sources": sources,
        "coverage": {"alerts_in_state_feed": len(alerts), "alerts_relevant": len(relevant),
                     "county_codes_checked": sorted(all_ugc), "gauges_checked": sorted(gauges)},
        "alerts": relevant,
        "gauges": list(gauges.values()),
        "places": places,
    }

# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def collect(links: dict, raw_dir: Path | None, pause: float = 0.3) -> dict:
    sources = []
    a = get(NWS_ALERTS + "?area=TX", raw_dir, "nws-alerts-TX")
    sources.append({"kind": "nws-alerts", "url": a["url"], "retrieved_at": a["retrieved_at"], "sha256": a["sha256"]})
    details = {}
    lids = {(p.get("flood_gauge") or {}).get("lid") for p in links["places"]} | {st["lid"] for st in links.get("stations", [])}
    for lid in sorted(lids - {None}):
        d = get(NWPS_GAUGE.format(lid=lid), raw_dir, f"nwps-{lid}")
        details[lid] = d["body"]
        sources.append({"kind": "nwps-gauge", "lid": lid, "url": d["url"], "retrieved_at": d["retrieved_at"], "sha256": d["sha256"]})
        time.sleep(pause)
    return {"fetched_at": now_utc().isoformat(), "alerts": a["body"], "gauges": details, "sources": sources}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="Storm and floodwater layer from official NWS sources.")
    sub = p.add_subparsers(dest="cmd", required=True)
    l = sub.add_parser("links", help="rebuild hazard-links.json from official lookups")
    l.add_argument("--holes", default=str(ROOT / "data/holes.json")); l.add_argument("--gauges", default=str(ROOT / "data/gauges.json"))
    l.add_argument("--out", default=str(ROOT / "data/hazard-links.json")); l.add_argument("--raw-dir", default=str(ROOT / "data/raw/hazards"))
    s = sub.add_parser("assess", help="fetch (or read a fixture), assess, write the status sidecar")
    s.add_argument("--links", default=str(ROOT / "data/hazard-links.json"))
    s.add_argument("--out", default=str(ROOT / "app/hazards-status.json"))
    s.add_argument("--fixture"); s.add_argument("--save-fixture")
    s.add_argument("--raw-dir", default=str(ROOT / "data/raw/hazards"), help="raw capture dir (git-ignored); '' to skip")
    s.add_argument("--at", help="ISO time to assess at (default now, UTC)")
    args = p.parse_args(argv)

    raw_dir = Path(args.raw_dir) if args.raw_dir else None
    if args.cmd == "links":
        holes = json.loads(Path(args.holes).read_text()); gauges = json.loads(Path(args.gauges).read_text())
        links = build_links(holes, gauges, raw_dir)
        Path(args.out).write_text(json.dumps(links, indent=1))
        linked = sum(1 for x in links["places"] if x["flood_gauge"])
        print(f"[links] {len(links['places'])} places, {linked} with a flood forecast point -> {args.out}", file=sys.stderr)
        return 0

    links = json.loads(Path(args.links).read_text())
    if args.fixture:
        bundle = json.loads(Path(args.fixture).read_text())
    else:
        bundle = collect(links, raw_dir)
        if args.save_fixture:
            Path(args.save_fixture).write_text(json.dumps(bundle, indent=1))
            print(f"[saved] {args.save_fixture}", file=sys.stderr)
    at = parse_time(args.at) if args.at else (parse_time(bundle["fetched_at"]) if args.fixture else now_utc())
    status = assess(links, bundle["alerts"], bundle["gauges"], at, bundle.get("sources", []))
    Path(args.out).write_text(json.dumps(status, indent=1))
    active = [x for x in status["places"] if x["hazard_notice"] == "active"]
    caution = [x for x in status["places"] if x["hazard_notice"] == "caution"]
    print(f"[hazards] {status['coverage']['alerts_in_state_feed']} TX alerts, {status['coverage']['alerts_relevant']} relevant; "
          f"{len(active)} places active, {len(caution)} caution -> {args.out}", file=sys.stderr)
    for x in active + caution:
        print(f"  {x['hazard_notice']:<8} {x['name']}: {x['reason']}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
