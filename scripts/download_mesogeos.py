"""Download Mesogeos Track A (CC BY 4.0) into data/raw/mesogeos/. Needs `pip install gdown`.

File ids come from the public Drive folder linked in
https://github.com/Orion-AI-Lab/mesogeos (ml_tracks/a.danger_forecasting).
"""
from pathlib import Path

import gdown

FILES = {
    "positives.csv": "1IYONBanlerMi84wedto-Vck8vmfnyVUR",
    "negatives.csv": "1qB6TjMCgpVvM04ysCZSgE-5sjJ2C9gNJ",
    "norms.json": "1uXsRpCJa7JNlPXmHvzCCIxs3E0eC6NUE",
    "vars_dict.json": "1PdwYyMX-51-zJ1dr36g8Hq-_7K7KTVAx",
}

if __name__ == "__main__":
    out = Path("data/raw/mesogeos")
    out.mkdir(parents=True, exist_ok=True)
    for name, file_id in FILES.items():
        gdown.download(id=file_id, output=str(out / name), resume=True)
