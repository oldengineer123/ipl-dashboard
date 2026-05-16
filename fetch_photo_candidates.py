#!/usr/bin/env python3
"""
IPL Dashboard — Multi-source photo candidate fetcher

For each player, collects up to 8 candidate photos from 4 sources:
  1. Wikipedia article lead image   (text search → infobox photo; best for famous players)
  2. Wikimedia Commons category     (Category:{name} → files)
  3. Wikimedia Commons file search  (file namespace text search)
  4. Wikidata P18 + Wikipedia page  (via Cricinfo ID → Q-entity)

Then generates photo_picker.html — open it in your browser, click the best
photo for each player, and download player_headshots.json when done.

Run:
    python3 fetch_photo_candidates.py
    open photo_picker.html
"""

import json, re, sys, time, urllib.request, urllib.parse
from pathlib import Path

SCRIPT_DIR   = Path(__file__).parent
ASSETS_DIR   = SCRIPT_DIR / "assets"

COMMONS_API  = "https://commons.wikimedia.org/w/api.php"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
WIKI_API     = "https://en.wikipedia.org/w/api.php"
HEADERS      = {"User-Agent": "IPLDashboard/1.0 (personal cricket stats project)"}
THUMB        = 250
SLEEP        = 0.6   # increased to avoid Wikipedia rate limiting

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp"}
# Reject files whose names suggest they are not photos of a person
REJECT_WORDS = {"logo","flag","stadium","ground","trophy","pitch","map",
                "signature","autograph","mascot","crowd","emblem","icon",
                "college","university","school","institute","club","association",
                "svg","crest","coat","arms","seal"}


def api(base, params):
    params["format"] = "json"
    url = base + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=12) as r:
        return json.loads(r.read())


def is_ok_image(title):
    """Accept any image file that isn't obviously a non-person graphic."""
    t = title.lower()
    ext = t.rsplit(".", 1)[-1] if "." in t else ""
    if ext not in IMAGE_EXTS:
        return False
    words = set(re.split(r"[\W_]+", t))
    return not words & REJECT_WORDS


# ── Wikipedia via REST summary API (CDN-backed, no rate limits) ──────────────

WIKI_REST = "https://en.wikipedia.org/api/rest_v1/page/summary"


def wiki_summary_photo(title: str) -> str | None:
    """Fetch the lead photo from a Wikipedia article using the REST summary API.
    Served from CDN — much more tolerant than the MediaWiki search API."""
    try:
        url = f"{WIKI_REST}/{urllib.parse.quote(title, safe='')}"
        req = urllib.request.Request(url, headers=HEADERS)
        d   = json.loads(urllib.request.urlopen(req, timeout=10).read())
        return d.get("thumbnail", {}).get("source") or d.get("originalimage", {}).get("source")
    except Exception:
        return None


def wikipedia_direct_photo(full_name):
    """Try article title variants directly via REST summary API."""
    candidates = [full_name]
    parts = full_name.split()
    if len(parts) >= 2:
        initials = "".join(p[0] for p in parts[:-1]) + " " + parts[-1]
        candidates.append(initials)
    for title in candidates:
        url = wiki_summary_photo(title)
        if url:
            return url
        time.sleep(SLEEP)
    return None


# ── Wikipedia search fallback (MediaWiki API) ─────────────────────────────────

def name_matches_title(full_name: str, article_title: str) -> bool:
    name_words = set(full_name.lower().split())
    title_words = set(article_title.lower().split())
    stopwords = {"the", "of", "and", "a", "in", "at", "for", "cricket", "cricketer"}
    name_words -= stopwords
    return bool(name_words & title_words)


def wikipedia_article_photos(full_name):
    """Search Wikipedia then fetch the summary for each matching hit."""
    urls = []
    for query in [f"{full_name} cricketer", f"{full_name} cricket"]:
        try:
            sr = api(WIKI_API, {
                "action": "query", "list": "search",
                "srsearch": query, "srlimit": 5, "srprop": "title",
            })
            hits = sr.get("query", {}).get("search", [])
            for hit in hits:
                title = hit.get("title", "")
                if not name_matches_title(full_name, title):
                    continue
                url = wiki_summary_photo(title)
                if url and url not in urls:
                    urls.append(url)
                time.sleep(SLEEP)
            if urls:
                break
        except Exception:
            pass
        time.sleep(SLEEP)
    return urls[:3]


# ── Source 2: Wikimedia Commons category ─────────────────────────────────────

def commons_category_photos(full_name):
    """Fetch files from Category:{full_name} on Wikimedia Commons."""
    urls = []
    try:
        d = api(COMMONS_API, {
            "action": "query",
            "generator": "categorymembers",
            "gcmtitle": f"Category:{full_name}",
            "gcmtype": "file",
            "gcmlimit": 8,
            "prop": "imageinfo",
            "iiprop": "url|mime",
            "iiurlwidth": THUMB,
        })
        for pg in d.get("query", {}).get("pages", {}).values():
            title = pg.get("title", "")
            ii    = pg.get("imageinfo", [{}])[0]
            mime  = ii.get("mime", "")
            thumb = ii.get("thumburl") or ii.get("url", "")
            if mime.startswith("image/") and is_ok_image(title) and thumb and thumb not in urls:
                urls.append(thumb)
    except Exception:
        pass
    time.sleep(SLEEP)
    return urls[:3]


# ── Source 3: Wikimedia Commons file search ───────────────────────────────────

def commons_file_search(full_name):
    """Search Commons file namespace by player name."""
    urls = []
    for query in [f"{full_name} cricketer", f"{full_name} cricket", full_name]:
        if len(urls) >= 3:
            break
        try:
            d = api(COMMONS_API, {
                "action": "query", "generator": "search",
                "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 8,
                "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": THUMB,
            })
            for pg in d.get("query", {}).get("pages", {}).values():
                title = pg.get("title", "")
                ii    = pg.get("imageinfo", [{}])[0]
                mime  = ii.get("mime", "")
                thumb = ii.get("thumburl") or ii.get("url", "")
                if mime.startswith("image/") and is_ok_image(title) and thumb and thumb not in urls:
                    urls.append(thumb)
                if len(urls) >= 4:
                    break
        except Exception:
            pass
        time.sleep(SLEEP)
    return urls


# ── Source 4: ESPNCricinfo player page ───────────────────────────────────────

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

def slugify(name):
    name = name.lower().strip()
    name = re.sub(r"[^\w\s-]", "", name)
    return re.sub(r"[\s_]+", "-", name)

def cricinfo_photo(full_name, cricinfo_id):
    """Scrape ESPNCricinfo player page og:image."""
    url = f"https://www.espncricinfo.com/player/{slugify(full_name)}-{cricinfo_id}"
    try:
        req  = urllib.request.Request(url, headers=BROWSER_HEADERS)
        html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", errors="ignore")
        for pat in [
            r'property="og:image"\s+content="([^"]+)"',
            r'content="([^"]+)"\s+property="og:image"',
        ]:
            m = re.search(pat, html)
            if m:
                img = m.group(1)
                if not any(x in img.lower() for x in ["placeholder", "generic", "default",
                                                        "espncricinfo-logo", "icon"]):
                    return img
    except Exception:
        pass
    return None


# ── Source 5: Cricbuzz player search ─────────────────────────────────────────

def cricbuzz_photo(full_name):
    """Search Cricbuzz player suggest API and scrape the first matching profile."""
    try:
        encoded = urllib.parse.quote(full_name)
        url = f"https://www.cricbuzz.com/api/mvc/seriesSquadsSearch?term={encoded}"
        req = urllib.request.Request(url, headers=BROWSER_HEADERS)
        data = json.loads(urllib.request.urlopen(req, timeout=10).read())

        # Response is a list of {id, label, value, imgUrl, ...}
        for item in data:
            label = item.get("label", "") or item.get("value", "")
            if name_matches_title(full_name, label):
                player_id = item.get("playerId") or item.get("id")
                img_url   = item.get("imgUrl") or item.get("image")
                if img_url:
                    # Make absolute if needed
                    if img_url.startswith("//"):
                        img_url = "https:" + img_url
                    elif img_url.startswith("/"):
                        img_url = "https://www.cricbuzz.com" + img_url
                    return img_url

                # Fall back: scrape player profile page
                if player_id:
                    slug = slugify(full_name)
                    purl = f"https://www.cricbuzz.com/profiles/{player_id}/{slug}"
                    req2 = urllib.request.Request(purl, headers=BROWSER_HEADERS)
                    html = urllib.request.urlopen(req2, timeout=12).read().decode("utf-8", errors="ignore")
                    m = re.search(r'property="og:image"\s+content="([^"]+)"', html)
                    if not m:
                        m = re.search(r'content="([^"]+)"\s+property="og:image"', html)
                    if m:
                        return m.group(1)
    except Exception:
        pass
    return None


def wikidata_photos(cricinfo_id):
    """Q-entity → Wikipedia page photo + Wikidata P18 photo."""
    photos = []
    try:
        # Step 1: Cricinfo ID → Q-ID
        d = api(WIKIDATA_API, {
            "action": "query", "list": "search",
            "srsearch": f"haswbstatement:P2697={cricinfo_id}",
            "srlimit": 1, "srprop": "",
        })
        hits = d.get("query", {}).get("search", [])
        if not hits:
            return photos
        qid = hits[0]["title"]
        time.sleep(SLEEP)

        # Step 2: Q-ID → sitelinks + P18
        d = api(WIKIDATA_API, {
            "action": "wbgetentities", "ids": qid,
            "props": "sitelinks|claims", "sitefilter": "enwiki",
        })
        entity = d.get("entities", {}).get(qid, {})
        time.sleep(SLEEP)

        # 2a: Wikipedia page thumbnail
        wiki_title = entity.get("sitelinks", {}).get("enwiki", {}).get("title")
        if wiki_title:
            d2 = api(WIKI_API, {
                "action": "query", "titles": wiki_title,
                "prop": "pageimages", "pithumbsize": THUMB,
            })
            for pg in d2.get("query", {}).get("pages", {}).values():
                url = pg.get("thumbnail", {}).get("source")
                if url:
                    photos.append(url)
            time.sleep(SLEEP)

        # 2b: Wikidata P18 → Commons thumbnail
        p18 = entity.get("claims", {}).get("P18", [])
        if p18:
            fname = p18[0].get("mainsnak", {}).get("datavalue", {}).get("value", "")
            if fname:
                d3 = api(COMMONS_API, {
                    "action": "query", "titles": f"File:{fname.replace(' ', '_')}",
                    "prop": "imageinfo", "iiprop": "url", "iiurlwidth": THUMB,
                })
                for pg in d3.get("query", {}).get("pages", {}).values():
                    ii = pg.get("imageinfo", [{}])[0]
                    url = ii.get("thumburl") or ii.get("url", "")
                    if url:
                        photos.append(url)
                time.sleep(SLEEP)
    except Exception:
        pass
    return photos


def main():
    ids_path = ASSETS_DIR / "player_cricinfo_ids.json"
    if not ids_path.exists():
        print("ERROR: assets/player_cricinfo_ids.json not found.")
        return
    cricinfo_map = json.loads(ids_path.read_text())
    fullnames_map = {}
    fp = ASSETS_DIR / "player_fullnames.json"
    if fp.exists():
        fullnames_map = json.loads(fp.read_text())

    all_abbrev = sorted(cricinfo_map.keys())

    # --limit N  → first N players alphabetically
    limit = None
    if "--limit" in sys.argv:
        try: limit = int(sys.argv[sys.argv.index("--limit") + 1])
        except (IndexError, ValueError): pass
    if limit:
        all_abbrev = all_abbrev[:limit]
        print(f"[TEST MODE] First {limit} players only.\n")

    # --players "AB de Villiers,AC Gilchrist"  → specific players by abbreviated name
    if "--players" in sys.argv:
        try:
            names = sys.argv[sys.argv.index("--players") + 1].split(",")
            all_abbrev = [n.strip() for n in names if n.strip() in cricinfo_map]
            print(f"[TEST MODE] Testing: {all_abbrev}\n")
        except (IndexError, ValueError): pass

    # --debug  → print what each source returns
    DEBUG = "--debug" in sys.argv

    total      = len(all_abbrev)
    cands_path = ASSETS_DIR / "player_photo_candidates.json"

    # Load existing candidates (url sets per player, keyed by abbrev name)
    candidates = {}
    if cands_path.exists():
        candidates = json.loads(cands_path.read_text())

    # ── Source-first ordering ────────────────────────────────────────────────
    # Run ALL players through source 1, then ALL through source 2, etc.
    # By the time we revisit an API for source 2, 800+ sleep cycles have passed
    # → no rate limiting, maximum candidates per player.

    SOURCES = [
        ("Wiki-direct",  lambda fn, cid: [wikipedia_direct_photo(fn)],          False),
        ("Wiki-search",  lambda fn, cid: wikipedia_article_photos(fn),           False),
        ("Commons-cat",  lambda fn, cid: commons_category_photos(fn),            False),
        ("Commons-file", lambda fn, cid: commons_file_search(fn),                False),
        ("Wikidata",     lambda fn, cid: wikidata_photos(cid) if cid else [],    True),
    ]

    for src_label, src_fn, needs_cricinfo in SOURCES:
        already = sum(1 for v in candidates.values() if src_label in v.get("sources_done", []))
        print(f"\n── {src_label}  ({already}/{total} already done) ───────────────────────")

        for i, abbrev in enumerate(all_abbrev, 1):
            entry       = candidates.setdefault(abbrev, {"full_name": "", "candidates": [], "sources_done": []})
            full_name   = fullnames_map.get(abbrev, abbrev)
            cricinfo_id = cricinfo_map.get(abbrev)
            entry["full_name"] = full_name

            if src_label in entry.get("sources_done", []):
                continue  # already ran this source for this player

            try:
                new_urls = src_fn(full_name, cricinfo_id) or []
                new_urls = [u for u in new_urls if u]
            except Exception as e:
                new_urls = []
                if DEBUG: print(f"  [{i:>3}] {full_name}: ERROR {e}")

            # Merge into candidates, deduplicate
            existing = set(entry["candidates"])
            added = [u for u in new_urls if u not in existing]
            entry["candidates"] = (entry["candidates"] + added)[:12]
            entry.setdefault("sources_done", []).append(src_label)

            if DEBUG or added:
                print(f"  [{i:>3}/{total}]  {full_name}  +{len(added)} from {src_label}"
                      f"  (total {len(entry['candidates'])})")

            cands_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2))
            time.sleep(SLEEP)

    print(f"\n── Done fetching. Summary ──────────────────────────────")
    with_photos = sum(1 for v in candidates.values() if v.get("candidates"))
    print(f"  Players with ≥1 photo: {with_photos}/{total}")

    print(f"\nGenerating photo_picker.html …")
    generate_picker(candidates)
    print(f"Done. Open photo_picker.html in your browser to review.\n")


def generate_picker(candidates):
    # Sort: players with candidates first, then no-photo ones
    players = sorted(
        candidates.items(),
        key=lambda x: (len(x[1].get("candidates", [])) == 0, x[1].get("full_name", x[0]))
    )
    data_json = json.dumps(
        [{"abbrev": a, "full_name": v["full_name"], "candidates": v.get("candidates", [])}
         for a, v in players],
        ensure_ascii=False
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>IPL Player Photo Picker</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f0f2f5; color: #1a1a1a; }}

  /* ── header ── */
  #header {{ position: sticky; top: 0; z-index: 100;
             background: #1a1a2e; color: #fff;
             display: flex; align-items: center; gap: 16px;
             padding: 12px 24px; box-shadow: 0 2px 8px rgba(0,0,0,.4); }}
  #header h1 {{ font-size: 1.1rem; font-weight: 700; flex: 1; }}
  #progress {{ font-size: .85rem; opacity: .8; white-space: nowrap; }}
  #filter {{ padding: 6px 12px; border-radius: 6px; border: none;
             background: #2a2a4e; color: #fff; font-size: .85rem; cursor: pointer; }}
  #filter:hover {{ background: #3a3a6e; }}
  #save-btn {{ padding: 8px 18px; border-radius: 8px; border: none;
               background: #22c55e; color: #fff; font-weight: 700;
               font-size: .9rem; cursor: pointer; transition: background .2s; }}
  #save-btn:hover {{ background: #16a34a; }}

  /* ── search ── */
  #search-wrap {{ background: #fff; padding: 10px 24px; border-bottom: 1px solid #e5e7eb; }}
  #search {{ width: 100%; max-width: 400px; padding: 8px 14px;
             border: 1px solid #d1d5db; border-radius: 8px; font-size: .95rem; }}

  /* ── player grid ── */
  #grid {{ padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }}

  .player-card {{ background: #fff; border-radius: 12px;
                  box-shadow: 0 1px 4px rgba(0,0,0,.1); overflow: hidden; }}
  .player-card.done {{ border-left: 4px solid #22c55e; }}
  .player-card.skipped {{ border-left: 4px solid #94a3b8; }}

  .player-header {{ display: flex; align-items: center; gap: 12px;
                    padding: 12px 16px; background: #f8fafc;
                    border-bottom: 1px solid #e5e7eb; }}
  .player-name {{ font-weight: 700; font-size: 1rem; flex: 1; }}
  .player-status {{ font-size: .78rem; padding: 3px 10px; border-radius: 20px;
                    font-weight: 600; }}
  .status-pending  {{ background: #fef3c7; color: #92400e; }}
  .status-selected {{ background: #dcfce7; color: #166534; }}
  .status-skipped  {{ background: #f1f5f9; color: #64748b; }}

  .photos {{ display: flex; flex-wrap: wrap; gap: 10px; padding: 14px 16px; }}

  .photo-wrap {{ position: relative; cursor: pointer; border-radius: 8px; overflow: hidden;
                 border: 3px solid transparent; transition: border-color .15s, transform .15s; }}
  .photo-wrap:hover {{ border-color: #60a5fa; transform: scale(1.03); }}
  .photo-wrap.selected {{ border-color: #22c55e !important; }}

  .photo-wrap img {{ width: 120px; height: 120px; object-fit: cover; display: block; }}
  .photo-wrap.broken {{ display: none; }}

  .no-photos {{ color: #94a3b8; font-size: .85rem; padding: 8px 0; }}

  .card-actions {{ display: flex; gap: 8px; padding: 10px 16px 14px; }}
  .btn {{ padding: 6px 14px; border-radius: 6px; border: none; font-size: .82rem;
          font-weight: 600; cursor: pointer; transition: background .15s; }}
  .btn-skip {{ background: #f1f5f9; color: #475569; }}
  .btn-skip:hover {{ background: #e2e8f0; }}
  .btn-clear {{ background: #fee2e2; color: #991b1b; }}
  .btn-clear:hover {{ background: #fecaca; }}
</style>
</head>
<body>

<div id="header">
  <h1>📷 IPL Player Photo Picker</h1>
  <span id="progress">Loading…</span>
  <button id="filter" onclick="toggleFilter()">Show: All</button>
  <button id="save-btn" onclick="saveJSON()">⬇ Download player_headshots.json</button>
</div>

<div id="search-wrap">
  <input id="search" type="search" placeholder="Search player name…"
         oninput="renderGrid()" autocomplete="off">
</div>

<div id="grid"></div>

<script>
const PLAYERS = {data_json};

// selections: abbrev → url  (url === null means explicitly skipped)
const SEL = {{}};
let showFilter = 'all';  // 'all' | 'pending' | 'done'

function toggleFilter() {{
  const order = ['all','pending','done'];
  showFilter = order[(order.indexOf(showFilter) + 1) % order.length];
  document.getElementById('filter').textContent =
    showFilter === 'all' ? 'Show: All' :
    showFilter === 'pending' ? 'Show: Pending' : 'Show: Done';
  renderGrid();
}}

function updateProgress() {{
  const selected = Object.keys(SEL).filter(k => SEL[k] !== null).length;
  const skipped  = Object.keys(SEL).filter(k => SEL[k] === null).length;
  const total    = PLAYERS.length;
  document.getElementById('progress').textContent =
    `${{selected}} selected · ${{skipped}} skipped · ${{total - selected - skipped}} pending`;
}}

function renderGrid() {{
  const q = document.getElementById('search').value.toLowerCase();
  const grid = document.getElementById('grid');
  grid.innerHTML = '';

  const visible = PLAYERS.filter(p => {{
    if (q && !p.full_name.toLowerCase().includes(q)) return false;
    if (showFilter === 'pending' && (p.abbrev in SEL)) return false;
    if (showFilter === 'done'    && !(p.abbrev in SEL)) return false;
    return true;
  }});

  visible.forEach(p => {{
    const card = document.createElement('div');
    const sel  = SEL[p.abbrev];
    card.className = 'player-card' + (sel !== undefined ? (sel ? ' done' : ' skipped') : '');
    card.id = 'card-' + p.abbrev.replace(/\\s+/g, '_');

    const statusText = sel === undefined ? 'Pending' : sel ? 'Selected' : 'Skipped';
    const statusCls  = sel === undefined ? 'status-pending' : sel ? 'status-selected' : 'status-skipped';

    card.innerHTML = `
      <div class="player-header">
        <span class="player-name">${{p.full_name}}</span>
        <span class="player-status ${{statusCls}}" id="status-${{p.abbrev.replace(/\\s+/g,'_')}}">${{statusText}}</span>
      </div>
      <div class="photos" id="photos-${{p.abbrev.replace(/\\s+/g,'_')}}">
        ${{p.candidates.length === 0
          ? '<span class="no-photos">No photos found from any source.</span>'
          : p.candidates.map((url, idx) => `
              <div class="photo-wrap${{sel === url ? ' selected' : ''}}"
                   id="pw-${{p.abbrev.replace(/\\s+/g,'_')}}-${{idx}}"
                   onclick="selectPhoto('${{p.abbrev}}', '${{url.replace(/'/g,"\\\\'")}}', ${{idx}})">
                <img src="${{url}}" alt="${{p.full_name}}"
                     onerror="this.parentElement.classList.add('broken')">
              </div>`).join('')
        }}
      </div>
      <div class="card-actions">
        <button class="btn btn-skip"  onclick="skipPlayer('${{p.abbrev}}')">No good photo</button>
        ${{sel !== undefined ? `<button class="btn btn-clear" onclick="clearPlayer('${{p.abbrev}}')">Clear</button>` : ''}}
      </div>
    `;
    grid.appendChild(card);
  }});
  updateProgress();
}}

function selectPhoto(abbrev, url, idx) {{
  SEL[abbrev] = url;
  // Update all thumbs for this player
  const key = abbrev.replace(/\\s+/g, '_');
  document.querySelectorAll(`[id^="pw-${{key}}-"]`).forEach(el => el.classList.remove('selected'));
  document.getElementById(`pw-${{key}}-${{idx}}`).classList.add('selected');
  // Update card and status
  const card = document.getElementById(`card-${{key}}`);
  if (card) {{ card.className = 'player-card done'; }}
  const status = document.getElementById(`status-${{key}}`);
  if (status) {{ status.textContent = 'Selected'; status.className = 'player-status status-selected'; }}
  updateProgress();
}}

function skipPlayer(abbrev) {{
  SEL[abbrev] = null;
  const key = abbrev.replace(/\\s+/g, '_');
  document.querySelectorAll(`[id^="pw-${{key}}-"]`).forEach(el => el.classList.remove('selected'));
  const card = document.getElementById(`card-${{key}}`);
  if (card) {{ card.className = 'player-card skipped'; }}
  const status = document.getElementById(`status-${{key}}`);
  if (status) {{ status.textContent = 'Skipped'; status.className = 'player-status status-skipped'; }}
  updateProgress();
}}

function clearPlayer(abbrev) {{
  delete SEL[abbrev];
  renderGrid();
}}

function saveJSON() {{
  // Output only players where a photo was actually selected (not skipped)
  const out = {{}};
  for (const [abbrev, url] of Object.entries(SEL)) {{
    if (url) out[abbrev] = url;
  }}
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'player_headshots.json';
  a.click();
}}

renderGrid();
</script>
</body>
</html>"""

    out = SCRIPT_DIR / "photo_picker.html"
    out.write_text(html, encoding="utf-8")
    print(f"  Saved → {out}")


if __name__ == "__main__":
    main()
