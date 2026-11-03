"""Build src/ashaway/resources/pilot_destinations.csv from the full Track A files.

The live model needs terrain, land cover, road and population values, and the live
feeds do not supply them. Each pilot destination therefore borrows them from the
nearest real Track A cell in Greece, and is only supported when that cell is within
MAX_SOURCE_KM. A destination is represented by that one 1 km cell.
"""
from pathlib import Path

import pandas as pd

from ashaway.geo import cell_of_point, in_greece
from ashaway.model.data import STATIC_FEATURES, load_mesogeos_track_a
from ashaway.targets import haversine_km

MAX_SOURCE_KM = 10.0
OUT = Path("src/ashaway/resources/pilot_destinations.csv")

# Approximate centre of each candidate holiday area: id, name, lat, lon.
CANDIDATES = [
    ("rhodes", "Rhodes", 36.25, 27.95),
    ("chania", "Chania", 35.40, 23.90),
    ("heraklion", "Heraklion", 35.25, 25.20),
    ("rethymno", "Rethymno", 35.30, 24.50),
    ("marathon", "Marathon", 38.15, 23.95),
    ("nafplio", "Nafplio", 37.57, 22.80),
    ("corfu", "Corfu", 39.60, 19.85),
    ("zakynthos", "Zakynthos", 37.78, 20.80),
    ("kefalonia", "Kefalonia", 38.25, 20.55),
    ("lefkada", "Lefkada", 38.75, 20.65),
    ("kos", "Kos", 36.80, 27.10),
    ("mykonos", "Mykonos", 37.45, 25.37),
    ("naxos", "Naxos", 37.05, 25.50),
    ("skiathos", "Skiathos", 39.17, 23.47),
    ("kassandra", "Kassandra", 40.05, 23.45),
    ("sithonia", "Sithonia", 40.05, 23.95),
    ("thasos", "Thasos", 40.68, 24.65),
    ("kalamata", "Kalamata", 37.05, 22.10),
    ("olympia", "Ancient Olympia", 37.65, 21.60),
    ("evia", "North Evia", 38.90, 23.20),
    ("volos", "Volos", 39.35, 22.95),
    ("delphi", "Delphi", 38.48, 22.50),
]


if __name__ == "__main__":
    df = load_mesogeos_track_a()
    greek = df[in_greece(df["lon"].to_numpy(), df["lat"].to_numpy())].reset_index(drop=True)
    rows = []
    for dest_id, name, lat, lon in CANDIDATES:
        dist = haversine_km(greek["lon"].to_numpy(), greek["lat"].to_numpy(), lon, lat)
        best = dist.argmin()
        if dist[best] > MAX_SOURCE_KM:
            print(f"skipped {name}: nearest cell is {dist[best]:.1f} km away")
            continue
        cell = greek.iloc[best]
        rows.append({
            "id": dest_id,
            "name": name,
            "lon": round(float(cell["lon"]), 5),
            "lat": round(float(cell["lat"]), 5),
            "cell_id": cell_of_point(float(cell["lon"]), float(cell["lat"])),
            "source_km": round(float(dist[best]), 1),
            **{c: float(cell[c]) for c in STATIC_FEATURES},
        })
    pd.DataFrame(rows).to_csv(OUT, index=False)
    print(f"wrote {len(rows)} destinations to {OUT}")
