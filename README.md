# Alexander Dovnar personal site
TBA
## Tools \ materials used
### Site template
(Dominic - Responsive HTML5 OnePage Template)[https://html.design/download/dominic-personal-template/]


# TODO: Move everything in dedicated repo and sync in site the static content only!

---

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

Notes:
- Rendering will minify HTML automatically when `CI` is set in the environment.
- Dependencies are declared in `pyproject.toml`; Task will run `uv sync` automatically.