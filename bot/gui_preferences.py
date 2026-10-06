"""Application appearance only; independent of routine JSON and character SQLite."""
import json
from pathlib import Path


class GuiPreferences:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> str:
        try:
            value = json.loads(self.path.read_text(encoding="utf-8")).get("appearance")
            return value if value in ("Light", "Dark") else "Light"
        except (OSError, ValueError, AttributeError):
            return "Light"

    def save(self, appearance: str) -> None:
        if appearance not in ("Light", "Dark"):
            raise ValueError("Appearance must be Light or Dark")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"appearance": appearance}) + "\n", encoding="utf-8")
        temporary.replace(self.path)
