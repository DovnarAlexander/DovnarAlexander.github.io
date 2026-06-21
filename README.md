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

## Blog

Articles live as Markdown in `content/blog/<slug>.md` with a YAML front-matter block:

```markdown
---
title: "Kubernetes probes are a mental model, not a checklist"
date: 2026-06-21
slug: kubernetes-probes-mental-model   # optional; defaults to the filename
excerpt: "A one-line summary used in the blog list and meta description."
tags: [Kubernetes, DevOps, SRE]
# draft: true                          # optional; omit to publish
---

# Title repeated as H1 (stripped from the body — rendered from front-matter)

Article body in Markdown (fenced code blocks and tables supported)…
```

`generate.py` scans `content/blog/`, renders each post to `blog/<slug>/index.html` (template:
`post.html.j2`), and lists them in the site's `#blog` section. URLs are clean and readable:
`https://alex-dovnar.in/blog/<slug>/`.

**Publishing flow:** add the Markdown file (typically via the `/content-publish-blog` command in the
content pipeline, which opens a PR), get the PR reviewed/merged to `main`. The
`Deploy site to Pages` GitHub Action builds the site (`task render`) and deploys it — the post is
live at its canonical URL on merge. Nothing is committed pre-built; HTML is a build artifact.

> One-time setup for CI deploys: in repo **Settings → Pages**, set the source to **GitHub Actions**,
> and add a `YOUTUBE_API_KEY` repository secret (`generate.py` requires it).

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
