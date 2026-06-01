#!env python3
import json
import logging
import os
import re
from pathlib import Path

import minify_html
from jinja2 import Template
from markdown import markdown
from pyyoutube import Api

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
about_me_html = load_markdown(os.path.join(content_dir, "about_me.md"))
experience_html = load_markdown(os.path.join(content_dir, "experience.md"))
education_html = load_markdown(os.path.join(content_dir, "education.md"))
skills_html = load_markdown(os.path.join(content_dir, "skills.md"))
highlights_html = load_markdown(os.path.join(content_dir, "highlights.md"))

logger.debug("Initializing YouTube API client")
api = Api(api_key=os.environ["YOUTUBE_API_KEY"])

# Load cache
youtube_cache = load_youtube_cache()
logger.info(f"Loaded {len(youtube_cache)} videos from cache")

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

logger.debug("Rendering HTML with %d total videos", len(youtube))
html = template.render(
    youtube_links=youtube,
    youtube_groups=youtube_groups,
    has_groups=has_groups,
    about_me_html=about_me_html,
    experience_html=experience_html,
    education_html=education_html,
    skills_html=skills_html,
    highlights_html=highlights_html,
)

logger.debug("Writing output to index.html")
htmlFile = open("./index.html", mode="w+")
if os.getenv("CI", False):
    logger.debug("CI detected: minifying HTML output")
    html = minify_html.minify(html)
htmlFile.write(html)
htmlFile.close()
logger.info("Generation complete: index.html updated")
