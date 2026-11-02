# Rexan data

The data behind [Rexan](https://rexan.org): the YouTube videos that the hacker and engineering
community keeps telling each other to watch. Use it to build your own UI, recommender, newsletter,
analysis, or anything else. Cloned from HackerTube with full attribution under ODC-By 1.0.

- 6,454 videos, recommended (or at least discussed) on HN between 2007 and 2026
- 39,834 HN comments linking them, each labeled by what the commenter was doing
- 150 topic categories in 16 areas, and the graph of videos that share HN recommenders

## For AI agents: start here

You were probably handed this folder and asked to build something with it (a site, a recommender, a
newsletter, a CLI, an analysis). Everything you need is in these files. No network access or API key
is required.

**File map and joins**

| file | one row is | key | joins to |
|---|---|---|---|
| `videos.jsonl` | a video (6,454 rows, best-scored first) | `vid` (11-char YouTube id) | the hub |
| `mentions.jsonl` | an HN comment linking a video (39,834 rows) | `hn_comment_id` + `vid` | `vid` → `videos.vid` |
| `related.jsonl` | a video's co-recommended videos (3,778 rows) | `vid` | `vid`, `related[].vid` → `videos.vid` |
| `taxonomy.json` | the topic tree (16 areas, 150 categories) | category `id` | `videos.categories[].id` |
| `embeddings.npy` | a video's 384-d vector | row index | row `i` ↔ `embedding_ids.json[i]` → `videos.vid` |

**Loading:** all `.jsonl` files are UTF-8, one JSON object per line. They fit in memory (the largest,
`mentions.jsonl`, is ~35 MB). For example, `pandas.read_json(path, lines=True)` or a line-by-line
`json.loads`.

**Things to know before you build**

- `videos.score` is the ranking signal: the number of distinct months HN recommended the video, with
  strong recommendations counting extra. Sort by it for "best of"; sample from it for variety.
- Only `stance` ∈ {`rec`, `strong_rec`} are recommendations. `reference`, `joke` and `critical`
  mentions also exist. About 25% of videos were only cited and never recommended
  (`hn.recommenders == 0`), so decide whether to show those.
- At most 20 mentions per video are included, so `hn.mentions` is capped at 20.
- `mentions.text` is cut at 1,500 characters. Links in it appear as `[VIDEO]` (this video) and `[LINK]`.
- `shelf_life == "news"` marks videos that only matter around one event; most UIs should hide them by
  default.
- Stances, summaries and categories were written by an LLM: good, but expect a few percent of noise.
- Some talks were uploaded twice under different `vid`s with near-identical titles. Dedupe by
  normalized title if that matters.
- Video thumbnails need no API: `https://i.ytimg.com/vi/<vid>/hqdefault.jpg` (the uploader's custom
  thumbnail) or `.../hq2.jpg` (an automatic frame from the middle of the video, which Rexan
  shows instead). Embed a player with `https://www.youtube-nocookie.com/embed/<vid>`.
- For semantic search, embed the query with the same model: see `embeddings.npy` below.

**Example records** (one of each, long text trimmed)

`videos.jsonl`:
```json
{
 "vid": "fNk_zzaMoSs",
 "url": "https://www.youtube.com/watch?v=fNk_zzaMoSs",
 "title": "Vectors | Chapter 1, Essence of linear algebra",
 "channel": "3Blue1Brown",
 "summary": "The first chapter of 3Blue1Brown's Essence of Linear Algebra series, introducing vectors with animated geometric visuals. It begins a series that builds intuition for linear algebra from the basics.",
 "why_hn": "HN's go-to recommendation for learning linear algebra intuition, repeatedly credited with making concepts click and complementing textbooks.",
 "content_type": "course",
 "level": "intro",
 "shelf_life": "evergreen",
 "primary_topic": "linear algebra",
 "tags": [
  "vectors",
  "linear algebra",
  "visual intuition",
  "3blue1brown",
  "machine learning math"
 ],
 "categories": [
  {
   "id": "pure-mathematics",
   "name": "Pure mathematics",
   "area": "math-theory",
   "area_name": "Mathematics & Theoretical CS"
  },
  {
   "id": "recreational-math",
   "name": "Recreational & visual math",
   "area": "math-theory",
   "area_name": "Mathematics & Theoretical CS"
  }
 ],
 "quote": {
  "text": "the most welcoming and informative introduction to the topic I've ever seen",
  "hn_comment_id": 18679785,
  "year": "2018"
 },
 "hn": {
  "mentions": 20,
  "recommenders": 17,
  "rec_months": 18,
  "strong_recs": 14,
  "stances": {
   "rec": 5,
   "strong_rec": 14,
   "reference": 1
  },
  "first_year": 2018,
  "last_year": 2026
 },
 "score": 25.0
}
```

`mentions.jsonl`:
```json
{
 "hn_comment_id": 18679785,
 "hn_url": "https://news.ycombinator.com/item?id=18679785",
 "vid": "fNk_zzaMoSs",
 "author": "nicebill8",
 "month": "2018-12",
 "story_title": "Introduction to Applied Linear Algebra: Vectors, Matrices, and Least Squares",
 "stance": "strong_rec",
 "why": "Most welcoming and informative intro to linear algebra",
 "quote": "the most welcoming and informative introduction to the topic I've ever seen",
 "text": "The 3B1B series on Linear Algebra is by far the most welcoming and informative introduction to the topic I've ever seen: [VIDEO]"
}
```

## License and attribution

Released under the [Open Data Commons Attribution License (ODC-By) v1.0](https://opendatacommons.org/licenses/by/1-0/).
Dataset derived from HackerTube (https://hackertube.org) and the
[open-index/hacker-news](https://huggingface.co/datasets/open-index/hacker-news) archive. Comments remain
the work of their authors. Video titles and channel names belong to their creators. Not affiliated with
YouTube, Google, Hacker News or Y Combinator.
