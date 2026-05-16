#!/usr/bin/env python3
"""
IPL Dashboard — Team logo fetcher (multi-source, source-first ordering)

Fetches logo candidates for all 15 IPL franchises from multiple sources,
downloads them as base64 data URIs, then generates logo_picker.html for review.

Sources (run all teams through each source before moving to next):
  1. Wikimedia direct  — known SVG/PNG URLs from Wikimedia Commons
  2. Wikipedia article — infobox image via REST summary API
  3. Commons search    — file namespace search for "{team} logo cricket"
  4. IPL website       — iplt20.com team pages (og:image)
  5. Cricbuzz          — cricbuzz.com team pages (og:image)

Run:
    python3 fetch_team_logos.py
    open logo_picker.html
"""

import base64, json, re, sys, time, urllib.request, urllib.parse
from pathlib import Path

SCRIPT_DIR  = Path(__file__).parent
ASSETS_DIR  = SCRIPT_DIR / "assets"
ASSETS_DIR.mkdir(exist_ok=True)

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
WIKI_REST   = "https://en.wikipedia.org/api/rest_v1/page/summary"
HEADERS_API = {"User-Agent": "IPLDashboard/1.0 (personal cricket stats project)"}
HEADERS_WEB = {
    "User-Agent": ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"),
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
}
SLEEP       = 0.6
THUMB       = 300

# ── All 15 IPL franchises ────────────────────────────────────────────────────
TEAMS = {
    "Chennai Super Kings":         {"wiki": "Chennai Super Kings",         "ipl_slug": "chennai-super-kings",     "cb_slug": "chennai-super-kings-2"},
    "Mumbai Indians":              {"wiki": "Mumbai Indians",               "ipl_slug": "mumbai-indians",          "cb_slug": "mumbai-indians-6"},
    "Royal Challengers Bengaluru": {"wiki": "Royal Challengers Bangalore", "ipl_slug": "royal-challengers-bangalore","cb_slug": "royal-challengers-bangalore-4"},
    "Kolkata Knight Riders":       {"wiki": "Kolkata Knight Riders",       "ipl_slug": "kolkata-knight-riders",   "cb_slug": "kolkata-knight-riders-3"},
    "Sunrisers Hyderabad":         {"wiki": "Sunrisers Hyderabad",         "ipl_slug": "sunrisers-hyderabad",     "cb_slug": "sunrisers-hyderabad-12"},
    "Delhi Capitals":              {"wiki": "Delhi Capitals",              "ipl_slug": "delhi-capitals",          "cb_slug": "delhi-capitals-10"},
    "Punjab Kings":                {"wiki": "Punjab Kings (cricket)",      "ipl_slug": "punjab-kings",            "cb_slug": "punjab-kings-8"},
    "Rajasthan Royals":            {"wiki": "Rajasthan Royals",            "ipl_slug": "rajasthan-royals",        "cb_slug": "rajasthan-royals-7"},
    "Gujarat Titans":              {"wiki": "Gujarat Titans",              "ipl_slug": "gujarat-titans",          "cb_slug": "gujarat-titans-15"},
    "Lucknow Super Giants":        {"wiki": "Lucknow Super Giants",        "ipl_slug": "lucknow-super-giants",   "cb_slug": "lucknow-super-giants-16"},
    "Deccan Chargers":             {"wiki": "Deccan Chargers",             "ipl_slug": None,                      "cb_slug": "deccan-chargers-1"},
    "Rising Pune Supergiants":     {"wiki": "Rising Pune Supergiants",     "ipl_slug": None,                      "cb_slug": "rising-pune-supergiant-11"},
    "Gujarat Lions":               {"wiki": "Gujarat Lions",               "ipl_slug": None,                      "cb_slug": "gujarat-lions-13"},
    "Kochi Tuskers Kerala":        {"wiki": "Kochi Tuskers Kerala",        "ipl_slug": None,                      "cb_slug": "kochi-tuskers-kerala-9"},
    "Pune Warriors":               {"wiki": "Pune Warriors India",         "ipl_slug": None,                      "cb_slug": "pune-warriors-india-5"},
}

# Known Wikimedia direct URLs (from download_assets.py)
WIKIMEDIA_URLS = {
    "Chennai Super Kings":         "https://upload.wikimedia.org/wikipedia/en/2/2b/Chennai_Super_Kings_Logo.svg",
    "Mumbai Indians":              "https://upload.wikimedia.org/wikipedia/en/c/cd/Mumbai_Indians_Logo.svg",
    "Royal Challengers Bengaluru": "https://upload.wikimedia.org/wikipedia/en/2/2a/Royal_Challengers_Bangalore_2020.svg",
    "Kolkata Knight Riders":       "https://upload.wikimedia.org/wikipedia/en/4/4c/Kolkata_Knight_Riders_Logo.svg",
    "Sunrisers Hyderabad":         "https://upload.wikimedia.org/wikipedia/en/3/3f/Sunrisers_Hyderabad.svg",
    "Delhi Capitals":              "https://upload.wikimedia.org/wikipedia/en/f/f5/Delhi_Capitals_Logo.svg",
    "Punjab Kings":                "https://upload.wikimedia.org/wikipedia/en/d/d4/Punjab_Kings_Logo.svg",
    "Rajasthan Royals":            "https://upload.wikimedia.org/wikipedia/en/6/60/Rajasthan_Royals_Logo.svg",
    "Gujarat Titans":              "https://upload.wikimedia.org/wikipedia/en/0/09/Gujarat_Titans_Logo.svg",
    "Lucknow Super Giants":        "https://upload.wikimedia.org/wikipedia/en/a/a9/Lucknow_Super_Giants_Logo.svg",
    "Deccan Chargers":             "https://upload.wikimedia.org/wikipedia/en/7/7e/Deccan_Chargers.svg",
    "Rising Pune Supergiants":     "https://upload.wikimedia.org/wikipedia/en/5/5e/Rising_Pune_Supergiants_Logo.svg",
    "Gujarat Lions":               "https://upload.wikimedia.org/wikipedia/en/0/07/Gujarat_Lions_Logo.svg",
    "Kochi Tuskers Kerala":        "https://upload.wikimedia.org/wikipedia/en/e/e9/Kochi_Tuskers.svg",
    "Pune Warriors":               "https://upload.wikimedia.org/wikipedia/en/d/da/Pune_Warriors_India.svg",
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def download_as_data_uri(url: str, referer: str = "https://en.wikipedia.org/") -> str | None:
    """Download image bytes and return as a base64 data URI."""
    try:
        headers = {**HEADERS_WEB, "Referer": referer}
        req  = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as r:
            data        = r.read()
            content_type = r.headers.get_content_type() or "image/png"
        if not data:
            return None
        b64 = base64.b64encode(data).decode()
        return f"data:{content_type};base64,{b64}"
    except Exception:
        return None


def commons_api(params: dict) -> dict:
    params["format"] = "json"
    url = COMMONS_API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers=HEADERS_API)
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def scrape_og_image(url: str) -> str | None:
    """Fetch a web page and extract its og:image URL."""
    try:
        req  = urllib.request.Request(url, headers=HEADERS_WEB)
        html = urllib.request.urlopen(req, timeout=12).read().decode("utf-8", errors="ignore")
        for pat in [r'property="og:image"\s+content="([^"]+)"',
                    r'content="([^"]+)"\s+property="og:image"']:
            m = re.search(pat, html)
            if m:
                img = m.group(1)
                if not any(x in img.lower() for x in ["placeholder", "default", "generic"]):
                    return img
    except Exception:
        pass
    return None


# ── Sources ───────────────────────────────────────────────────────────────────

def source_wikimedia_direct(team: str, info: dict) -> list[str]:
    """Download the known Wikimedia SVG/PNG directly."""
    url = WIKIMEDIA_URLS.get(team)
    if not url:
        return []
    data_uri = download_as_data_uri(url)
    return [data_uri] if data_uri else []


def source_wikipedia_article(team: str, info: dict) -> list[str]:
    """Wikipedia REST summary → infobox image for the team article."""
    wiki_title = info.get("wiki", team)
    try:
        api_url = f"{WIKI_REST}/{urllib.parse.quote(wiki_title, safe='')}"
        req = urllib.request.Request(api_url, headers=HEADERS_API)
        d   = json.loads(urllib.request.urlopen(req, timeout=10).read())
        img_url = (d.get("thumbnail") or d.get("originalimage") or {}).get("source")
        if img_url:
            data_uri = download_as_data_uri(img_url)
            if data_uri:
                return [data_uri]
    except Exception:
        pass
    return []


def source_commons_search(team: str, info: dict) -> list[str]:
    """Search Wikimedia Commons file namespace for the team logo."""
    results = []
    for query in [f"{team} logo cricket IPL", f"{team} IPL logo", team + " logo"]:
        try:
            d = commons_api({
                "action": "query", "generator": "search",
                "gsrsearch": query, "gsrnamespace": 6, "gsrlimit": 5,
                "prop": "imageinfo", "iiprop": "url|mime", "iiurlwidth": THUMB,
            })
            for pg in d.get("query", {}).get("pages", {}).values():
                ii    = pg.get("imageinfo", [{}])[0]
                mime  = ii.get("mime", "")
                thumb = ii.get("thumburl") or ii.get("url", "")
                if mime.startswith("image/") and thumb:
                    data_uri = download_as_data_uri(thumb, "https://commons.wikimedia.org/")
                    if data_uri and data_uri not in results:
                        results.append(data_uri)
            if results:
                break
        except Exception:
            pass
        time.sleep(SLEEP)
    return results[:3]


def source_ipl_website(team: str, info: dict) -> list[str]:
    """Scrape og:image from the IPL official website team page."""
    slug = info.get("ipl_slug")
    if not slug:
        return []
    url = f"https://www.iplt20.com/teams/{slug}"
    img_url = scrape_og_image(url)
    if img_url:
        if img_url.startswith("/"):
            img_url = "https://www.iplt20.com" + img_url
        data_uri = download_as_data_uri(img_url, "https://www.iplt20.com/")
        if data_uri:
            return [data_uri]
    return []


def source_cricbuzz(team: str, info: dict) -> list[str]:
    """Scrape og:image from the Cricbuzz team page."""
    slug = info.get("cb_slug")
    if not slug:
        return []
    url = f"https://www.cricbuzz.com/cricket-team/{slug}/squad"
    img_url = scrape_og_image(url)
    if img_url:
        if img_url.startswith("/"):
            img_url = "https://www.cricbuzz.com" + img_url
        data_uri = download_as_data_uri(img_url, "https://www.cricbuzz.com/")
        if data_uri:
            return [data_uri]
    return []


# ── Main ──────────────────────────────────────────────────────────────────────

SOURCES = [
    ("Wikimedia-direct",  source_wikimedia_direct),
    ("Wikipedia-article", source_wikipedia_article),
    ("Commons-search",    source_commons_search),
    ("IPL-website",       source_ipl_website),
    ("Cricbuzz",          source_cricbuzz),
]

DEBUG = "--debug" in sys.argv


def main():
    cands_path = ASSETS_DIR / "team_logo_candidates.json"
    candidates: dict = {}
    if cands_path.exists():
        candidates = json.loads(cands_path.read_text())

    team_names = list(TEAMS.keys())
    total      = len(team_names)

    for src_label, src_fn in SOURCES:
        already = sum(1 for v in candidates.values() if src_label in v.get("sources_done", []))
        print(f"\n── {src_label}  ({already}/{total} already done) ───────────────────────")

        for team in team_names:
            info  = TEAMS[team]
            entry = candidates.setdefault(team, {"candidates": [], "sources_done": []})

            if src_label in entry.get("sources_done", []):
                print(f"  [skip]  {team}")
                continue

            try:
                new_uris = src_fn(team, info) or []
            except Exception as e:
                new_uris = []
                if DEBUG: print(f"  {team}: ERROR {e}")

            existing = set(entry["candidates"])
            added    = [u for u in new_uris if u not in existing]
            entry["candidates"] = (entry["candidates"] + added)[:8]
            entry.setdefault("sources_done", []).append(src_label)

            status = f"+{len(added)} logo(s)  (total {len(entry['candidates'])})" if added else "nothing new"
            print(f"  {team}: {status}")

            cands_path.write_text(json.dumps(candidates, ensure_ascii=False, indent=2))
            time.sleep(SLEEP)

    print(f"\n── Summary ─────────────────────────────────────────────")
    with_logos = sum(1 for v in candidates.values() if v.get("candidates"))
    print(f"  Teams with ≥1 logo: {with_logos}/{total}")

    generate_picker(candidates)
    print(f"\nOpen logo_picker.html in your browser to pick the best logo per team.")


def generate_picker(candidates):
    data_json = json.dumps(
        [{"team": t, "candidates": v.get("candidates", [])}
         for t, v in candidates.items()],
        ensure_ascii=False
    )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>IPL Team Logo Picker</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
          background: #f0f2f5; color: #1a1a1a; }}
  #header {{ position: sticky; top: 0; z-index: 100; background: #1a1a2e; color: #fff;
             display: flex; align-items: center; gap: 16px; padding: 12px 24px;
             box-shadow: 0 2px 8px rgba(0,0,0,.4); }}
  #header h1 {{ font-size: 1.1rem; font-weight: 700; flex: 1; }}
  #progress {{ font-size: .85rem; opacity: .8; }}
  #save-btn {{ padding: 8px 18px; border-radius: 8px; border: none;
               background: #22c55e; color: #fff; font-weight: 700; cursor: pointer; }}
  #save-btn:hover {{ background: #16a34a; }}
  #grid {{ padding: 20px 24px; display: flex; flex-direction: column; gap: 16px; }}
  .team-card {{ background: #fff; border-radius: 12px; overflow: hidden;
                box-shadow: 0 1px 4px rgba(0,0,0,.1); }}
  .team-card.done {{ border-left: 4px solid #22c55e; }}
  .team-card.skipped {{ border-left: 4px solid #94a3b8; }}
  .team-header {{ display: flex; align-items: center; gap: 12px; padding: 12px 16px;
                  background: #f8fafc; border-bottom: 1px solid #e5e7eb; }}
  .team-name {{ font-weight: 700; font-size: 1rem; flex: 1; }}
  .status-badge {{ font-size: .78rem; padding: 3px 10px; border-radius: 20px; font-weight: 600; }}
  .status-pending  {{ background: #fef3c7; color: #92400e; }}
  .status-selected {{ background: #dcfce7; color: #166534; }}
  .status-skipped  {{ background: #f1f5f9; color: #64748b; }}
  .logos {{ display: flex; flex-wrap: wrap; gap: 12px; padding: 16px; }}
  .logo-wrap {{ cursor: pointer; border: 3px solid transparent; border-radius: 8px;
                padding: 8px; background: #f8fafc; transition: border-color .15s; }}
  .logo-wrap:hover {{ border-color: #60a5fa; }}
  .logo-wrap.selected {{ border-color: #22c55e; background: #f0fdf4; }}
  .logo-wrap img {{ width: 100px; height: 100px; object-fit: contain; display: block; }}
  .no-logos {{ color: #94a3b8; font-size: .85rem; padding: 8px 16px; }}
  .card-actions {{ display: flex; gap: 8px; padding: 8px 16px 14px; }}
  .btn {{ padding: 6px 14px; border-radius: 6px; border: none; font-size: .82rem;
          font-weight: 600; cursor: pointer; }}
  .btn-skip {{ background: #f1f5f9; color: #475569; }}
  .btn-skip:hover {{ background: #e2e8f0; }}
</style>
</head>
<body>
<div id="header">
  <h1>🏏 IPL Team Logo Picker</h1>
  <span id="progress">0 / {len(candidates)} selected</span>
  <button id="save-btn" onclick="saveJSON()">⬇ Download team_logos.json</button>
</div>
<div id="grid"></div>
<script>
const TEAMS = {data_json};
const SEL = {{}};

function updateProgress() {{
  const n = Object.keys(SEL).filter(k => SEL[k] !== null).length;
  document.getElementById('progress').textContent = n + ' / {len(candidates)} selected';
}}

function render() {{
  const grid = document.getElementById('grid');
  grid.innerHTML = '';
  TEAMS.forEach(t => {{
    const sel = SEL[t.team];
    const card = document.createElement('div');
    card.className = 'team-card' + (sel !== undefined ? (sel ? ' done' : ' skipped') : '');
    card.innerHTML = `
      <div class="team-header">
        <span class="team-name">${{t.team}}</span>
        <span class="status-badge ${{sel === undefined ? 'status-pending' : sel ? 'status-selected' : 'status-skipped'}}">
          ${{sel === undefined ? 'Pending' : sel ? 'Selected' : 'Skipped'}}
        </span>
      </div>
      <div class="logos">
        ${{t.candidates.length === 0
          ? '<span class="no-logos">No logos found.</span>'
          : t.candidates.map((uri, idx) => `
              <div class="logo-wrap ${{sel === uri ? 'selected' : ''}}"
                   onclick="pick('${{t.team}}', ${{idx}})">
                <img src="${{uri}}" alt="${{t.team}}" onerror="this.parentElement.style.display='none'">
              </div>`).join('')
        }}
      </div>
      <div class="card-actions">
        <button class="btn btn-skip" onclick="skip('${{t.team}}')">No good logo</button>
      </div>
    `;
    grid.appendChild(card);
  }});
  updateProgress();
}}

function pick(team, idx) {{
  const t = TEAMS.find(x => x.team === team);
  SEL[team] = t.candidates[idx];
  render();
}}
function skip(team) {{
  SEL[team] = null;
  render();
}}

function saveJSON() {{
  const out = {{}};
  for (const [team, uri] of Object.entries(SEL)) {{
    if (uri) out[team] = uri;
  }}
  const blob = new Blob([JSON.stringify(out, null, 2)], {{type: 'application/json'}});
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'team_logos.json';
  a.click();
}}

render();
</script>
</body>
</html>"""

    out = SCRIPT_DIR / "logo_picker.html"
    out.write_text(html, encoding="utf-8")
    print(f"  Saved → {out}")


if __name__ == "__main__":
    main()
