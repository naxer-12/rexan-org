let defaultServer = "http://localhost:8000";
let serverUrl = defaultServer;
let currentMeta = null;
let currentTags = [];
let addedRedirectUrl = "";

const statusDot = document.getElementById("status-indicator");
const loader = document.getElementById("loader");
const notConnected = document.getElementById("not-connected");
const urlBox = document.getElementById("url-box");
const manualUrlInput = document.getElementById("manual-url");
const manualFetchBtn = document.getElementById("manual-fetch-btn");
const videoCard = document.getElementById("video-card");
const successCard = document.getElementById("success-card");
const vThumb = document.getElementById("v-thumb");
const vTitle = document.getElementById("v-title");
const vChannel = document.getElementById("v-channel");
const vBadge = document.getElementById("v-badge");
const vPlaylist = document.getElementById("v-playlist");
const vTags = document.getElementById("v-tags");
const newTagInput = document.getElementById("new-tag-input");
const addBtn = document.getElementById("add-btn");
const openVideoBtn = document.getElementById("open-video-btn");
const addAnotherBtn = document.getElementById("add-another-btn");
const toggleSettings = document.getElementById("toggle-settings");
const settingsPanel = document.getElementById("settings-panel");
const serverUrlInput = document.getElementById("server-url");
const saveSettingsBtn = document.getElementById("save-settings-btn");
const serverLabel = document.getElementById("server-label");

// Load stored server URL
chrome.storage?.local?.get(["rexan_server"], (res) => {
  if (res && res.rexan_server) {
    serverUrl = res.rexan_server;
  }
  serverUrlInput.value = serverUrl;
  serverLabel.textContent = `Server: ${serverUrl.replace(/^https?:\/\//, "")}`;
  init();
});

// Fallback if not running in extension context
if (!chrome.storage?.local) {
  init();
}

async function init() {
  loader.style.display = "block";
  notConnected.style.display = "none";
  videoCard.style.display = "none";
  urlBox.style.display = "none";
  successCard.style.display = "none";

  const online = await checkServer();
  if (!online) {
    loader.style.display = "none";
    notConnected.style.display = "block";
    statusDot.className = "status-dot offline";
    return;
  }

  statusDot.className = "status-dot online";
  await loadPlaylists();

  // Inspect current tab
  if (chrome.tabs?.query) {
    chrome.tabs.query({ active: true, currentWindow: true }, async (tabs) => {
      const activeTab = tabs[0];
      const url = activeTab?.url || "";
      if (isYouTubeUrl(url)) {
        await fetchVideo(url);
      } else {
        loader.style.display = "none";
        urlBox.style.display = "block";
      }
    });
  } else {
    loader.style.display = "none";
    urlBox.style.display = "block";
  }
}

function isYouTubeUrl(url) {
  return /youtube\.com\/watch|youtu\.be\/|youtube\.com\/shorts\//i.test(url);
}

async function checkServer() {
  try {
    const res = await fetch(`${serverUrl}/api/config`, { signal: AbortSignal.timeout(3000) });
    return res.ok;
  } catch (e) {
    return false;
  }
}

async function loadPlaylists() {
  try {
    const res = await fetch(`${serverUrl}/api/playlists`);
    const pls = await res.json();
    vPlaylist.innerHTML = '<option value="">-- None (Video Catalog only) --</option>';
    pls.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p.slug;
      opt.textContent = `${p.title} (${p.count} videos)`;
      vPlaylist.appendChild(opt);
    });
  } catch (e) {}
}

async function fetchVideo(url) {
  loader.style.display = "block";
  urlBox.style.display = "none";
  videoCard.style.display = "none";

  try {
    const res = await fetch(`${serverUrl}/api/video/fetch-meta?url=${encodeURIComponent(url)}`);
    if (!res.ok) throw new Error("Video not found");
    const meta = await res.json();
    currentMeta = meta;
    currentTags = meta.tags ? [...meta.tags] : [];

    vThumb.src = meta.thumbnail;
    vTitle.textContent = meta.title;
    vChannel.textContent = `${meta.channel} · ${meta.views.toLocaleString()} views`;

    if (meta.exists) {
      vBadge.innerHTML = '<span class="badge" style="background:#065fd4; color:#fff;">Already in Rexan</span>';
    } else if (meta.comments_source === "hackernews") {
      vBadge.innerHTML = `<span class="badge hn">✓ ${meta.comments.length} HN mentions</span>`;
    } else {
      vBadge.innerHTML = '<span class="badge yt">ℹ Top YouTube comments</span>';
    }

    renderTags();
    loader.style.display = "none";
    videoCard.style.display = "block";
  } catch (err) {
    loader.style.display = "none";
    urlBox.style.display = "block";
    alert(`Could not fetch video: ${err.message}`);
  }
}

function renderTags() {
  const existing = vTags.querySelectorAll(".tag-chip");
  existing.forEach(e => e.remove());
  currentTags.forEach((tag, idx) => {
    const chip = document.createElement("span");
    chip.className = "tag-chip";
    chip.innerHTML = `${tag} <span class="tag-del" data-idx="${idx}">×</span>`;
    newTagInput.before(chip);
  });
}

vTags.onclick = (e) => {
  const del = e.target.closest(".tag-del");
  if (del) {
    const idx = parseInt(del.dataset.idx, 10);
    currentTags.splice(idx, 1);
    renderTags();
  }
};

newTagInput.onkeydown = (e) => {
  if (e.key === "Enter" || e.key === ",") {
    e.preventDefault();
    const val = newTagInput.value.trim().toLowerCase().replace(/^#/, "");
    if (val && !currentTags.includes(val)) {
      currentTags.push(val);
      renderTags();
    }
    newTagInput.value = "";
  }
};

manualFetchBtn.onclick = () => {
  const val = manualUrlInput.value.trim();
  if (val) fetchVideo(val);
};

manualUrlInput.onkeydown = (e) => {
  if (e.key === "Enter") {
    e.preventDefault();
    manualFetchBtn.click();
  }
};

addBtn.onclick = async () => {
  if (!currentMeta) return;
  addBtn.disabled = true;
  addBtn.textContent = "Adding to Rexan...";

  const payload = {
    url: currentMeta.vid,
    title: currentMeta.title,
    channel: currentMeta.channel,
    summary: currentMeta.summary,
    tags: currentTags,
    categories: currentMeta.categories || [],
    playlist_slug: vPlaylist.value || null
  };

  try {
    const res = await fetch(`${serverUrl}/api/video/add`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Error adding video");

    addedRedirectUrl = `${serverUrl}${data.redirect_url || `/watch/${currentMeta.vid}`}`;
    videoCard.style.display = "none";
    successCard.style.display = "block";
    document.getElementById("success-title").textContent = "Added to Rexan!";
    document.getElementById("success-sub").textContent = `"${currentMeta.title}" is now part of your collection.`;
  } catch (err) {
    alert(`Error: ${err.message}`);
    addBtn.disabled = false;
    addBtn.textContent = "Add to Rexan (1-Click)";
  }
};

openVideoBtn.onclick = () => {
  if (addedRedirectUrl) {
    if (chrome.tabs?.create) {
      chrome.tabs.create({ url: addedRedirectUrl });
    } else {
      window.open(addedRedirectUrl, "_blank");
    }
  }
};

addAnotherBtn.onclick = () => {
  currentMeta = null;
  currentTags = [];
  successCard.style.display = "none";
  urlBox.style.display = "block";
  manualUrlInput.value = "";
  manualUrlInput.focus();
};

document.getElementById("retry-conn-btn").onclick = () => init();

toggleSettings.onclick = (e) => {
  e.preventDefault();
  settingsPanel.style.display = settingsPanel.style.display === "none" ? "block" : "none";
};

saveSettingsBtn.onclick = () => {
  serverUrl = serverUrlInput.value.trim().replace(/\/+$/, "");
  if (chrome.storage?.local) {
    chrome.storage.local.set({ rexan_server: serverUrl });
  }
  serverLabel.textContent = `Server: ${serverUrl.replace(/^https?:\/\//, "")}`;
  settingsPanel.style.display = "none";
  init();
};
