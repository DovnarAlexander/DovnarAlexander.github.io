# Alexander Dovnar personal site
## Development

This project uses [uv](https://docs.astral.sh/uv/) for Python management and [Taskfile](https://taskfile.dev) for developer tasks.

### Prerequisites
- Install uv (macOS): `curl -LsSf https://astral.sh/uv/install.sh | sh`
- Install Task (macOS): `brew install go-task/tap/go-task`
- Set `YOUTUBE_API_KEY` in your environment (used by `generate.py`).

### Common tasks
- Render the page (generates `index.html`):
```bash
task render
```
- Build (alias of render, reserved for future steps):
```bash
task build
```
- Clean generated files:
```bash
task clean
```
- Build the CV PDFs (English + Russian):
```bash
task build-cv
```

Notes:
- Rendering will minify HTML automatically when `CI` is set in the environment.
- Dependencies are declared in `pyproject.toml`; Task will run `uv sync` automatically.

## CV / résumé

The two résumé PDFs in `uploads/` are **generated**, not hand-edited. Sources live in `cv/`:

- `cv/content/en.md`, `cv/content/ru.md` — each is Markdown with a YAML front-matter block.
  The front-matter holds the structured sections (contact, summary, skills, certifications,
  communities, education); the Markdown body holds the Experience entries.
- `cv/template.html.j2` + `cv/cv.css` — one single-column, ATS-friendly layout (real selectable
  text, standard section headers, no photo/columns/tables) used for both languages.
- `cv/Dockerfile` — pins WeasyPrint and Cyrillic-capable fonts so the build is reproducible.

To update a CV: edit the relevant `cv/content/<lang>.md`, then run `task build-cv` (requires only
**Docker** — no host Python/font setup). It rewrites `uploads/DevOps-Alexander-Dovnar-EN.pdf` and
`… RU.pdf`, which the site already links to. Debug HTML is written to `cv/build/` (git-ignored).
