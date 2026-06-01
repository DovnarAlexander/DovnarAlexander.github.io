#!env python3
"""Build the CV PDFs (EN + RU) from cv/content/<lang>.md via WeasyPrint.

Each source file is Markdown with a YAML front-matter block. The front-matter
holds the structured sections (contact, summary, skills, certifications,
communities, education); the Markdown body holds the Experience entries. One
Jinja template + one print stylesheet render a single-column, ATS-friendly PDF
per language.
"""

import logging
import os
import re
from pathlib import Path

import yaml
from jinja2 import Template
from markdown import markdown
from weasyprint import HTML

_LEVEL = getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO)
logging.basicConfig(
    level=_LEVEL, format="%(asctime)s %(levelname)s %(name)s - %(message)s"
)


class _DropNoisy(logging.Filter):
    """Drop WeasyPrint/fontTools internal chatter so build output stays readable."""

    def filter(self, record: logging.LogRecord) -> bool:
        return not record.name.startswith(("fontTools", "weasyprint"))


for _h in logging.getLogger().handlers:
    _h.addFilter(_DropNoisy())
logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
CV_DIR = ROOT / "cv"
OUT_DIR = ROOT / "uploads"
BUILD_DIR = CV_DIR / "build"

# lang -> output filename (matches the links in index.html.j2)
LANGS = {
    "en": "DevOps-Alexander-Dovnar-EN.pdf",
    "ru": "DevOps-Alexander-Dovnar-RU.pdf",
}

FRONT_MATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)


def parse_source(path: Path) -> tuple[dict, str]:
    """Split a Markdown file into (front-matter dict, body HTML)."""
    text = path.read_text(encoding="utf-8")
    match = FRONT_MATTER_RE.match(text)
    if not match:
        raise ValueError(f"{path} is missing a '---' YAML front-matter block")
    meta = yaml.safe_load(match.group(1)) or {}
    body_html = markdown(match.group(2), extensions=["attr_list"])
    return meta, body_html


def main() -> None:
    template = Template((CV_DIR / "template.html.j2").read_text(encoding="utf-8"))
    css_text = (CV_DIR / "cv.css").read_text(encoding="utf-8")
    BUILD_DIR.mkdir(parents=True, exist_ok=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    for lang, out_name in LANGS.items():
        meta, body_html = parse_source(CV_DIR / "content" / f"{lang}.md")
        html = template.render(lang=lang, css=css_text, body=body_html, **meta)

        debug_html = BUILD_DIR / f"{lang}.html"
        debug_html.write_text(html, encoding="utf-8")

        out_path = OUT_DIR / out_name
        HTML(string=html, base_url=str(CV_DIR)).write_pdf(str(out_path))
        logger.info("Built %s CV: %s", lang.upper(), out_path)


if __name__ == "__main__":
    main()
