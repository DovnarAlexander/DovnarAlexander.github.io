#!env python3
import datetime
import hashlib
import json
import logging
import os
import re
from pathlib import Path

import frontmatter
import yaml
from jinja2 import Template
from markdown import markdown
from pyyoutube import Api

# Public base URL of the site — used to build absolute canonical links for posts.
BASE_URL = "https://alex-dovnar.in"

# Site languages -> URL prefix. EN is served from /, RU from /ru/. RU page
# content comes from content/ru/ and falls back to the EN file per section;
# a RU blog post is content/blog/<slug>.ru.md next to the EN original.
LANGS = {"en": "", "ru": "ru"}
I18N = yaml.safe_load(Path("i18n.yml").read_text(encoding="utf-8"))
RU_MONTHS = ["янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"]

# Configure logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.DEBUG),
    format="%(asctime)s %(levelname)s %(name)s - %(message)s",
)
logger = logging.getLogger(__name__)


def classify_video_group(title: str) -> str:
    classification = "Public talks"
    dkt = "DevOps Kitchen Talks"
    logging.debug(f"Classifying video title {title}")
    if "DKT" in title:
        classification = dkt
    elif "DevOps Kitchen" in title:
        classification = dkt
    return classification


def strip_top_h1(html: str) -> str:
    if not html:
        return html
    # Remove the first <h1>...</h1> (greedy enough to stop at the first closing tag)
    return re.sub(
        r"<h1[^>]*>.*?</h1>\s*", "", html, count=1, flags=re.IGNORECASE | re.DOTALL
    )


def load_markdown(path: str) -> str:
    if os.path.exists(path):
        logger.debug("Loading markdown from %s", path)
        with open(path, mode="r") as f:
            rendered = markdown(f.read())
            return strip_top_h1(rendered)
    logger.warning("Markdown file not found: %s", path)
    return ""


def _coerce_date(value) -> str:
    """Normalize a frontmatter date (date/datetime/str) to an ISO YYYY-MM-DD string."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.strftime("%Y-%m-%d")
    return str(value or "").strip()


def _human_date(iso: str, lang: str = "en") -> str:
    """Render an ISO date as 'Jun 21, 2026' (EN) or '21 июн 2026' (RU); fall back to the raw string."""
    try:
        d = datetime.datetime.strptime(iso, "%Y-%m-%d")
    except ValueError:
        return iso
    if lang == "ru":
        return f"{d.day} {RU_MONTHS[d.month - 1]} {d.year}"
    return d.strftime("%b %-d, %Y")


def lang_prefix(lang: str) -> str:
    """URL path prefix for a language: '/' for EN, '/ru/' for RU."""
    return f"/{LANGS[lang]}/" if LANGS[lang] else "/"


def namespace_slug(tag: str) -> str:
    """Turn a post tag into a namespace name: 'Platform Engineering' -> 'platformengineering'."""
    return re.sub(r"[^a-z0-9]", "", tag.lower())


def build_namespaces(posts: list) -> list:
    """Collect post tags into namespaces for the blog filter.

    Tags that differ only in case/spacing share one namespace. Each namespace keeps the
    most common spelling as its label. Sorted by post count desc, then by name.
    """
    spellings: dict = {}
    counts: dict = {}
    for post in posts:
        for slug, tag in {namespace_slug(t): t for t in post["tags"]}.items():
            if not slug:
                continue
            counts[slug] = counts.get(slug, 0) + 1
            spellings.setdefault(slug, {})
            spellings[slug][tag] = spellings[slug].get(tag, 0) + 1

    namespaces = [
        {
            "slug": slug,
            "label": max(spellings[slug], key=spellings[slug].get),
            "count": count,
        }
        for slug, count in counts.items()
    ]
    namespaces.sort(key=lambda ns: (-ns["count"], ns["slug"]))
    return namespaces


def load_blog_posts(content_dir: str, lang: str = "en") -> list:
    """Load blog articles from content/blog/*.md (EN) or content/blog/*.ru.md (RU).

    Each file carries YAML frontmatter (title, date, slug, excerpt, tags, draft).
    Returns a list of post dicts (newest first), skipping anything marked draft.
    """
    blog_dir = Path(content_dir) / "blog"
    if not blog_dir.is_dir():
        logger.info("No blog directory at %s — skipping posts", blog_dir)
        return []

    posts = []
    for md_path in sorted(blog_dir.glob("*.md")):
        is_ru = md_path.name.endswith(".ru.md")
        if is_ru != (lang == "ru"):
            continue
        logger.debug("Loading blog post %s", md_path)
        post = frontmatter.load(md_path)
        meta = post.metadata
        if meta.get("draft"):
            logger.info("Skipping draft post %s", md_path)
            continue

        slug = str(meta.get("slug") or md_path.stem.removesuffix(".ru")).strip()
        iso_date = _coerce_date(meta.get("date"))
        body_html = strip_top_h1(
            markdown(
                post.content,
                extensions=["fenced_code", "codehilite", "tables", "toc", "sane_lists"],
                extension_configs={
                    # Highlight fenced blocks at build time via Pygments (CSS classes,
                    # no inline styles) and never guess a language for unlabelled blocks.
                    "codehilite": {"css_class": "highlight", "guess_lang": False},
                },
            )
        )
        tags = meta.get("tags") or []
        if isinstance(tags, str):
            tags = [t.strip() for t in tags.replace(",", " ").split() if t.strip()]

        posts.append(
            {
                "slug": slug,
                "title": str(meta.get("title") or slug).strip(),
                "date": iso_date,
                "date_human": _human_date(iso_date, lang),
                "excerpt": str(meta.get("excerpt") or "").strip(),
                "tags": tags,
                "tag_links": [
                    {"label": t, "ns": namespace_slug(t)}
                    for t in tags
                    if namespace_slug(t)
                ],
                "body_html": body_html,
                "lang": lang,
                "url": f"{lang_prefix(lang)}blog/{slug}/",
                "canonical": f"{BASE_URL}{lang_prefix(lang)}blog/{slug}/",
            }
        )

    posts.sort(key=lambda p: p["date"], reverse=True)
    logger.info("Loaded %d %s blog post(s)", len(posts), lang.upper())
    return posts


def link_translations(en_posts: list, ru_posts: list) -> list:
    """Pair EN and RU posts by slug and build the RU listing.

    Sets alt_url on every post (its counterpart, or the other language's home
    page when there is none). The RU listing holds every RU translation plus the
    untranslated EN posts, flagged en_only so the template can mark them.
    """
    ru_by_slug = {p["slug"]: p for p in ru_posts}
    en_by_slug = {p["slug"]: p for p in en_posts}
    for post in en_posts:
        ru = ru_by_slug.get(post["slug"])
        post["translated"] = bool(ru)
        post["alt_url"] = ru["url"] if ru else lang_prefix("ru")
    for post in ru_posts:
        en = en_by_slug.get(post["slug"])
        post["translated"] = bool(en)
        post["alt_url"] = en["url"] if en else lang_prefix("en")
    listing = list(ru_posts) + [
        {**p, "en_only": True, "date_human": _human_date(p["date"], "ru")}
        for p in en_posts
        if p["slug"] not in ru_by_slug
    ]
    listing.sort(key=lambda p: p["date"], reverse=True)
    return listing


def asset_version(path: str) -> str:
    """Short content hash of a static asset, appended as ?v= so browsers and the CDN
    fetch the new file on every change instead of serving a stale cached copy."""
    try:
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:10]
    except FileNotFoundError:
        logger.warning("Asset not found for versioning: %s", path)
        return ""


def load_youtube_cache(cache_file: str = ".youtube_cache.json") -> dict:
    """Load cached YouTube video data from file"""
    cache_path = Path(cache_file)
    if cache_path.exists():
        logger.info(f"Loading YouTube cache from {cache_file}")
        with open(cache_path, "r", encoding="utf-8") as f:
            return json.load(f)
    logger.info("No YouTube cache found, will fetch all videos")
    return {}


def save_youtube_cache(cache_data: dict, cache_file: str = ".youtube_cache.json"):
    """Save YouTube video data to cache file"""
    cache_path = Path(cache_file)
    logger.info(f"Saving YouTube cache to {cache_file} ({len(cache_data)} videos)")
    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache_data, f, indent=2, ensure_ascii=False)


def fetch_video_details(api: Api, video_id: str) -> dict:
    """Fetch video details from YouTube API"""
    logger.debug(f"Fetching video details for {video_id}")
    video = api.get_video_by_id(video_id=video_id).items[0]
    return {
        "title": video.snippet.title,
        "description": video.snippet.description,
        "publishedAt": video.snippet.publishedAt,
    }


logger.debug("Reading Jinja template from index.html.j2")
templateFile = open("./index.html.j2", mode="r")
template = Template(templateFile.read())
templateFile.close()

# Load Markdown content
content_dir = os.getenv("CONTENT_DIR", "content")
SECTIONS = ["about_me", "experience", "education", "skills", "highlights"]


def load_sections(lang: str) -> dict:
    """Render the page sections for a language, falling back to EN per file."""
    sections = {}
    for name in SECTIONS:
        path = os.path.join(content_dir, f"{name}.md")
        if LANGS[lang]:
            translated = os.path.join(content_dir, LANGS[lang], f"{name}.md")
            if os.path.exists(translated):
                path = translated
            else:
                logger.warning("No %s translation of %s, using EN", lang, name)
        sections[f"{name}_html"] = load_markdown(path)
    return sections


# Load blog posts: EN originals and RU translations, paired by slug
en_posts = load_blog_posts(content_dir, "en")
ru_posts = load_blog_posts(content_dir, "ru")
posts_by_lang = {"en": en_posts, "ru": link_translations(en_posts, ru_posts)}

# Cache-busting token for the stylesheet (built by `task build-css` before this script).
css_version = asset_version("css/tailwind.css")

# Load cache first — it lets the site build (videos + blog) even if the API key
# is absent (local preview) or the API call fails.
youtube_cache = load_youtube_cache()
logger.info(f"Loaded {len(youtube_cache)} videos from cache")

youtube_api_key = os.environ.get("YOUTUBE_API_KEY")
if youtube_api_key:
    logger.debug("Initializing YouTube API client")
    api = Api(api_key=youtube_api_key)

    logger.debug("Fetching playlist items (IDs only)")
    playlist_item_by_playlist = api.get_playlist_items(
        playlist_id="PLAGNQxMisRs1F-1CryCRWKjmEsj5GAy6y", count=100
    )
    logger.debug("Fetched %d playlist items", len(playlist_item_by_playlist.items))

    # Extract video IDs from playlist
    playlist_video_ids = [
        item.contentDetails.videoId for item in playlist_item_by_playlist.items
    ]
    logger.info(f"Found {len(playlist_video_ids)} videos in playlist")

    # Find new videos (not in cache)
    new_video_ids = [vid for vid in playlist_video_ids if vid not in youtube_cache]
    logger.info(f"Found {len(new_video_ids)} new videos to fetch")

    # Fetch details only for new videos
    youtube_raw = dict(youtube_cache)  # Start with cached data
    for video_id in new_video_ids:
        logger.info(f"Fetching new video: {video_id}")
        try:
            video_data = fetch_video_details(api, video_id)
            youtube_raw[video_id] = video_data
        except Exception as e:
            logger.error(f"Failed to fetch video {video_id}: {e}")

    # Remove videos that are no longer in the playlist
    youtube_raw = {
        vid: data for vid, data in youtube_raw.items() if vid in playlist_video_ids
    }
    logger.info(f"Total videos after cleanup: {len(youtube_raw)}")

    # Save updated cache
    save_youtube_cache(youtube_raw)
else:
    logger.warning(
        "YOUTUBE_API_KEY not set — building from cache only (videos may be empty)"
    )
    youtube_raw = dict(youtube_cache)

logger.debug("Sorting %d videos by publishedAt desc", len(youtube_raw))
youtube = sorted(youtube_raw.items(), key=lambda x: x[1]["publishedAt"], reverse=True)

# Group videos by parsed title
logger.debug("Grouping videos by title pattern")
youtube_groups = {
    "DevOps Kitchen Talks": [],
    "Public talks": [],
}
for vid, info in youtube:
    logging.info(f"Processing video {info['title']}")
    group = classify_video_group(info["title"]) if "title" in info else "Public talks"
    logger.info("Video '%s' assigned to group '%s'", info.get("title", vid), group)
    youtube_groups.setdefault(group, []).append((vid, info))

has_groups = any(len(items) > 0 for items in youtube_groups.values())
logger.debug("has_groups=%s", has_groups)

ci = bool(os.getenv("CI", False))


def write_html(out_path: Path, rendered: str):
    if ci:
        # Imported lazily: minify_html is only needed for CI builds, and avoiding
        # the hard import lets the site render locally without a Rust toolchain.
        import minify_html

        rendered = minify_html.minify(rendered)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(rendered, encoding="utf-8")


with open("./post.html.j2", mode="r") as f:
    post_template = Template(f.read())

for lang in LANGS:
    base = lang_prefix(lang)
    other = "ru" if lang == "en" else "en"
    posts = posts_by_lang[lang]
    logger.debug("Rendering %s HTML with %d total videos", lang.upper(), len(youtube))
    html = template.render(
        youtube_links=youtube,
        youtube_groups=youtube_groups,
        has_groups=has_groups,
        posts=posts,
        namespaces=build_namespaces(posts),
        css_version=css_version,
        lang=lang,
        t=I18N[lang],
        base=base,
        alt_url=lang_prefix(other),
        alternates={code: f"{BASE_URL}{lang_prefix(code)}" for code in LANGS},
        base_url=BASE_URL,
        **load_sections(lang),
    )
    out_dir = Path(LANGS[lang]) if LANGS[lang] else Path(".")
    write_html(out_dir / "index.html", html)
    logger.info("Generation complete: %s", out_dir / "index.html")

    # Blog post pages: <prefix>/blog/<slug>/index.html, only for posts written
    # in this language (untranslated EN posts in the RU listing link to EN).
    own = [p for p in posts if p["lang"] == lang]
    for post in own:
        logger.info("Rendering %s blog post: %s", lang.upper(), post["slug"])
        alternates = {lang: post["canonical"]}
        if post["translated"]:
            alternates[other] = f"{BASE_URL}{post['alt_url']}"
        post_html = post_template.render(
            post=post,
            posts=posts,
            css_version=css_version,
            lang=lang,
            t=I18N[lang],
            base=base,
            alternates=alternates,
        )
        write_html(out_dir / "blog" / post["slug"] / "index.html", post_html)
    logger.info("Rendered %d %s blog post page(s)", len(own), lang.upper())
