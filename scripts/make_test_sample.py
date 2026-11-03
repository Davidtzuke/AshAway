"""Cut the small real-data sample in tests/data/track_a_sample/ from the full Track A files.

Takes POS_PER_SPLIT positives and NEG_PER_SPLIT negatives per split, so the
tests can run in CI without the 218 MB download. Mesogeos is CC BY 4.0.
"""
from pathlib import Path

import numpy as np
import pandas as pd

POS_PER_SPLIT = 12
NEG_PER_SPLIT = 26  # 2 more than the 2:1 ratio keeps, so downsampling is exercised
SPLITS = (range(2006, 2020), (2020,), (2021, 2022))

SRC, DST = Path("data/raw/mesogeos"), Path("tests/data/track_a_sample")


def cut(name: str, per_split: int, rng: np.random.Generator) -> None:
    raw = pd.read_csv(SRC / name)
    year = pd.to_datetime(raw.loc[raw["time_idx"] == 29].set_index("sample")["time"]).dt.year
    chosen = []
    for years in SPLITS:
        pool = year.index[year.isin(list(years))].to_numpy()
        chosen.extend(rng.choice(pool, per_split, replace=False))
    sample = raw[raw["sample"].isin(chosen)].round(6)
    sample.to_csv(DST / name, index=False)


if __name__ == "__main__":
    DST.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(7)
    cut("positives.csv", POS_PER_SPLIT, rng)
    cut("negatives.csv", NEG_PER_SPLIT, rng)
