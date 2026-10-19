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

## Languages (EN / RU)

The site is built twice: English at `/` and Russian at `/ru/`. Everything is static; there is no
runtime machine translation.

- UI strings (titles, nav, buttons, labels) live in `i18n.yml`, one block per language.
- Page sections: `content/<section>.md` (EN) and `content/ru/<section>.md` (RU). A missing RU file
  falls back to the EN one, with a warning in the build log.
- Blog: a translation is `content/blog/<slug>.ru.md` next to the EN original, same `slug`. It renders
  to `/ru/blog/<slug>/`. EN posts without a translation still appear in the RU list, marked `EN`,
  and link to the English page.
- Every page carries `hreflang` alternates. The `EN | RU` switch in the top bar opens the same page
  in the other language and stores the choice in a `lang` cookie.
- First visit: a Cloudflare redirect rule on `/` sends visitors from Russia and Belarus to `/ru/`
  unless they already have a `lang` cookie (see below).

**Cloudflare redirect rule** (Rules → Redirect Rules → Create rule, "Custom filter expression"):

```
(http.request.uri.path eq "/" and (http.cookie contains "lang=ru" or (ip.src.country in {"RU" "BY"} and not http.cookie contains "lang=")))
```

Then: Type *Static*, URL `https://alex-dovnar.in/ru/`, status code **302**, *Preserve query string* on.

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

**Namespaces:** post `tags` double as namespaces for the filter above the post list
(`kubectl get posts -n <namespace>`). A namespace name is the tag lowercased with everything but
letters and digits dropped, so `Platform Engineering` and `PlatformEngineering` land in the same
`platformengineering` namespace. The ten largest namespaces are shown; the rest sit behind
"+N more". The selected namespace lives in the URL (`/?ns=terraform#blog`), so filtered views can
be shared, and tags on a post page link back to the filtered list.

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
  communities, languages, education); the Markdown body holds the Experience entries.
- `cv/template.html.j2` + `cv/cv.css` — one single-column, ATS-friendly layout (real selectable
  text, standard section headers, no photo/columns/tables) used for both languages.
- `cv/Dockerfile` — pins WeasyPrint and Cyrillic-capable fonts so the build is reproducible.

To update a CV: edit the relevant `cv/content/<source>.md`, then run `task build-cv` (requires only
**Docker** — no host Python/font setup). It rewrites `uploads/DevOps-Alexander-Dovnar-EN.pdf` and
`… RU.pdf`, which the site already links to. `cv/content/en-leadership.md` (CTO/VP roles) is built to
`cv/build/Alexander-Dovnar-CV-Leadership.pdf`: git-ignored, not deployed, sent by hand. Debug HTML is written to `cv/build/` (git-ignored).
