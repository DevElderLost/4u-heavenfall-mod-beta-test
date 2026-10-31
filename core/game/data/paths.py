"""Where the knowledge base's files are: a module of its own, so that code that only reads a
curated file (the single-screen mode, the game GUI's arrangement) loads none of the knowledge base."""

from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent
GENERATED_DIR = DATA_DIR / "generated"
CURATED_DIR = DATA_DIR / "curated"
