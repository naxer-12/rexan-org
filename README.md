# Rexan (`rexan.org`)

**Rexan** is a fast, algorithm-free video discovery platform built exclusively from YouTube talks, lectures, explainers, and documentaries recommended by the tech and hacker community over nearly two decades (2007–2026).

Cloned from [HackerTube](https://hackertube.org) and rebranded to **rexan.org**, featuring a modern, dependency-free vanilla frontend and an asynchronous Python/FastAPI backend backed by SQLite FTS5 full-text search and NumPy semantic vector embeddings.

---

## Features

- **6,454 Hand-Curated Videos:** Filtered to videos recommended by multiple community members across multiple months.
- **39,834 Labeled Comments:** Full context for every recommendation—why people recommended it, pull quotes, stances, and links back to the original threads.
- **16 Topic Areas & 150 Categories:** From distributed systems and computability to biology, microeconomics, and retrocomputing.
- **27 Curated Playlists:** Themed paths including "The HN Canon", "Talks Every Programmer Should Watch", and "Computers From the Transistor Up".
- **Hybrid Search Engine:** Combines SQLite FTS5 BM25 text search, topic synonym expansion, and 384-dimensional vector similarity (`BAAI/bge-small-en-v1.5`).
- **Privacy-First:** No accounts, cookies, or server-side user tracking. Likes, Watch Later, and History stay entirely in `localStorage`.
- **YouTube Embed Player & Frames Bypass:** Option to view a true frame from the video instead of clickbait thumbnails.
- **Export & Open Data:** Complete dataset exportable as `rexan-data.zip` under ODC-By 1.0.

---

## Tech Stack

- **Backend:** Python 3.10+, [FastAPI](https://fastapi.tiangolo.com/), [Uvicorn](https://www.uvicorn.org/)
- **Database & Search:** SQLite 3 with FTS5 virtual tables, [NumPy](https://numpy.org/) for vector cosine similarity
- **Frontend:** Single-page application in pure HTML5, CSS3 (CSS variables, dark/light mode), and vanilla ES6+ (no build step, no npm overhead)

---

## Quickstart

### 1. Requirements

- Python 3.10 or later
- Dependencies listed in `requirements.txt`:
  ```bash
  pip install -r requirements.txt
  ```

### 2. Build or Rebuild the Database

The SQLite database (`data/rexan.db`) and FTS5 search index are generated directly from the JSON Lines data:

```bash
python build_db.py data
```

### 3. Run the Server

```bash
python server.py
```
Or with Uvicorn:
```bash
uvicorn server:app --host 0.0.0.0 --port 8000
```

Open your browser to [http://localhost:8000](http://localhost:8000).

---

## Docker Deployment

To build and run with Docker:

```bash
docker compose up --build
```

Or standalone:

```bash
docker build -t rexan .
docker run -p 8000:8000 rexan
```

---

## Running the Test Suite

Rexan includes an end-to-end integration and unit test suite verifying all 17 core features and API endpoints:

```bash
python -m unittest discover tests -v
```

---

## Browser Extension (1-Click Video Curator)

Rexan includes a Manifest V3 browser extension located in `rexan.org/extension`:
- **1-Click on YouTube:** While watching any video on YouTube, click the Rexan toolbar icon. It automatically fetches video metadata, checks for HN discussions, pre-fills playlists, assigns tags, and saves it with a single click.
- **Manual Input:** Also allows pasting any YouTube link directly into the popup.

### Installation
1. Go to `chrome://extensions` (or `edge://extensions` / `brave://extensions`).
2. Enable **Developer mode** in the top right.
3. Click **Load unpacked** and select `rexan.org/extension`.
4. Pin the **Rexan** extension to your toolbar.

---

## API Documentation

| Endpoint | Method | Description |
|---|---|---|
| `/api/config` | `GET` | Server configuration (e.g. frame source) |
| `/api/stats` | `GET` | Total videos, comments, recommenders, year span, areas, and categories |
| `/api/browse` | `GET` | List of 16 topic areas, their categories, and video counts |
| `/api/playlists` | `GET` | List of all 27 curated playlists with covers and counts |
| `/api/playlist?slug={slug}` | `GET` | Full playlist contents with introduction and video notes |
| `/api/video?vid={vid}` | `GET` | Single video details, stats, likes, dislikes, whys, categories, and community comments |
| `/api/video/dislikes?vid={vid}` | `GET` | Return YouTube Dislike API integration |
| `/api/video/fetch-meta?url={url}`| `GET` | Auto-extracts metadata, checks HN discussions (or YouTube comments), and pre-assigns tags |
| `/api/video/add` | `POST` | Adds or updates video in database, FTS5 index, comments, and chosen playlist |
| `/api/docs?vids={id1,id2}` | `GET` | Batch video metadata lookup preserving order |
| `/api/related?vid={vid}&n=20` | `GET` | Co-recommended videos graph lookup with semantic fallback |
| `/api/feed` | `GET` | Stratified recommendations feed (parameters: `seed`, `like`, `dislike`, `seen`, `offset`, `n`) |
| `/api/list` | `GET` | Filtered & sorted video catalog (parameters: `cat`, `area`, `date`, `type`, `dur`, `gems`, `evergreen`, `sort`, `offset`, `n`) |
| `/api/search?q={query}` | `GET` | Full-text and semantic search |
| `/api/export` | `GET` | Manifest of downloadable dataset files |
| `/download/{filename}` | `GET` | Direct download for `rexan-data.zip` or individual data files |

---

## License & Attribution

- Released under the [Open Data Commons Attribution License (ODC-By) v1.0](https://opendatacommons.org/licenses/by/1-0/).
- Cloned from [HackerTube](https://hackertube.org) created by Andrej Karpathy.
- Community comments and discussions are derived from the [open-index/hacker-news](https://huggingface.co/datasets/open-index/hacker-news) archive.
- Video titles, channels, and playback are provided via YouTube embeds under standard YouTube terms.
