import json
from pathlib import Path

def load_mapping():
    path = Path(__file__).resolve().parent.parent / "data" / "motorcycles.json"
    if path.exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    raise FileNotFoundError(f"Mapping file not found: {path}")