import urllib.request
import json
import ssl
import re
import html
from typing import Optional, Dict, Any, List, Tuple

_ctx = ssl._create_unverified_context()

def extract_video_id(url_or_id: str) -> Optional[str]:
    if not url_or_id:
        return None
    url_or_id = url_or_id.strip()
    # Match standard youtube url formats
    m = re.search(r'(?:v=|youtu\.be/|embed/|/v/|/shorts/)([a-zA-Z0-9_-]{11})', url_or_id)
    if m:
        return m.group(1)
    if len(url_or_id) == 11 and re.match(r'^[a-zA-Z0-9_-]{11}$', url_or_id):
        return url_or_id
    return None

def strip_html(raw_html: str) -> str:
    if not raw_html:
        return ""
    clean = re.sub(r'<[^<]+?>', '', raw_html)
    return html.unescape(clean)

def fetch_youtube_metadata(vid: str) -> Dict[str, Any]:
    url = "https://www.youtube.com/youtubei/v1/player"
    payload = {
        "context": {"client": {"clientName": "WEB", "clientVersion": "2.20230526.00.00"}},
        "videoId": vid
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
    )
    
    title = f"YouTube Video ({vid})"
    channel = "YouTube Creator"
    duration_s = 0
    views = 0
    summary = ""
    thumbnail = f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"
    
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=10) as resp:
            data = json.load(resp)
            details = data.get("videoDetails", {})
            title = details.get("title") or title
            channel = details.get("author") or channel
            duration_s = int(details.get("lengthSeconds") or 0)
            views = int(details.get("viewCount") or 0)
            summary = details.get("shortDescription") or ""
            if summary and len(summary) > 300:
                summary = summary[:297] + "..."
    except Exception as e:
        print(f"Warning: YouTube Innertube fetch failed: {e}")
        # Fallback to oembed
        try:
            oembed_url = f"https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v={vid}&format=json"
            oreq = urllib.request.Request(oembed_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(oreq, context=_ctx, timeout=5) as oresp:
                odata = json.load(oresp)
                title = odata.get("title") or title
                channel = odata.get("author_name") or channel
        except Exception:
            pass

    return {
        "vid": vid,
        "title": title,
        "channel": channel,
        "duration_s": duration_s,
        "views": views,
        "summary": summary or f"A talk and video by {channel} on YouTube.",
        "thumbnail": thumbnail,
        "published": "2026-01-01T00:00:00Z"
    }

def fetch_dislike_stats(vid: str) -> Dict[str, Any]:
    url = f"https://returnyoutubedislikeapi.com/votes?videoId={vid}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=4) as resp:
            data = json.load(resp)
            return {
                "likes": int(data.get("likes") or 0),
                "dislikes": int(data.get("dislikes") or 0),
                "rating": float(data.get("rating") or 5.0)
            }
    except Exception:
        return {"likes": 0, "dislikes": 0, "rating": 5.0}

def fetch_hn_comments(vid: str) -> List[Dict[str, Any]]:
    url = f"https://hn.algolia.com/api/v1/search?query={vid}&tags=comment"
    req = urllib.request.Request(url, headers={"User-Agent": "Rexan/1.0"})
    comments = []
    try:
        with urllib.request.urlopen(req, context=_ctx, timeout=8) as resp:
            data = json.load(resp)
            hits = data.get("hits", [])
            for h in hits[:20]:
                raw_text = h.get("comment_text", "")
                clean_text = strip_html(raw_text)
                if not clean_text or len(clean_text) < 20:
                    continue
                created = h.get("created_at", "")
                ym = created[:7] if len(created) >= 7 else "2024-01"
                story = h.get("story_title") or "Hacker News discussion"
                comments.append({
                    "id": int(h.get("objectID") or 0),
                    "author": h.get("author") or "hn_user",
                    "ym": ym,
                    "story": story,
                    "stance": "rec",
                    "why": "Recommended on Hacker News",
                    "quote": clean_text[:180] + ("..." if len(clean_text) > 180 else ""),
                    "text": clean_text[:1500]
                })
    except Exception as e:
        print(f"Warning: HN Algolia fetch failed: {e}")
    return comments

def fetch_youtube_top_comments(vid: str) -> List[Dict[str, Any]]:
    comments = []
    try:
        # Step 1: get continuation token
        req1 = urllib.request.Request(
            "https://www.youtube.com/youtubei/v1/next",
            data=json.dumps({
                "context": {"client": {"clientName": "WEB", "clientVersion": "2.20230526.00.00"}},
                "videoId": vid
            }).encode("utf-8"),
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
        )
        token = None
        with urllib.request.urlopen(req1, context=_ctx, timeout=8) as r1:
            d1 = json.load(r1)
            panels = d1.get("engagementPanels", [])
            for p in panels:
                p_rend = p.get("engagementPanelSectionListRenderer", {})
                if p_rend.get("panelIdentifier") == "engagement-panel-comments-section":
                    contents = p_rend.get("content", {}).get("sectionListRenderer", {}).get("contents", [])
                    for c_sec in contents:
                        items = c_sec.get("itemSectionRenderer", {}).get("contents", [])
                        for item in items:
                            cmd = item.get("continuationItemRenderer", {}).get("continuationEndpoint", {}).get("continuationCommand", {})
                            if cmd.get("token"):
                                token = cmd.get("token")
                                break

        # Step 2: call next with continuation token
        if token:
            req2 = urllib.request.Request(
                "https://www.youtube.com/youtubei/v1/next",
                data=json.dumps({
                    "context": {"client": {"clientName": "WEB", "clientVersion": "2.20230526.00.00"}},
                    "continuation": token
                }).encode("utf-8"),
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req2, context=_ctx, timeout=8) as r2:
                d2 = json.load(r2)
                mutations = d2.get("frameworkUpdates", {}).get("entityBatchUpdate", {}).get("mutations", [])
                for m in mutations:
                    cp = m.get("payload", {}).get("commentEntityPayload")
                    if cp:
                        author = cp.get("author", {}).get("displayName") or "YouTube User"
                        text = cp.get("properties", {}).get("content", {}).get("content") or ""
                        likes = cp.get("toolbar", {}).get("likeCountNotliked") or "0"
                        if text:
                            cid = abs(hash(f"{author}_{text[:30]}")) % 100000000
                            comments.append({
                                "id": cid,
                                "author": author.lstrip("@"),
                                "ym": "YouTube",
                                "story": "Top YouTube Community Comment",
                                "stance": "rec",
                                "why": f"{likes} likes on YouTube",
                                "quote": text[:180] + ("..." if len(text) > 180 else ""),
                                "text": text[:1500]
                            })
                            if len(comments) >= 5:
                                break
    except Exception as e:
        print(f"Warning: YouTube comments fetch failed: {e}")

    # Fallback placeholder if no comments found (e.g. comments disabled on video)
    if not comments:
        comments.append({
            "id": abs(hash(f"yt_cmt_{vid}")) % 100000000,
            "author": "Community",
            "ym": "Rexan",
            "story": "Added via Rexan",
            "stance": "rec",
            "why": "Curated video added to Rexan",
            "quote": "Added to Rexan collection.",
            "text": "Curated video added directly to the Rexan video catalog."
        })
    return comments

def assign_tags_and_categories(title: str, summary: str, channel: str, taxonomy: dict) -> Tuple[List[str], List[dict]]:
    t_words = set(re.findall(r'\b[a-z]{4,}\b', title.lower()))
    stopwords = {"music", "future", "projects", "help", "thanks", "video", "channel", "subscribe", "patreon"}
    s_words = set(re.findall(r'\b[a-z]{4,}\b', summary.lower())) - stopwords
    
    assigned_cats = []
    tags = set()

    # Pre-extract common technical and conceptual tags
    common_tags = [
        "python", "rust", "javascript", "typescript", "c++", "golang", "go",
        "linux", "database", "sql", "distributed systems", "concurrency",
        "machine learning", "deep learning", "ai", "neural networks", "llm",
        "functional programming", "haskell", "lisp", "compilers", "architecture",
        "security", "cryptography", "graphics", "game development", "algorithms",
        "mathematics", "linear algebra", "calculus", "physics", "hardware",
        "retrocomputing", "tutorial", "lecture", "talk", "documentary"
    ]
    full_text = f"{title} {summary} {channel}".lower()
    for tag in common_tags:
        if re.search(r'\b' + re.escape(tag) + r'\b', full_text):
            tags.add(tag)

    # Channel as a tag
    if channel:
        clean_chan = re.sub(r'[^a-zA-Z0-9 ]', '', channel).strip().lower()
        if clean_chan and len(clean_chan) > 2:
            tags.add(clean_chan)

    # Match taxonomy areas and categories using weighted overlap
    areas = taxonomy.get("areas", [])
    for a in areas:
        area_id = a.get("id")
        area_name = a.get("name")
        for c in a.get("categories", []):
            cat_id = c.get("id")
            cat_name = c.get("name")
            desc = c.get("description", "").lower()
            
            cat_words = set(re.findall(r'\b[a-z]{4,}\b', cat_name.lower() + ' ' + desc))
            score = (len(t_words & cat_words) * 10) + len(s_words & cat_words)

            if score > 0:
                assigned_cats.append({
                    "id": cat_id,
                    "name": cat_name,
                    "area": area_id,
                    "area_name": area_name,
                    "score": score
                })

    assigned_cats.sort(key=lambda x: x["score"], reverse=True)
    final_cats = [{
        "id": c["id"],
        "name": c["name"],
        "area": c["area"],
        "area_name": c["area_name"]
    } for c in assigned_cats[:2]]

    # If no category matched, assign general Software or Ideas category
    if not final_cats:
        final_cats = [{
            "id": "software-architecture-design",
            "name": "Software architecture & design",
            "area": "software",
            "area_name": "Software Engineering & Languages"
        }]

    # Ensure at least 3 tags
    if not tags:
        tags.update(["technology", "programming", "talk"])
    elif len(tags) < 3:
        tags.add("talk")
        tags.add("curated")

    return sorted(list(tags))[:8], final_cats
