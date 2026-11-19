"""Local storage for confirmed project details."""
from pathlib import Path
import re


def save_project(root: Path, name: str, description: str, concept: str = "", next_steps: str = "", context: str = "") -> Path:
    """Create a new directory without overwriting existing projects."""
    name = name.strip()
    description = description.strip()
    if not name or not description:
        raise ValueError("Enter a project name and description.")
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    if not slug:
        raise ValueError("The name must contain Latin letters or numbers.")
    root.mkdir(parents=True, exist_ok=True)
    directory = root / slug
    directory.mkdir(exist_ok=False)
    (directory / "project.md").write_text(f"# {name}\n\n## Confirmed idea\n\n{description}\n", encoding="utf-8")
    (directory / "next-steps.md").write_text(f"# Next steps\n\n{next_steps.strip()}\n", encoding="utf-8")
    (directory / "context.md").write_text(f"# Context\n\n{context.strip()}\n", encoding="utf-8")
    (directory / "concept-map.md").write_text(f"# Concept map\n\n{concept.strip()}\n", encoding="utf-8")
    return directory
