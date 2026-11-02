import os
import sys
import json
import sqlite3
import random
from typing import Optional, List, Dict, Any
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import numpy as np

from video_fetcher import (
    extract_video_id,
    fetch_youtube_metadata,
    fetch_dislike_stats,
    fetch_hn_comments,
    fetch_youtube_top_comments,
    assign_tags_and_categories
)

# Base paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
STATIC_DIR = os.path.join(BASE_DIR, "static")
DB_PATH = os.path.join(DATA_DIR, "rexan.db")

app = FastAPI(title="Rexan", description="Cloned from HackerTube, rebranded to rexan.in")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class AddVideoRequest(BaseModel):
    url: str
    title: Optional[str] = None
    channel: Optional[str] = None
    summary: Optional[str] = None
    tags: Optional[List[str]] = None
    categories: Optional[List[Dict[str, Any]]] = None
    playlist_slug: Optional[str] = None
    custom_note: Optional[str] = None

# In-memory caches for fast lookup
embeddings = None
embedding_ids = []
vid_to_emb_idx: Dict[str, int] = {}
playlists_cache: List[Dict[str, Any]] = []
playlists_by_slug: Dict[str, Dict[str, Any]] = {}
taxonomy_cache: Dict[str, Any] = {}
stats_cache: Dict[str, Any] = {}
browse_cache: List[Dict[str, Any]] = []

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

@app.on_event("startup")
def startup_event():
    global embeddings, embedding_ids, vid_to_emb_idx
    global playlists_cache, playlists_by_slug, taxonomy_cache, stats_cache, browse_cache

    print("Initializing Rexan server caches...")

    # Ensure database exists
    if not os.path.exists(DB_PATH):
        try:
            from build_db import build_database
            print(f"Database not found at {DB_PATH}. Building database from data files...")
            build_database(DATA_DIR)
        except Exception as e:
            print(f"Warning: Failed to auto-build database: {e}")
    
    # 1. Load taxonomy
    tax_file = os.path.join(DATA_DIR, "taxonomy.json")
    if os.path.exists(tax_file):
        with open(tax_file, "r", encoding="utf-8") as f:
            taxonomy_cache = json.load(f)

    # 2. Load embeddings
    emb_file = os.path.join(DATA_DIR, "embeddings.npy")
    ids_file = os.path.join(DATA_DIR, "embedding_ids.json")
    if os.path.exists(emb_file) and os.path.exists(ids_file):
        try:
            embeddings = np.load(emb_file).astype(np.float32)
            with open(ids_file, "r", encoding="utf-8") as f:
                embedding_ids = json.load(f)
            vid_to_emb_idx = {vid: i for i, vid in enumerate(embedding_ids)}
            print(f"Loaded embeddings: {embeddings.shape}")
        except Exception as e:
            print(f"Warning: Could not load embeddings: {e}")

    # 3. Load playlists
    pl_file = os.path.join(DATA_DIR, "playlists.json")
    if os.path.exists(pl_file):
        with open(pl_file, "r", encoding="utf-8") as f:
            playlists_cache = json.load(f)
            playlists_by_slug = {p["slug"]: p for p in playlists_cache}
            print(f"Loaded {len(playlists_cache)} playlists")

    # 4. Compute / load stats & browse cache
    if os.path.exists(DB_PATH):
        conn = get_db()
        cur = conn.cursor()
        total_vids = cur.execute("SELECT COUNT(*) FROM videos").fetchone()[0]
        total_comments = cur.execute("SELECT COUNT(*) FROM mentions").fetchone()[0]
        total_recommenders = cur.execute("SELECT COUNT(DISTINCT author) FROM mentions WHERE stance IN ('rec', 'strong_rec')").fetchone()[0]
        min_year = cur.execute("SELECT MIN(first_year) FROM videos WHERE first_year > 0").fetchone()[0] or 2007
        max_year = cur.execute("SELECT MAX(last_year) FROM videos").fetchone()[0] or 2026
        
        areas = taxonomy_cache.get("areas", [])
        num_areas = len(areas)
        num_cats = sum(len(a.get("categories", [])) for a in areas)

        stats_cache = {
            "videos": total_vids,
            "comments": total_comments,
            "recommenders": total_recommenders,
            "first_year": str(min_year),
            "last_year": str(max_year),
            "areas": num_areas,
            "categories": num_cats
        }

        # Build browse cache with counts
        browse_list = []
        for a in areas:
            area_id = a["id"]
            area_vids = cur.execute("SELECT COUNT(DISTINCT vid) FROM video_categories WHERE area_id = ?", (area_id,)).fetchone()[0]
            cats_list = []
            for c in a.get("categories", []):
                cat_id = c["id"]
                cat_vids = cur.execute("SELECT COUNT(DISTINCT vid) FROM video_categories WHERE cat_id = ?", (cat_id,)).fetchone()[0]
                cats_list.append({
                    "id": cat_id,
                    "name": c["name"],
                    "count": cat_vids,
                    "description": c.get("description", "")
                })
            browse_list.append({
                "id": area_id,
                "name": a["name"],
                "count": area_vids,
                "categories": cats_list
            })
        browse_cache = browse_list
        conn.close()
        print("Stats and browse cache initialized.")

# ================= API Endpoints =================

@app.get("/api/config")
def get_config():
    return {"frames_source": "youtube"}

@app.get("/api/stats")
def get_stats():
    return stats_cache

@app.get("/api/browse")
def get_browse():
    return browse_cache

@app.get("/api/playlists")
def get_playlists():
    res = []
    for p in playlists_cache:
        res.append({
            "slug": p.get("slug"),
            "title": p.get("title"),
            "pitch": p.get("pitch"),
            "kind": p.get("kind", p.get("tier", "deep")),
            "tier": p.get("tier", "deep"),
            "minutes": p.get("minutes", 0),
            "count": p.get("count", len(p.get("videos", []))),
            "cover": p.get("cover", [v.get("vid") for v in p.get("videos", [])[:4]])
        })
    return res

@app.get("/api/playlist")
def get_playlist(slug: str = Query(...)):
    if slug not in playlists_by_slug:
        raise HTTPException(status_code=404, detail="Playlist not found")
    return playlists_by_slug[slug]

@app.get("/api/docs")
def get_docs(vids: str = Query("")):
    if not vids:
        return []
    vid_list = [v.strip() for v in vids.split(",") if v.strip()]
    if not vid_list:
        return []

    conn = get_db()
    cur = conn.cursor()
    placeholders = ",".join(["?"] * len(vid_list))
    rows = cur.execute(f"SELECT data_json, vid FROM videos WHERE vid IN ({placeholders})", vid_list).fetchall()
    conn.close()

    doc_map = {}
    for r in rows:
        try:
            doc_map[r["vid"]] = json.loads(r["data_json"])
        except Exception:
            pass

    # Preserve order of requested vids
    return [doc_map[v] for v in vid_list if v in doc_map]

@app.get("/api/video")
def get_video(vid: str = Query(...)):
    conn = get_db()
    cur = conn.cursor()
    row = cur.execute("SELECT data_json FROM videos WHERE vid = ?", (vid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Video not found")

    video_data = json.loads(row["data_json"])
    
    # Comments for this video
    cmt_rows = cur.execute("""
        SELECT id, author, ym, story, stance, why, quote, text
        FROM mentions WHERE vid = ?
        ORDER BY (stance = 'strong_rec') DESC, (stance = 'rec') DESC, ym DESC
    """, (vid,)).fetchall()
    conn.close()

    comments = [dict(c) for c in cmt_rows]

    # Fetch live or cached dislikes
    dislike_stats = fetch_dislike_stats(vid)
    if dislike_stats and dislike_stats.get("dislikes") is not None:
        video_data["dislikes"] = dislike_stats["dislikes"]
        if dislike_stats.get("likes"):
            video_data["likes"] = dislike_stats["likes"]

    return {
        "video": video_data,
        "comments": comments
    }

@app.get("/api/video/dislikes")
def get_video_dislikes(vid: str = Query(...)):
    stats = fetch_dislike_stats(vid)
    return stats

@app.get("/api/video/fetch-meta")
def fetch_meta_endpoint(url: str = Query(...)):
    vid = extract_video_id(url)
    if not vid:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL or Video ID")
    
    # Check if already in DB
    conn = get_db()
    cur = conn.cursor()
    row = cur.execute("SELECT data_json FROM videos WHERE vid = ?", (vid,)).fetchone()
    if row:
        video_data = json.loads(row["data_json"])
        cmt_rows = cur.execute("SELECT id, author, ym, story, stance, why, quote, text FROM mentions WHERE vid = ?", (vid,)).fetchall()
        conn.close()
        dislike_stats = fetch_dislike_stats(vid)
        return {
            "vid": vid,
            "title": video_data.get("title", ""),
            "channel": video_data.get("channel", ""),
            "duration_s": video_data.get("duration_s", 0),
            "views": video_data.get("views", 0),
            "likes": dislike_stats.get("likes") or video_data.get("likes", 0),
            "dislikes": dislike_stats.get("dislikes", 0),
            "summary": video_data.get("summary", ""),
            "thumbnail": video_data.get("thumbnail", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg"),
            "tags": video_data.get("tags", []),
            "categories": video_data.get("categories", []),
            "comments": [dict(c) for c in cmt_rows],
            "comments_source": video_data.get("comments_source", "existing"),
            "exists": True
        }
    conn.close()

    # Not in DB: fetch from YouTube + HN
    meta = fetch_youtube_metadata(vid)
    dislike_stats = fetch_dislike_stats(vid)
    
    # Check HN
    hn_comments = fetch_hn_comments(vid)
    if hn_comments:
        comments = hn_comments
        comments_source = "hackernews"
    else:
        comments = fetch_youtube_top_comments(vid)
        comments_source = "youtube"

    tags, cats = assign_tags_and_categories(meta["title"], meta["summary"], meta["channel"], taxonomy_cache)

    return {
        "vid": vid,
        "title": meta["title"],
        "channel": meta["channel"],
        "duration_s": meta["duration_s"],
        "views": meta["views"],
        "likes": dislike_stats.get("likes", 0),
        "dislikes": dislike_stats.get("dislikes", 0),
        "summary": meta["summary"],
        "thumbnail": meta["thumbnail"],
        "tags": tags,
        "categories": cats,
        "comments": comments,
        "comments_source": comments_source,
        "exists": False
    }

@app.post("/api/video/add")
def add_video_endpoint(req: AddVideoRequest):
    vid = extract_video_id(req.url)
    if not vid:
        raise HTTPException(status_code=400, detail="Invalid YouTube URL or Video ID")

    # Fetch metadata if title/channel/summary missing
    meta = fetch_youtube_metadata(vid)
    title = req.title.strip() if req.title and req.title.strip() else meta["title"]
    channel = req.channel.strip() if req.channel and req.channel.strip() else meta["channel"]
    summary = req.summary.strip() if req.summary and req.summary.strip() else meta["summary"]
    duration_s = meta.get("duration_s", 0)
    views = meta.get("views", 0)
    thumbnail = meta.get("thumbnail", f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg")

    dislike_stats = fetch_dislike_stats(vid)
    likes = dislike_stats.get("likes") or meta.get("views", 0) // 50

    # Check comments: HN first, else YouTube top 5
    hn_comments = fetch_hn_comments(vid)
    if hn_comments:
        comments = hn_comments
        comments_source = "hackernews"
    else:
        comments = fetch_youtube_top_comments(vid)
        comments_source = "youtube"

    # Tags & categories
    if req.tags is not None and len(req.tags) > 0:
        tags = [t.strip().lower() for t in req.tags if t.strip()]
    else:
        auto_tags, _ = assign_tags_and_categories(title, summary, channel, taxonomy_cache)
        tags = auto_tags

    if req.categories is not None and len(req.categories) > 0:
        categories = req.categories
    else:
        _, auto_cats = assign_tags_and_categories(title, summary, channel, taxonomy_cache)
        categories = auto_cats

    # Build video doc
    first_year = 2026
    last_year = 2026
    rec_months = len(set(c.get("ym", "2026-01") for c in comments)) or 1
    recommenders = len(set(c.get("author", "user") for c in comments)) or 1
    score = float(rec_months) + 1.0

    primary_topic = tags[0] if tags else "technology"
    whys = [c.get("why") for c in comments if c.get("why")][:5]
    if not whys:
        whys = [f"Recommended video by {channel}"]

    doc = {
        "vid": vid,
        "title": title,
        "channel": channel,
        "published": meta.get("published", "2026-01-01T00:00:00Z"),
        "duration_s": duration_s,
        "views": views,
        "likes": likes,
        "dislikes": dislike_stats.get("dislikes", 0),
        "thumbnail": thumbnail,
        "summary": summary,
        "why_hn": whys[0] if whys else f"Curated video by {channel}",
        "content_type": "talk",
        "level": "general",
        "shelf_life": "evergreen",
        "primary_topic": primary_topic,
        "tags": tags,
        "categories": categories,
        "quote": {
            "text": comments[0].get("quote", "") if comments else "",
            "id": comments[0].get("id", 0) if comments else 0,
            "year": "2026"
        },
        "hn": {
            "mentions": len(comments),
            "recommenders": recommenders,
            "stances": {"rec": len(comments)},
            "rec_months": rec_months,
            "strong": 1,
            "first": "2026",
            "last": "2026",
            "last_rec": "2026-01"
        },
        "score": score,
        "whys": whys,
        "hn_related": [],
        "comments_source": comments_source
    }

    # Save to SQLite DB
    conn = get_db()
    cur = conn.cursor()

    cur.execute("""
        INSERT INTO videos (
            vid, title, channel, published, duration_s, views, likes,
            summary, why_hn, content_type, level, shelf_life,
            primary_topic, score, first_year, last_year, rec_months,
            recommenders, last_rec, data_json
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(vid) DO UPDATE SET
            title=excluded.title,
            channel=excluded.channel,
            summary=excluded.summary,
            duration_s=excluded.duration_s,
            views=excluded.views,
            likes=excluded.likes,
            data_json=excluded.data_json
    """, (
        vid, title, channel, doc["published"], duration_s, views, likes,
        summary, doc["why_hn"], doc["content_type"], doc["level"], doc["shelf_life"],
        primary_topic, score, first_year, last_year, rec_months,
        recommenders, "2026-01", json.dumps(doc, ensure_ascii=False)
    ))

    # Categories
    cur.execute("DELETE FROM video_categories WHERE vid = ?", (vid,))
    for c in categories:
        cur.execute("INSERT OR IGNORE INTO video_categories (vid, cat_id, area_id) VALUES (?,?,?)",
                    (vid, c.get("id"), c.get("area")))

    # FTS5 index update
    cur.execute("DELETE FROM videos_fts WHERE vid = ?", (vid,))
    tags_str = " ".join(tags)
    cats_str = " ".join([c.get("name", "") for c in categories])
    cur.execute("""
        INSERT INTO videos_fts (vid, title, channel, summary, why_hn, primary_topic, tags, categories)
        VALUES (?,?,?,?,?,?,?,?)
    """, (vid, title, channel, summary, doc["why_hn"], primary_topic, tags_str, cats_str))

    # Mentions / comments
    cur.execute("DELETE FROM mentions WHERE vid = ?", (vid,))
    for m in comments:
        cur.execute("""
            INSERT INTO mentions (id, vid, author, ym, story, stance, why, quote, text)
            VALUES (?,?,?,?,?,?,?,?,?)
        """, (
            m.get("id", 0),
            vid,
            m.get("author", "user"),
            m.get("ym", "2026-01"),
            m.get("story", "Community recommendation"),
            m.get("stance", "rec"),
            m.get("why", ""),
            m.get("quote", ""),
            m.get("text", "")
        ))

    conn.commit()
    conn.close()

    # Append to playlist if chosen
    if req.playlist_slug and req.playlist_slug in playlists_by_slug:
        pl = playlists_by_slug[req.playlist_slug]
        pl_vids = pl.setdefault("videos", [])
        if not any(v.get("vid") == vid for v in pl_vids):
            pl_vids.append({
                "vid": vid,
                "title": title,
                "channel": channel,
                "duration_s": duration_s,
                "views": views,
                "published": doc["published"],
                "note": req.custom_note.strip() if req.custom_note else (whys[0] if whys else "Added via Rexan")
            })
            pl["count"] = len(pl_vids)
            pl["minutes"] = sum((v.get("duration_s", 0) for v in pl_vids)) // 60
            
            # Save updated playlists.json
            pl_file = os.path.join(DATA_DIR, "playlists.json")
            with open(pl_file, "w", encoding="utf-8") as f:
                json.dump(playlists_cache, f, indent=2, ensure_ascii=False)

    return {
        "success": True,
        "vid": vid,
        "title": title,
        "comments_source": comments_source,
        "comments_count": len(comments),
        "redirect_url": f"/watch/{vid}"
    }

@app.get("/api/related")
def get_related(vid: str = Query(...), n: int = Query(20)):
    conn = get_db()
    cur = conn.cursor()
    
    # 1. First check graph of co-recommendations
    rows = cur.execute("""
        SELECT v.data_json
        FROM related r
        JOIN videos v ON r.related_vid = v.vid
        WHERE r.vid = ?
        ORDER BY r.shared DESC, v.score DESC
        LIMIT ?
    """, (vid, n)).fetchall()

    results = []
    seen = {vid}
    for r in rows:
        try:
            d = json.loads(r["data_json"])
            results.append(d)
            seen.add(d["vid"])
        except Exception:
            pass

    # 2. If fewer than n, fill with semantic vector similarity
    if len(results) < n and embeddings is not None and vid in vid_to_emb_idx:
        idx = vid_to_emb_idx[vid]
        target_vec = embeddings[idx]
        sims = embeddings @ target_vec
        best_indices = np.argsort(-sims)
        
        needed = n - len(results)
        candidate_vids = []
        for i in best_indices:
            cand = embedding_ids[i]
            if cand not in seen:
                candidate_vids.append(cand)
                seen.add(cand)
                if len(candidate_vids) >= needed:
                    break

        if candidate_vids:
            placeholders = ",".join(["?"] * len(candidate_vids))
            sim_rows = cur.execute(f"SELECT data_json, vid FROM videos WHERE vid IN ({placeholders})", candidate_vids).fetchall()
            sim_map = {r["vid"]: json.loads(r["data_json"]) for r in sim_rows}
            for cv in candidate_vids:
                if cv in sim_map:
                    results.append(sim_map[cv])

    conn.close()
    return results[:n]

def apply_filters_sql(where_clauses: List[str], params: List[Any],
                      date: str, vtype: str, dur: str, gems: str, evergreen: str):
    if date == "year":
        where_clauses.append("published >= date('now', '-1 year')")
    elif date == "2020s":
        where_clauses.append("published >= '2020-01-01'")
    elif date == "2010s":
        where_clauses.append("published >= '2010-01-01' AND published < '2020-01-01'")
    elif date == "2000s":
        where_clauses.append("published >= '2000-01-01' AND published < '2010-01-01'")

    if vtype:
        where_clauses.append("content_type = ?")
        params.append(vtype)

    if dur == "short":
        where_clauses.append("duration_s > 0 AND duration_s < 240")
    elif dur == "medium":
        where_clauses.append("duration_s >= 240 AND duration_s <= 1200")
    elif dur == "long":
        where_clauses.append("duration_s > 1200 AND duration_s <= 3600")
    elif dur == "xlong":
        where_clauses.append("duration_s > 3600")

    if gems == "1":
        where_clauses.append("views > 0 AND views < 100000 AND score >= 1.5")

    if evergreen == "1":
        where_clauses.append("shelf_life != 'news'")

def get_order_sql(sort: str, default: str = "v.score DESC") -> str:
    if sort == "recent":
        return "v.last_year DESC, v.last_rec DESC, v.score DESC"
    elif sort == "date":
        return "v.published DESC"
    elif sort == "old":
        return "v.published ASC"
    elif sort == "views":
        return "v.views DESC"
    elif sort == "liked":
        return "(v.likes * 1.0 / MAX(v.views, 1)) DESC"
    elif sort == "hn":
        return "v.score DESC"
    return default

@app.get("/api/list")
def get_list(
    cat: Optional[str] = None,
    area: Optional[str] = None,
    date: str = "",
    type: str = "",
    dur: str = "",
    gems: str = "",
    evergreen: str = "",
    sort: str = "",
    offset: int = 0,
    n: int = 36
):
    conn = get_db()
    cur = conn.cursor()

    where = []
    params = []

    if cat:
        where.append("v.vid IN (SELECT vid FROM video_categories WHERE cat_id = ?)")
        params.append(cat)
    elif area:
        where.append("v.vid IN (SELECT vid FROM video_categories WHERE area_id = ?)")
        params.append(area)

    apply_filters_sql(where, params, date, type, dur, gems, evergreen)
    
    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = get_order_sql(sort, "v.score DESC")

    query = f"""
        SELECT v.data_json
        FROM videos v
        {where_sql}
        ORDER BY {order_sql}
        LIMIT ? OFFSET ?
    """
    params.extend([n, offset])
    
    rows = cur.execute(query, params).fetchall()
    conn.close()

    return [json.loads(r["data_json"]) for r in rows]

@app.get("/api/search")
def search(
    q: str = Query(...),
    date: str = "",
    type: str = "",
    dur: str = "",
    gems: str = "",
    evergreen: str = "",
    sort: str = "",
    limit: int = 50
):
    query_str = q.strip()
    if not query_str:
        return {"results": [], "weak": False}

    conn = get_db()
    cur = conn.cursor()

    # Clean query for FTS5 (remove punctuation, handle quotes)
    clean_terms = [t for t in "".join(c if c.isalnum() else " " for c in query_str).split() if t]
    if not clean_terms:
        conn.close()
        return {"results": [], "weak": False}

    fts_query = " OR ".join([f"{term}*" for term in clean_terms])
    
    filter_clauses = []
    filter_params = []
    apply_filters_sql(filter_clauses, filter_params, date, type, dur, gems, evergreen)
    filter_sql = ("AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

    order_sql = get_order_sql(sort, "rank, v.score DESC")
    if sort:
        order_by = get_order_sql(sort, "v.score DESC")
    else:
        order_by = "rank, v.score DESC"

    sql = f"""
        SELECT v.data_json, f.rank, v.vid
        FROM videos_fts f
        JOIN videos v ON f.vid = v.vid
        WHERE videos_fts MATCH ?
        {filter_sql}
        ORDER BY {order_by}
        LIMIT ?
    """
    params = [fts_query] + filter_params + [limit]
    
    rows = cur.execute(sql, params).fetchall()
    
    results = []
    for r in rows:
        d = json.loads(r["data_json"])
        # compute relevance score
        d["relevance"] = max(0.5, min(0.99, round(1.0 - (float(r["rank"]) / -10.0), 2)))
        d["via"] = None
        results.append(d)

    # If few results, supplement with semantic search if embeddings exist
    weak = len(results) < 3
    if len(results) < limit and embeddings is not None:
        # Check if query matches any topic category in taxonomy for expansion
        cat_matches = []
        for a in taxonomy_cache.get("areas", []):
            for c in a.get("categories", []):
                if any(t.lower() in c["name"].lower() or t.lower() in c.get("description", "").lower() for t in clean_terms):
                    cat_matches.append(c["id"])

        if cat_matches:
            seen_vids = {r["vid"] for r in results}
            cat_placeholders = ",".join(["?"] * len(cat_matches))
            cat_sql = f"""
                SELECT v.data_json, v.vid
                FROM video_categories vc
                JOIN videos v ON vc.vid = v.vid
                WHERE vc.cat_id IN ({cat_placeholders})
                {filter_sql}
                ORDER BY v.score DESC
                LIMIT ?
            """
            c_rows = cur.execute(cat_sql, cat_matches + filter_params + [limit - len(results)]).fetchall()
            for r in c_rows:
                if r["vid"] not in seen_vids:
                    d = json.loads(r["data_json"])
                    d["relevance"] = 0.65
                    d["via"] = d.get("primary_topic", "Topic match")
                    results.append(d)
                    seen_vids.add(r["vid"])

    conn.close()
    return {"results": results, "weak": weak}

@app.get("/api/feed")
def get_feed(
    like: str = "",
    dislike: str = "",
    seen: str = "",
    seed: str = "42",
    date: str = "",
    type: str = "",
    dur: str = "",
    gems: str = "",
    evergreen: str = "",
    offset: int = 0,
    n: int = 36
):
    likes = [v.strip() for v in like.split(",") if v.strip()]
    dislikes = set(v.strip() for v in dislike.split(",") if v.strip())
    seen_set = set(v.strip() for v in seen.split(",") if v.strip())
    excluded = dislikes | seen_set

    # Seeded PRNG for reproducible pagination
    rng = random.Random(f"{seed}_{offset}")

    conn = get_db()
    cur = conn.cursor()

    filter_clauses = []
    filter_params = []
    apply_filters_sql(filter_clauses, filter_params, date, type, dur, gems, evergreen)
    filter_sql = ("AND " + " AND ".join(filter_clauses)) if filter_clauses else ""

    candidates = []

    # 1. If likes present, pull related videos
    if likes:
        placeholders = ",".join(["?"] * len(likes))
        rel_sql = f"""
            SELECT v.data_json, r.shared
            FROM related r
            JOIN videos v ON r.related_vid = v.vid
            WHERE r.vid IN ({placeholders})
            {filter_sql}
            ORDER BY r.shared DESC, v.score DESC
            LIMIT 40
        """
        for r in cur.execute(rel_sql, likes + filter_params).fetchall():
            d = json.loads(r["data_json"])
            if d["vid"] not in excluded:
                d["source"] = "likes"
                d["reason"] = "Recommended because of your likes"
                candidates.append(d)

    # 2. Classics
    classics_sql = f"""
        SELECT data_json FROM videos v
        WHERE score >= 10.0 {filter_sql}
        ORDER BY score DESC LIMIT 100
    """
    for r in cur.execute(classics_sql, filter_params).fetchall():
        d = json.loads(r["data_json"])
        if d["vid"] not in excluded:
            d["source"] = "classics"
            d["reason"] = "An HN classic"
            candidates.append(d)

    # 3. Hidden gems
    gems_sql = f"""
        SELECT data_json FROM videos v
        WHERE views > 0 AND views < 100000 AND score >= 2.0 {filter_sql}
        ORDER BY score DESC LIMIT 100
    """
    for r in cur.execute(gems_sql, filter_params).fetchall():
        d = json.loads(r["data_json"])
        if d["vid"] not in excluded:
            d["source"] = "gems"
            d["reason"] = "Hidden gem: loved on HN, little-watched on YouTube"
            candidates.append(d)

    # 4. Recent
    recent_sql = f"""
        SELECT data_json FROM videos v
        WHERE last_year >= 2024 {filter_sql}
        ORDER BY last_year DESC, score DESC LIMIT 100
    """
    for r in cur.execute(recent_sql, filter_params).fetchall():
        d = json.loads(r["data_json"])
        if d["vid"] not in excluded:
            d["source"] = "recent"
            d["reason"] = "Recent on HN"
            candidates.append(d)

    # 5. Explore categories / areas
    explore_sql = f"""
        SELECT v.data_json, vc.area_id FROM videos v
        JOIN video_categories vc ON v.vid = vc.vid
        WHERE v.score >= 3.0 {filter_sql}
        ORDER BY v.score DESC LIMIT 150
    """
    for r in cur.execute(explore_sql, filter_params).fetchall():
        d = json.loads(r["data_json"])
        if d["vid"] not in excluded:
            area_name = d.get("categories", [{}])[0].get("area_name", "Technology")
            d["source"] = "explore"
            d["reason"] = f"Explore: {area_name}"
            candidates.append(d)

    # 6. Wildcard
    wildcard_sql = f"""
        SELECT data_json FROM videos v
        WHERE score >= 1.5 {filter_sql}
        ORDER BY RANDOM() LIMIT 50
    """
    for r in cur.execute(wildcard_sql, filter_params).fetchall():
        d = json.loads(r["data_json"])
        if d["vid"] not in excluded:
            d["source"] = "wildcard"
            d["reason"] = "Random pick"
            candidates.append(d)

    conn.close()

    # Deduplicate candidates while keeping diversity
    unique_candidates = []
    seen_cands = set()
    for c in candidates:
        if c["vid"] not in seen_cands:
            seen_cands.add(c["vid"])
            unique_candidates.append(c)

    # Shuffle using seeded PRNG
    rng.shuffle(unique_candidates)

    start = offset % max(len(unique_candidates), 1)
    page = unique_candidates[start:start + n]
    if len(page) < n and len(unique_candidates) > 0:
        page.extend(unique_candidates[:n - len(page)])

    return page

@app.get("/api/export")
def get_export():
    zip_path = os.path.join(DATA_DIR, "rexan-data.zip")
    zip_bytes = os.path.getsize(zip_path) if os.path.exists(zip_path) else 17800000

    def file_info(name, rows=None):
        p = os.path.join(DATA_DIR, name)
        b = os.path.getsize(p) if os.path.exists(p) else 0
        return {"name": name, "bytes": b, "rows": rows}

    return {
        "name": "rexan-data",
        "generated": "2026-10-31",
        "videos": stats_cache.get("videos", 6454),
        "mentions": stats_cache.get("comments", 39834),
        "zip": {"name": "rexan-data.zip", "bytes": zip_bytes},
        "files": [
            file_info("DATA.md", None),
            file_info("videos.jsonl", stats_cache.get("videos", 6454)),
            file_info("mentions.jsonl", stats_cache.get("comments", 39834)),
            file_info("taxonomy.json", stats_cache.get("categories", 150)),
            file_info("related.jsonl", 3778),
            file_info("embeddings.npy", stats_cache.get("videos", 6454)),
            file_info("embedding_ids.json", stats_cache.get("videos", 6454))
        ]
    }

@app.get("/download/{filename}")
def download_file(filename: str):
    safe_name = os.path.basename(filename)
    path = os.path.join(DATA_DIR, safe_name)
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="File not found")
    return FileResponse(path, filename=safe_name)

# ================= SPA Frontend Routing =================

# Serve index.html for all frontend routes
@app.get("/", response_class=HTMLResponse)
@app.get("/watch/{path:path}", response_class=HTMLResponse)
@app.get("/c/{path:path}", response_class=HTMLResponse)
@app.get("/a/{path:path}", response_class=HTMLResponse)
@app.get("/p/{path:path}", response_class=HTMLResponse)
@app.get("/browse", response_class=HTMLResponse)
@app.get("/search/{path:path}", response_class=HTMLResponse)
@app.get("/liked", response_class=HTMLResponse)
@app.get("/history", response_class=HTMLResponse)
@app.get("/later", response_class=HTMLResponse)
@app.get("/categories", response_class=HTMLResponse)
@app.get("/playlists", response_class=HTMLResponse)
@app.get("/about", response_class=HTMLResponse)
@app.get("/settings", response_class=HTMLResponse)
@app.get("/data", response_class=HTMLResponse)
@app.get("/add", response_class=HTMLResponse)
@app.get("/extension", response_class=HTMLResponse)
def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if not os.path.exists(index_file):
        raise HTTPException(status_code=404, detail="Frontend index.html not found")
    with open(index_file, "r", encoding="utf-8") as f:
        return HTMLResponse(content=f.read())

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    print(f"Starting Rexan server on port {port}...")
    uvicorn.run("server:app", host="0.0.0.0", port=port, reload=False)
