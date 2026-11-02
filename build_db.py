import sqlite3
import json
import os
import sys

def build_database(data_dir: str):
    zip_path = os.path.join(data_dir, "rexan-data.zip")
    if not os.path.exists(os.path.join(data_dir, "videos.jsonl")) and os.path.exists(zip_path):
        import zipfile
        print(f"Extracting {zip_path} into {data_dir}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(data_dir)

    db_path = os.path.join(data_dir, "rexan.db")
    if os.path.exists(db_path):
        os.remove(db_path)
    
    print(f"Connecting to database at {db_path}...")
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("PRAGMA journal_mode = WAL;")
    cur.execute("PRAGMA synchronous = NORMAL;")
    
    # 1. Create tables
    cur.execute("""
    CREATE TABLE videos (
        vid TEXT PRIMARY KEY,
        title TEXT,
        channel TEXT,
        published TEXT,
        duration_s INTEGER,
        views INTEGER,
        likes INTEGER,
        summary TEXT,
        why_hn TEXT,
        content_type TEXT,
        level TEXT,
        shelf_life TEXT,
        primary_topic TEXT,
        score REAL,
        first_year INTEGER,
        last_year INTEGER,
        rec_months INTEGER,
        recommenders INTEGER,
        last_rec TEXT,
        data_json TEXT
    );
    """)
    cur.execute("CREATE INDEX idx_videos_score ON videos(score DESC);")
    cur.execute("CREATE INDEX idx_videos_published ON videos(published DESC);")
    cur.execute("CREATE INDEX idx_videos_views ON videos(views DESC);")
    cur.execute("CREATE INDEX idx_videos_shelf_life ON videos(shelf_life);")
    cur.execute("CREATE INDEX idx_videos_content_type ON videos(content_type);")

    cur.execute("""
    CREATE TABLE video_categories (
        vid TEXT,
        cat_id TEXT,
        area_id TEXT,
        PRIMARY KEY(vid, cat_id)
    );
    """)
    cur.execute("CREATE INDEX idx_cat ON video_categories(cat_id);")
    cur.execute("CREATE INDEX idx_area ON video_categories(area_id);")

    cur.execute("""
    CREATE TABLE mentions (
        id INTEGER,
        vid TEXT,
        author TEXT,
        ym TEXT,
        story TEXT,
        stance TEXT,
        why TEXT,
        quote TEXT,
        text TEXT
    );
    """)
    cur.execute("CREATE INDEX idx_mentions_vid ON mentions(vid);")

    cur.execute("""
    CREATE TABLE related (
        vid TEXT,
        related_vid TEXT,
        shared INTEGER,
        PRIMARY KEY(vid, related_vid)
    );
    """)
    cur.execute("CREATE INDEX idx_related_vid ON related(vid);")

    # FTS5 search index
    cur.execute("""
    CREATE VIRTUAL TABLE videos_fts USING fts5(
        vid UNINDEXED,
        title,
        channel,
        summary,
        why_hn,
        primary_topic,
        tags,
        categories,
        tokenize='porter unicode61'
    );
    """)

    # 2. Load taxonomy descriptions for category expansion
    taxonomy_file = os.path.join(data_dir, "taxonomy.json")
    cat_desc = {}
    if os.path.exists(taxonomy_file):
        with open(taxonomy_file, "r", encoding="utf-8") as f:
            tax = json.load(f)
            for a in tax.get("areas", []):
                for c in a.get("categories", []):
                    cat_desc[c["id"]] = f"{c.get('name', '')} {c.get('description', '')}"

    # 3. Load videos (enriched if available, else standard)
    enriched_path = os.path.join(data_dir, "enriched_videos.jsonl")
    videos_path = os.path.join(data_dir, "videos.jsonl")
    
    source_file = enriched_path if os.path.exists(enriched_path) else videos_path
    print(f"Loading videos from {source_file}...")
    
    videos_rows = []
    cat_rows = []
    fts_rows = []
    seen_vids = set()

    with open(source_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            doc = json.loads(line)
            vid = doc["vid"]
            if vid in seen_vids:
                continue
            seen_vids.add(vid)

            hn = doc.get("hn", {})
            first_year = hn.get("first_year") or int(hn.get("first", 0) or 0)
            last_year = hn.get("last_year") or int(hn.get("last", 0) or 0)
            rec_months = hn.get("rec_months", 0)
            recommenders = hn.get("recommenders", 0)
            last_rec = hn.get("last_rec", "")

            # Ensure categories have full area data if missing
            categories = doc.get("categories", [])
            for c in categories:
                cid = c.get("id")
                aid = c.get("area")
                cat_rows.append((vid, cid, aid))

            videos_rows.append((
                vid,
                doc.get("title", ""),
                doc.get("channel", ""),
                doc.get("published", ""),
                doc.get("duration_s", 0),
                doc.get("views", 0),
                doc.get("likes", 0),
                doc.get("summary", ""),
                doc.get("why_hn", ""),
                doc.get("content_type", ""),
                doc.get("level", ""),
                doc.get("shelf_life", ""),
                doc.get("primary_topic", ""),
                float(doc.get("score", 0.0)),
                first_year,
                last_year,
                rec_months,
                recommenders,
                last_rec,
                json.dumps(doc, ensure_ascii=False)
            ))

            tags_str = " ".join(doc.get("tags", []))
            cats_str = " ".join([cat_desc.get(c.get("id"), c.get("name", "")) for c in categories])
            fts_rows.append((
                vid,
                doc.get("title", ""),
                doc.get("channel", ""),
                doc.get("summary", ""),
                doc.get("why_hn", ""),
                doc.get("primary_topic", ""),
                tags_str,
                cats_str
            ))

    cur.executemany("""
    INSERT INTO videos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
    """, videos_rows)

    cur.executemany("""
    INSERT OR IGNORE INTO video_categories VALUES (?,?,?);
    """, cat_rows)

    cur.executemany("""
    INSERT INTO videos_fts VALUES (?,?,?,?,?,?,?,?);
    """, fts_rows)

    print(f"Inserted {len(videos_rows)} videos.")

    # 4. Load mentions
    mentions_file = os.path.join(data_dir, "mentions.jsonl")
    if os.path.exists(mentions_file):
        print(f"Loading mentions from {mentions_file}...")
        m_rows = []
        with open(mentions_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                m = json.loads(line)
                m_rows.append((
                    m.get("hn_comment_id") or m.get("id"),
                    m.get("vid"),
                    m.get("author", ""),
                    m.get("month") or m.get("ym", ""),
                    m.get("story_title") or m.get("story", ""),
                    m.get("stance", ""),
                    m.get("why", ""),
                    m.get("quote", ""),
                    m.get("text", "")
                ))
        cur.executemany("INSERT INTO mentions VALUES (?,?,?,?,?,?,?,?,?);", m_rows)
        print(f"Inserted {len(m_rows)} mentions.")

    # 5. Load related
    related_file = os.path.join(data_dir, "related.jsonl")
    if os.path.exists(related_file):
        print(f"Loading related from {related_file}...")
        rel_rows = []
        with open(related_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                r = json.loads(line)
                vid = r.get("vid")
                for item in r.get("related", []):
                    rel_vid = item.get("vid")
                    shared = item.get("shared_recommenders", 1)
                    rel_rows.append((vid, rel_vid, shared))
        cur.executemany("INSERT OR IGNORE INTO related VALUES (?,?,?);", rel_rows)
        print(f"Inserted {len(rel_rows)} related edges.")

    conn.commit()
    conn.close()
    print("Database build complete!")

if __name__ == "__main__":
    d = sys.argv[1] if len(sys.argv) > 1 else "data"
    build_database(d)
