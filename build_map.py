#!/usr/bin/env python3
"""
NYC Public School Map — shows all ~1,600 DOE public schools with 2024-25 enrollment.
Highlights the ~112 schools with 150 or fewer students.

Data sources:
  - Enrollment: NYSED BEDS Day Enrollment 2024-25 (from Access DB export)
  - Locations:  NYC Open Data 2019-2020 School Locations (Socrata wg9x-4ke6)
  - Join key:   BEDS code (12-digit)
"""

import csv
import json
import os
import urllib.request
import urllib.parse

BASE_URL = "https://data.cityofnewyork.us/resource"


def fetch_socrata(dataset_id, params=None, limit=50000):
    if params is None:
        params = {}
    params["$limit"] = str(limit)
    query = urllib.parse.urlencode(params)
    url = f"{BASE_URL}/{dataset_id}.json?{query}"
    print(f"  {url[:120]}...")
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode())
    print(f"  -> {len(data)} records")
    return data


def load_nysed_enrollment(csv_path):
    nyc_county_codes = {"31", "32", "33", "34", "35"}
    schools = {}
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            entity = row["ENTITY_CD"].strip().strip('"')
            year = row["YEAR"].strip().strip('"')
            name = row["ENTITY_NAME"].strip().strip('"')
            k12_str = row["K12"].strip().strip('"')
            try:
                k12 = int(k12_str)
            except (ValueError, TypeError):
                continue
            if year != "2025" or len(entity) != 12 or entity[-4:] == "0000":
                continue
            county = entity[:2]
            is_nyc = county in nyc_county_codes or entity[:4] in ("3075", "3079")
            if not is_nyc or k12 <= 0:
                continue
            school_type = entity[6:8]
            is_charter = school_type == "86"
            schools[entity] = {
                "beds": entity,
                "name": name,
                "k12": k12,
                "county": county,
                "is_charter": is_charter,
            }
    return schools


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    csv_path = os.path.join(script_dir, "enrollment_2025.csv")

    print("=" * 60)
    print("NYC Public School Map Builder")
    print("=" * 60)

    # 1. Load NYSED 2024-25 enrollment
    print("\n[1/3] Loading NYSED 2024-25 enrollment...")
    all_schools = load_nysed_enrollment(csv_path)
    public = {k: v for k, v in all_schools.items() if not v["is_charter"]}
    print(f"  Public (non-charter): {len(public)}")

    # 2. Fetch school locations
    print("\n[2/3] Fetching school locations...")
    locations_raw = fetch_socrata("wg9x-4ke6", {
        "$where": "status_descriptions='Open'",
        "$select": "system_code,location_code,location_name,location_category_description,"
                   "location_type_description,latitude,longitude,primary_address_line_1,"
                   "grades_final_text,beds,managed_by_name"
    })

    loc_by_beds = {}
    for loc in locations_raw:
        beds = (loc.get("beds") or "").strip()
        lat = loc.get("latitude")
        lng = loc.get("longitude")
        if not beds or not lat or not lng:
            continue
        try:
            lat, lng = float(lat), float(lng)
        except (ValueError, TypeError):
            continue
        loc_by_beds[beds] = {
            "name": loc.get("location_name", ""),
            "lat": lat, "lng": lng,
            "address": loc.get("primary_address_line_1", ""),
            "category": loc.get("location_category_description", ""),
            "grades": loc.get("grades_final_text", ""),
            "dbn": loc.get("system_code", ""),
        }

    # 3. Join
    print("\n[3/3] Joining...")
    joined = []
    for beds, school in public.items():
        loc = loc_by_beds.get(beds)
        if loc:
            joined.append({
                "b": beds, "n": school["name"], "e": school["k12"],
                "la": loc["lat"], "ln": loc["lng"],
                "a": loc["address"], "c": loc["category"],
                "g": loc["grades"], "d": loc["dbn"],
            })

    # Sort: large schools first so small render on top
    joined.sort(key=lambda s: -s["e"])

    small = [s for s in joined if s["e"] <= 150]
    print(f"  Schools on map: {len(joined)}")
    print(f"  Schools <= 150: {len(small)}")

    # Write data JSON
    data_path = os.path.join(script_dir, "schools.json")
    with open(data_path, "w") as f:
        json.dump(joined, f, separators=(",", ":"))
    print(f"  Data: {data_path} ({os.path.getsize(data_path) // 1024}KB)")
    print("\nDone! Now deploy index.html + schools.json")


if __name__ == "__main__":
    main()
