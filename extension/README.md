# Rexan Browser Extension (1-Click Video Curator)

This extension lets you curate and add YouTube videos directly to your self-hosted **Rexan** instance with a single click while browsing YouTube.

---

## Installation (Chrome, Brave, Edge, Opera)

1. Open your browser and navigate to `chrome://extensions` (or `edge://extensions` / `brave://extensions`).
2. Turn on **Developer mode** (toggle in top right).
3. Click the **Load unpacked** button (in the top left).
4. Select this directory:
   ```
   /Users/jainamshah/Downloads/Learning French/rexan.org/extension
   ```
5. Pin the **Rexan** icon to your toolbar.

---

## Usage

1. **When watching any video on YouTube:**
   - Click the **Rexan** icon on your browser toolbar.
   - The extension detects the active video, auto-fills its title, channel, and thumbnail.
   - Tags are pre-assigned and editable (click `×` to remove, type in the box and press `Enter` to add new tags).
   - Choose a playlist to add it into (optional).
   - Click **Add to Rexan (1-Click)**.
   - Done! Rexan will fetch the community comments (from Hacker News discussions, or top 5 YouTube comments if not discussed on HN) and save it directly into your database and search index.

2. **From Any Tab:**
   - Click the extension icon.
   - Paste any YouTube URL and click **Fetch**.

3. **Custom Server Host:**
   - By default, the extension connects to `http://localhost:8000`.
   - Click **Settings** in the extension popup to change the URL if your Rexan instance is running on another port or domain.
