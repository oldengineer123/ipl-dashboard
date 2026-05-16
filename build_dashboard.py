#!/usr/bin/env python3
"""
Build a self-contained IPL analytics dashboard (single HTML file).

Reads deliveries.csv from a build/ folder and writes one HTML file with all
the data embedded. The output works offline — just double-click it.

Tabs:
  Batting  — batter leaderboard (runs, balls, SR, avg, outs)
  Bowling  — bowler leaderboard (matches, overs, runs, wickets, eco, avg, SR, dot%)

Note: ball speed is not present in Cricsheet data, so fastest/slowest ball
metrics are not available. Dot % is provided instead.

Usage:
    python3 build_dashboard.py <build_dir> <output_html>
"""

import argparse
import csv
import json
import sys
from pathlib import Path


# Wicket kinds that are NOT credited to the bowler
NON_BOWL_WICKETS = frozenset({
    'run out', 'obstructing the field', 'handled the ball',
    'retired hurt', 'retired out', 'retired not out', 'retired',
})


HTML_TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>IPL Dashboard</title>
<style>
*,*::before,*::after{box-sizing:border-box}
body{margin:0}
:root{
  --bg:#fafafa;
  --surface:#fff;
  --border:#e7e7e7;
  --border-strong:#d4d4d4;
  --text:#171717;
  --text-muted:#737373;
  --accent:#15803d;
  --accent-hover:#166534;
  --accent-bg:#f0fdf4;
  --hover:#f5f5f5;
  --shadow:0 1px 2px 0 rgb(0 0 0 / .04);
  --shadow-pop:0 6px 20px rgb(0 0 0 / .08);
}
html,body{
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",sans-serif;
  color:var(--text);background:var(--bg);font-size:14px;line-height:1.5;
}

/* ---- Header ---- */
header{
  background:var(--surface);border-bottom:1px solid var(--border);
  padding:1rem 2rem;display:flex;align-items:center;
  justify-content:space-between;flex-wrap:wrap;gap:.75rem
}
header h1{margin:0;font-size:1.2rem;font-weight:700;letter-spacing:-.015em}
header .subtitle{color:var(--text-muted);font-size:.8rem;margin-top:.1rem}

/* ---- Tab bar ---- */
.tab-bar{display:flex;background:var(--hover);border-radius:8px;padding:3px;gap:2px}
.tab-btn{
  padding:.4rem 1.1rem;border:none;background:transparent;border-radius:6px;
  cursor:pointer;font-size:.875rem;font-weight:500;color:var(--text-muted);
  font-family:inherit;transition:all .15s;white-space:nowrap;
}
.tab-btn:hover{color:var(--text)}
.tab-btn.active{
  background:var(--surface);color:var(--text);
  box-shadow:0 1px 3px rgb(0 0 0/.1),0 1px 2px rgb(0 0 0/.06);
}

/* ---- Main layout ---- */
main{max-width:1400px;margin:0 auto;padding:1.5rem 2rem}

/* ---- Filters ---- */
.filters{
  background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:1.25rem 1.5rem;margin-bottom:1rem;box-shadow:var(--shadow)
}
.filter-row{display:flex;flex-wrap:wrap;gap:1rem 1.5rem;align-items:flex-end;margin-bottom:1rem}
.filter-row:last-child{margin-bottom:0}
.filter-group{display:flex;flex-direction:column;gap:.4rem;min-width:0}
.label{font-size:.7rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em}

/* ---- Season chips ---- */
.chip-row{display:flex;flex-wrap:wrap;gap:.375rem}
.chip{
  padding:.3rem .7rem;border:1px solid var(--border-strong);border-radius:999px;
  background:var(--surface);cursor:pointer;font-size:.8125rem;color:var(--text);
  transition:background .1s,color .1s,border-color .1s;user-select:none;
  white-space:nowrap;font-family:inherit
}
.chip:hover{background:var(--hover)}
.chip.active{background:var(--accent);border-color:var(--accent);color:#fff}
.chip.active:hover{background:var(--accent-hover)}

/* ---- Button group (innings / overs) ---- */
.button-group{display:inline-flex;border:1px solid var(--border-strong);border-radius:8px;overflow:hidden}
.button-group button{
  padding:.45rem .8rem;border:none;background:var(--surface);cursor:pointer;
  font-size:.8125rem;color:var(--text);border-right:1px solid var(--border);
  white-space:nowrap;font-family:inherit
}
.button-group button:last-child{border-right:none}
.button-group button:hover{background:var(--hover)}
.button-group button.active{background:var(--accent);color:#fff}

/* ---- Dropdowns ---- */
.dropdown{position:relative}
.dropdown-toggle{
  padding:.45rem .8rem;border:1px solid var(--border-strong);border-radius:8px;
  background:var(--surface);cursor:pointer;font-size:.8125rem;color:var(--text);
  text-align:left;min-width:190px;display:flex;align-items:center;
  justify-content:space-between;gap:.5rem;font-family:inherit
}
.dropdown-toggle:hover{background:var(--hover)}
.dropdown-toggle .arrow{color:var(--text-muted)}
.dropdown-menu{
  display:none;position:absolute;top:calc(100% + 4px);left:0;
  background:var(--surface);border:1px solid var(--border-strong);
  border-radius:8px;box-shadow:var(--shadow-pop);z-index:20;
  min-width:250px;max-height:340px;overflow:hidden;flex-direction:column
}
.dropdown.open .dropdown-menu{display:flex}
.dropdown-search{padding:.5rem;border-bottom:1px solid var(--border);background:var(--surface)}
.dropdown-search input{
  width:100%;padding:.35rem .55rem;border:1px solid var(--border);
  border-radius:6px;font-size:.8125rem;font-family:inherit
}
.dropdown-search input:focus{outline:2px solid var(--accent);outline-offset:-1px}
.dropdown-list{overflow-y:auto;flex:1;padding:.25rem 0}
.dropdown-item{display:flex;align-items:center;gap:.5rem;padding:.35rem .75rem;cursor:pointer;font-size:.8125rem}
.dropdown-item:hover{background:var(--hover)}
.dropdown-item input{margin:0;accent-color:var(--accent)}
.dropdown-empty{padding:.75rem;color:var(--text-muted);font-size:.8125rem;text-align:center}

/* ---- Number inputs ---- */
.number-input{
  padding:.45rem .55rem;border:1px solid var(--border-strong);border-radius:8px;
  font-size:.8125rem;font-family:inherit;background:var(--surface)
}
.number-input:focus{outline:2px solid var(--accent);outline-offset:-1px}

/* ---- Text button ---- */
.text-button{
  background:none;border:none;color:var(--accent);font-size:.8125rem;
  cursor:pointer;padding:.4rem .65rem;border-radius:6px;font-family:inherit
}
.text-button:hover{background:var(--accent-bg)}

.muted-sep{color:var(--text-muted);font-size:.8125rem}

/* ---- Results card ---- */
.results-card{
  background:var(--surface);border:1px solid var(--border);
  border-radius:12px;overflow:hidden;box-shadow:var(--shadow)
}
.results-header{
  padding:.85rem 1.5rem;border-bottom:1px solid var(--border);
  display:flex;align-items:center;justify-content:space-between;
  flex-wrap:wrap;gap:.75rem
}
.results-count{font-size:.875rem;color:var(--text-muted)}
.results-count strong{color:var(--text);font-weight:600}
.player-search-wrap{position:relative;display:flex;align-items:center}
.player-search-wrap svg{position:absolute;left:.55rem;color:var(--text-muted);pointer-events:none;flex-shrink:0}
.player-search{
  padding:.38rem .7rem .38rem 2rem;border:1px solid var(--border-strong);
  border-radius:8px;font-size:.8125rem;font-family:inherit;background:var(--surface);
  width:200px;transition:border-color .15s,width .2s
}
.player-search:focus{outline:2px solid var(--accent);outline-offset:-1px;width:240px}
.player-search:not(:placeholder-shown){border-color:var(--accent)}
.table-wrap{max-height:70vh;overflow:auto}

/* ---- Table ---- */
table{width:100%;border-collapse:collapse;font-size:.875rem}
thead th{
  text-align:left;padding:.6rem 1rem;background:#fafafa;
  border-bottom:1px solid var(--border);font-weight:600;
  color:var(--text-muted);font-size:.7rem;text-transform:uppercase;
  letter-spacing:.06em;position:sticky;top:0;cursor:pointer;
  user-select:none;white-space:nowrap;z-index:1
}
thead th.numeric{text-align:right}
thead th .sort-arrow{display:inline-block;margin-left:.25rem;opacity:.25}
thead th.sorted{color:var(--text)}
thead th.sorted .sort-arrow{opacity:1;color:var(--accent)}
thead th[data-static]{cursor:default}

tbody td{padding:.5rem 1rem;border-bottom:1px solid var(--border)}
tbody tr:last-child td{border-bottom:none}
tbody td.numeric{text-align:right;font-variant-numeric:tabular-nums}
tbody tr:hover{background:var(--hover)}
tbody td.rank{color:var(--text-muted);font-variant-numeric:tabular-nums;width:48px}
tbody td.player{font-weight:500}

/* ---- Better/worse indicator colours (bowling SR / avg) ---- */
.good{color:#15803d}
.bad{color:#b91c1c}

.empty,.loading{padding:3rem 2rem;text-align:center;color:var(--text-muted)}
.footnote{
  padding:.75rem 1.5rem;font-size:.75rem;color:var(--text-muted);
  border-top:1px solid var(--border);background:#fafafa;line-height:1.6
}
/* ---- KPI Strip ---- */
.kpi-strip{display:flex;flex-wrap:wrap;gap:1rem;margin-bottom:1rem}
.kpi{
  background:var(--surface);border:1px solid var(--border);border-radius:12px;
  padding:1rem 1.5rem;flex:1;min-width:110px;box-shadow:var(--shadow);text-align:center
}
.kpi-val{font-size:1.75rem;font-weight:700;line-height:1.2;color:var(--text)}
.kpi-val.win{color:var(--accent)}
.kpi-val.lose{color:#b91c1c}
.kpi-label{font-size:.7rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-top:.25rem}
.kpi-empty{color:var(--text-muted);padding:2rem;text-align:center;width:100%;font-size:.875rem}
/* ---- Sub-tab bar ---- */
.subtab-bar{
  display:flex;gap:0;margin-bottom:1rem;
  border:1px solid var(--border);border-radius:8px;overflow:hidden;
  background:var(--hover);padding:3px;
}
.subtab-btn{
  padding:.38rem .9rem;border:none;background:transparent;cursor:pointer;
  font-size:.8125rem;font-weight:500;color:var(--text-muted);font-family:inherit;
  border-radius:6px;white-space:nowrap;transition:all .15s;
}
.subtab-btn:hover{color:var(--text)}
.subtab-btn.active{
  background:var(--surface);color:var(--text);
  box-shadow:0 1px 3px rgb(0 0 0/.1),0 1px 2px rgb(0 0 0/.06);
}
/* ---- Teams contrib panels ---- */
.contrib-panels{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:900px){.contrib-panels{grid-template-columns:1fr}}
.contrib-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:var(--shadow)}
.contrib-card-header{padding:.65rem 1.25rem;border-bottom:1px solid var(--border);background:#fafafa;font-weight:600;font-size:.8125rem}
.contrib-toggle-row{display:flex;align-items:center;gap:.75rem;padding:.65rem 1.5rem;border-bottom:1px solid var(--border);background:#fafafa;flex-wrap:wrap}
.contrib-toggle-label{font-size:.75rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;letter-spacing:.04em}
/* ---- Player profile ---- */
.player-stat-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;overflow:hidden;box-shadow:var(--shadow)}
.player-stat-card-header{padding:.55rem 1.1rem;background:#fafafa;border-bottom:1px solid var(--border);font-weight:700;font-size:.8rem;text-transform:uppercase;letter-spacing:.06em;color:var(--text-muted)}
.player-stat-grid{display:grid;grid-template-columns:1fr 1fr;gap:0}
.player-stat-item{padding:.6rem 1.1rem;border-bottom:1px solid var(--border);border-right:1px solid var(--border)}
.player-stat-item:nth-child(even){border-right:none}
.player-stat-item:nth-last-child(-n+2){border-bottom:none}
.player-stat-label{font-size:.7rem;color:var(--text-muted);font-weight:600;text-transform:uppercase;letter-spacing:.04em;margin-bottom:.15rem}
.player-stat-value{font-size:1.15rem;font-weight:700;color:var(--text)}
.player-stat-value.accent{color:var(--accent)}
.player-phase-table{width:100%;border-collapse:collapse;font-size:.8rem}
.player-phase-table th,.player-phase-table td{padding:.4rem .8rem;border-bottom:1px solid var(--border);text-align:right}
.player-phase-table th:first-child,.player-phase-table td:first-child{text-align:left;font-weight:600}
.player-phase-table thead th{background:#fafafa;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em;color:var(--text-muted)}
.player-kpi-strip{display:flex;flex-wrap:wrap;gap:0;border-bottom:1px solid var(--border);background:var(--surface)}
.player-kpi-item{flex:1;min-width:110px;padding:.8rem 1.1rem;border-right:1px solid var(--border);text-align:center}
.player-kpi-item:last-child{border-right:none}
.player-kpi-label{font-size:.68rem;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;font-weight:600;margin-bottom:.2rem}
.player-kpi-value{font-size:1.4rem;font-weight:800;color:var(--text)}
.player-kpi-sub{font-size:.75rem;color:var(--text-muted);margin-top:.1rem}
/* ---- Team logos & player photos ---- */
.team-logo-wrap{display:inline-flex;align-items:center;justify-content:center;flex-shrink:0;border-radius:50%;overflow:hidden;background:#f0f0f0}
.team-logo-wrap img{width:100%;height:100%;object-fit:contain}
.team-logo-fallback{display:flex;align-items:center;justify-content:center;border-radius:50%;font-weight:800;color:#fff;font-size:.7em;line-height:1;letter-spacing:-.02em}
.player-photo-wrap{flex-shrink:0;border-radius:50%;overflow:hidden;background:#e8e8e8;display:flex;align-items:center;justify-content:center}
.player-photo-wrap img{width:100%;height:100%;object-fit:cover}
.player-photo-fallback{display:flex;align-items:center;justify-content:center;border-radius:50%;font-weight:700;color:#fff;background:var(--accent);font-size:1.1rem}
.player-link{color:var(--accent);cursor:pointer;text-decoration:underline;text-decoration-color:transparent;transition:text-decoration-color .15s}
.player-link:hover{text-decoration-color:var(--accent)}
.player-search-item{padding:.5rem 1rem;cursor:pointer;font-size:.875rem;border-bottom:1px solid var(--border)}
.player-search-item:last-child{border-bottom:none}
.player-search-item:hover{background:var(--bg)}
@media(max-width:900px){#player-cards{grid-template-columns:1fr!important}}
/* ---- Teams toss grid ---- */
.toss-grid{display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-bottom:1rem}
@media(max-width:600px){.toss-grid{grid-template-columns:1fr}}
.toss-card{background:var(--surface);border:1px solid var(--border);border-radius:12px;padding:1.25rem 1.5rem;box-shadow:var(--shadow)}
.toss-title{font-size:.75rem;font-weight:700;color:var(--text-muted);text-transform:uppercase;letter-spacing:.06em;margin-bottom:.9rem}
.toss-stat{display:flex;justify-content:space-between;align-items:center;padding:.25rem 0;font-size:.875rem;border-bottom:1px solid var(--border)}
.toss-stat:last-child{border-bottom:none}
.toss-stat .val{font-weight:600}
.toss-big{font-size:1.5rem;font-weight:700;margin-bottom:.5rem}
/* ---- Team placeholder ---- */
.team-placeholder{padding:3rem 2rem;text-align:center;color:var(--text-muted)}
.team-placeholder strong{display:block;font-size:1rem;margin-bottom:.4rem;color:var(--text)}
.team-single-select{
  padding:.45rem .8rem;border:1px solid var(--border-strong);border-radius:8px;
  background:var(--surface);font-size:.8125rem;font-family:inherit;
  cursor:pointer;min-width:240px
}
.team-single-select:focus{outline:2px solid var(--accent);outline-offset:-1px}

</style>
</head>
<body>

<header>
  <div>
    <h1>IPL Dashboard</h1>
    <div class="subtitle" id="subtitle"></div>
  </div>
  <nav class="tab-bar" id="tab-bar">
    <button class="tab-btn active" data-tab="batting">Batting</button>
    <button class="tab-btn" data-tab="bowling">Bowling</button>
    <button class="tab-btn" data-tab="teams">Teams</button>
    <button class="tab-btn" data-tab="fielding">Fielding</button>
    <button class="tab-btn" data-tab="player">Player</button>
  </nav>
  <button class="text-button" id="reset-button">Reset filters</button>
</header>

<main>

  <!-- ===== SHARED FILTERS: Seasons / Innings / Overs / Venue ===== -->
  <section class="filters" id="shared-filters">
    <div class="filter-row">
      <div class="filter-group" style="flex:1;min-width:280px">
        <span class="label">Seasons</span>
        <div class="chip-row" id="seasons-chips"></div>
      </div>
    </div>
    <div class="filter-row">
      <div class="filter-group">
        <span class="label" id="innings-label">Innings</span>
        <div class="button-group" id="innings-toggle">
          <button data-value="all" class="active">All</button>
          <button data-value="1" id="inn-btn-1">Batting 1st</button>
          <button data-value="2" id="inn-btn-2">Chasing</button>
        </div>
      </div>
      <div class="filter-group" style="min-width:380px">
        <span class="label">Overs</span>
        <div style="display:flex;gap:.5rem;align-items:center;flex-wrap:wrap">
          <div class="button-group" id="over-presets">
            <button data-min="1" data-max="20" class="active">All</button>
            <button data-min="1" data-max="6">Powerplay</button>
            <button data-min="7" data-max="15">Middle</button>
            <button data-min="16" data-max="20">Death</button>
          </div>
          <span class="muted-sep">or</span>
          <input type="number" id="over-min" class="number-input" min="1" max="20" value="1" style="width:64px">
          <span class="muted-sep">to</span>
          <input type="number" id="over-max" class="number-input" min="1" max="20" value="20" style="width:64px">
        </div>
      </div>
      <div class="filter-group">
        <span class="label">Venue</span>
        <div class="dropdown" data-key="venue"></div>
      </div>
    </div>
  </section>

  <!-- ===== BATTING-SPECIFIC FILTERS ===== -->
  <section class="filters" id="bat-filters">
    <div class="filter-row">
      <div class="filter-group">
        <span class="label">Min balls faced</span>
        <input type="number" id="min-balls" class="number-input" min="0" value="100" style="width:90px">
      </div>
      <div class="filter-group">
        <span class="label">Opposition (bowling team)</span>
        <div class="dropdown" data-key="opposition"></div>
      </div>
      <div class="filter-group">
        <span class="label">Batter's team</span>
        <div class="dropdown" data-key="bat_team"></div>
      </div>
      <div class="filter-group" style="flex:1;min-width:220px">
        <span class="label">Bowler</span>
        <div class="dropdown" data-key="bowler"></div>
      </div>
    </div>
  </section>

  <!-- ===== BOWLING-SPECIFIC FILTERS ===== -->
  <section class="filters" id="bowl-filters" style="display:none">
    <div class="filter-row">
      <div class="filter-group">
        <span class="label">Min balls bowled</span>
        <input type="number" id="min-balls-bowl" class="number-input" min="0" value="120" style="width:90px">
      </div>
      <div class="filter-group">
        <span class="label">Opposition (batting team)</span>
        <div class="dropdown" data-key="bowl_opposition"></div>
      </div>
      <div class="filter-group">
        <span class="label">Bowler's team</span>
        <div class="dropdown" data-key="bowl_team"></div>
      </div>
      <div class="filter-group" style="flex:1;min-width:220px">
        <span class="label">Batter</span>
        <div class="dropdown" data-key="batter_filter"></div>
      </div>
    </div>
  </section>

  <!-- ===== RESULTS ===== -->
  <section class="results-card" id="main-results">
    <div class="results-header">
      <div class="results-count" id="results-count">Loading data…</div>
      <div class="player-search-wrap">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
        <input type="search" id="player-search" class="player-search" placeholder="Find player…" autocomplete="off">
      </div>
      <div class="muted-sep" id="results-meta"></div>
    </div>
    <div class="table-wrap" id="table-wrap">
      <div class="loading">Parsing data…</div>
    </div>
    <div class="footnote" id="footnote"></div>
  </section>

  <!-- ===== TEAMS SECTION ===== -->
  <div id="teams-section" style="display:none">

    <section class="filters" id="team-top-filters">
      <div class="filter-row">
        <div class="filter-group">
          <span class="label">Team</span>
          <div style="display:flex;align-items:center;gap:.6rem">
            <span id="team-logo-preview" style="display:none"></span>
            <select class="team-single-select" id="team-picker">
              <option value="-1">— pick a team —</option>
            </select>
          </div>
        </div>
        <div class="filter-group" style="flex:1;min-width:280px">
          <span class="label">Seasons</span>
          <div class="chip-row" id="team-seasons-chips"></div>
        </div>
      </div>
      <div class="filter-row">
        <div class="filter-group">
          <span class="label">Stage</span>
          <div class="button-group" id="team-stage-toggle">
            <button data-value="all" class="active">All</button>
            <button data-value="group">Group</button>
            <button data-value="playoffs">Playoffs</button>
            <button data-value="final">Final</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="label">Toss</span>
          <div class="button-group" id="team-toss-toggle">
            <button data-value="all" class="active">All</button>
            <button data-value="won">Won</button>
            <button data-value="lost">Lost</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="label">Innings</span>
          <div class="button-group" id="team-innings-toggle">
            <button data-value="all" class="active">All</button>
            <button data-value="bat1">Batting 1st</button>
            <button data-value="chase">Chasing</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="label">vs Opponent</span>
          <select class="team-single-select" id="team-opponent" style="min-width:200px">
            <option value="-1">All opponents</option>
          </select>
        </div>
      </div>
    </section>

    <div class="kpi-strip" id="kpi-strip">
      <div class="kpi-empty">Select a team above to see their stats</div>
    </div>

    <div class="subtab-bar" id="subtab-bar">
      <button class="subtab-btn active" data-subtab="season">Team Performance</button>
      <button class="subtab-btn" data-subtab="contributors">Contributors</button>
    </div>

    <section class="results-card" id="teams-results">
      <div class="team-placeholder"><strong>Pick a team to get started</strong>Select a team using the filter above.</div>
    </section>

  </div><!-- /#teams-section -->

  <!-- ===== FIELDING SECTION ===== -->
  <div id="field-section" style="display:none">

    <section class="filters" id="field-filters">
      <div class="filter-row">
        <div class="filter-group" style="flex:1;min-width:280px">
          <span class="label">Seasons</span>
          <div class="chip-row" id="field-seasons-chips"></div>
        </div>
      </div>
      <div class="filter-row">
        <div class="filter-group">
          <span class="label">Min dismissals</span>
          <input type="number" id="min-dismissals" class="number-input" min="0" value="5" style="width:80px">
        </div>
        <div class="filter-group">
          <span class="label">Dismissal type</span>
          <div class="button-group" id="field-type-toggle">
            <button data-value="all" class="active">All</button>
            <button data-value="0">Catches</button>
            <button data-value="1">Run-outs</button>
            <button data-value="2">Stumpings</button>
          </div>
        </div>
        <div class="filter-group">
          <span class="label">Fielder's team</span>
          <div class="dropdown" data-key="field_team"></div>
        </div>
        <div class="filter-group">
          <span class="label">Opposition</span>
          <div class="dropdown" data-key="field_opp"></div>
        </div>
      </div>
    </section>

    <section class="results-card" id="field-results">
      <div class="results-header">
        <div class="results-count" id="field-count">Loading…</div>
        <div class="player-search-wrap">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="11" cy="11" r="8"/><line x1="21" y1="21" x2="16.65" y2="16.65"/></svg>
          <input type="search" id="field-search" class="player-search" placeholder="Find fielder…" autocomplete="off">
        </div>
        <div class="muted-sep" id="field-meta"></div>
      </div>
      <div class="table-wrap" id="field-table-wrap">
        <div class="loading">Select the Fielding tab to load…</div>
      </div>
      <div class="footnote" id="field-footnote">
        Catches excludes caught &amp; bowled. Caught &amp; Bowled is credited to the bowler.
        Run-out (Direct) = fielder who effected the dismissal. Run-out (Assist) = second fielder involved.
        Stumpings are wicketkeeper dismissals. Super overs excluded.
      </div>
    </section>

  </div><!-- /#field-section -->

  <!-- ============================================================== -->
  <!--  PLAYER PROFILE SECTION                                        -->
  <!-- ============================================================== -->
  <div id="player-section" style="display:none">

    <!-- Player search bar -->
    <section class="filter-section" style="padding:.75rem 1.5rem;display:flex;align-items:center;gap:1rem;flex-wrap:wrap">
      <label style="font-weight:600;font-size:.85rem">Player</label>
      <div style="position:relative;flex:1;max-width:340px">
        <input type="text" id="profile-search" class="number-input"
               placeholder="Search player…"
               style="width:100%;padding:.45rem .75rem;font-size:.9rem" autocomplete="off">
        <div id="profile-dropdown" style="display:none;position:absolute;top:calc(100% + 4px);left:0;right:0;
             background:var(--surface);border:1px solid var(--border);border-radius:6px;
             max-height:260px;overflow-y:auto;z-index:50;box-shadow:0 4px 16px rgba(0,0,0,.12)">
        </div>
      </div>
      <span id="profile-selected-name" style="font-weight:600;font-size:1rem;color:var(--accent)"></span>
    </section>

    <!-- Player filters (shown after a player is selected) -->
    <div id="player-filter-bar" style="display:none;border-bottom:1px solid var(--border);background:#fafafa;padding:.6rem 1.5rem;display:none;flex-wrap:wrap;gap:1rem;align-items:flex-start">
      <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
        <span class="contrib-toggle-label">Team</span>
        <div id="player-team-chips" style="display:flex;gap:.35rem;flex-wrap:wrap"></div>
      </div>
      <div style="display:flex;align-items:center;gap:.5rem;flex-wrap:wrap">
        <span class="contrib-toggle-label">Season</span>
        <div id="player-season-chips" style="display:flex;gap:.35rem;flex-wrap:wrap"></div>
      </div>
    </div>

    <!-- KPI strip -->
    <div id="player-kpi" style="border-bottom:1px solid var(--border)">
      <div class="kpi-empty">Search for a player above to view their profile</div>
    </div>

    <!-- Profile body -->
    <div id="player-body" style="padding:1.25rem 1.5rem;display:none">

      <!-- Stat cards row -->
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:1rem;margin-bottom:1.25rem" id="player-cards">
      </div>

      <!-- Season-by-season table -->
      <div class="contrib-card" id="player-season-card" style="margin-bottom:1rem">
        <div class="contrib-card-header">Season by Season</div>
        <div class="table-wrap" id="player-season-table"></div>
      </div>

    </div>
  </div><!-- /#player-section -->

</main>

<script id="data" type="application/json">__DATA__</script>
<script>__TEAM_LOGOS_JS__</script>
<script>
(function(){
'use strict';

/* ------------------------------------------------------------------ */
/*  Decode embedded data                                                */
/* ------------------------------------------------------------------ */
const raw = JSON.parse(document.getElementById('data').textContent);
const N          = raw.n_events;
const e_batter   = new Uint16Array(raw.e_batter);
const e_bowler   = new Uint16Array(raw.e_bowler);
const e_season   = new Uint8Array(raw.e_season);
const e_bat_team = new Uint8Array(raw.e_bat_team);
const e_bowl_team= new Uint8Array(raw.e_bowl_team);
const e_venue    = new Uint8Array(raw.e_venue);
const e_over     = new Uint8Array(raw.e_over);
const e_innings  = new Uint8Array(raw.e_innings);
const e_runs     = new Uint8Array(raw.e_runs);
const e_ball_faced  = new Uint8Array(raw.e_ball_faced);   // 1 = legal (not wide)
const e_dismissed   = new Uint8Array(raw.e_dismissed);
const e_bowl_runs   = new Uint8Array(raw.e_bowl_runs);    // runs charged to bowler
const e_bowl_wicket = new Uint8Array(raw.e_bowl_wicket);  // 1 = bowler wicket
const e_match       = new Uint16Array(raw.e_match);
// e_is_wide is derived: wide = (e_ball_faced[i] === 0)
// e_is_noball is stored sparse; re-inflate into a Uint8Array once at load time
const e_is_noball = new Uint8Array(N);
for (const idx of raw.noball_indices) e_is_noball[idx] = 1;


/* ---- Match-level metadata arrays ---- */
const m_t1_balls = new Uint8Array(raw.m_t1_balls);
const m_t2_balls = new Uint8Array(raw.m_t2_balls);
const nTeamsRank = raw.n_teams_for_rank;
const seasonRankFlat = new Uint8Array(raw.season_rankings);
function getGroupRank(si, ti) { return seasonRankFlat[si * nTeamsRank + ti] || 0; }
const m_team1_a  = new Uint8Array(raw.m_team1);
const m_team2_a  = new Uint8Array(raw.m_team2);
const m_season_m = new Uint8Array(raw.m_season_m);
const m_winner   = new Int16Array(raw.m_winner);   // team_idx or -1
const m_toss_win = new Uint8Array(raw.m_toss_win);
const m_toss_dec = new Uint8Array(raw.m_toss_dec); // 0=bat 1=field
const m_stage    = new Uint8Array(raw.m_stage);
const m_t1_total = new Uint16Array(raw.m_t1_total);
const m_t2_total = new Uint16Array(raw.m_t2_total);
const m_is_tie   = new Uint8Array(raw.m_is_tie);
const m_no_result= new Uint8Array(raw.m_no_result);
const stages_list = raw.stages;
/* ---- Fielding event arrays ---- */
const NF         = raw.n_fd;
const fd_fielder = new Uint16Array(raw.fd_fielder);
const fd_season  = new Uint8Array(raw.fd_season);
const fd_bat_team= new Uint8Array(raw.fd_bat_team);
const fd_bowl_team=new Uint8Array(raw.fd_bowl_team);
const fd_type    = new Uint8Array(raw.fd_type);
const fd_match_a = new Uint16Array(raw.fd_match);
const fielders   = raw.fielders;
const nFielders  = fielders.length;

const PLAYOFF_STAGES = new Set(['Eliminator','Qualifier 1','Qualifier 2','Elimination Final','Semi Final','3rd Place Play-Off','Final']);

const batters  = raw.batters;
const bowlers  = raw.bowlers;
const teams    = raw.teams;
const venues   = raw.venues;
const seasons  = raw.seasons;
const nBatters = batters.length;
const nBowlers = bowlers.length;
const nMatches = raw.n_matches;

/* Player profile arrays — declared after nBatters/nBowlers/nFielders */
const all_players       = raw.all_players;
const nPlayers          = all_players.length;
const player_bat_idx    = new Int16Array(raw.player_bat_idx);
const player_bowl_idx   = new Int16Array(raw.player_bowl_idx);
const player_field_idx  = new Int16Array(raw.player_field_idx);
const m_pom             = new Int16Array(raw.m_pom);
/* Cricinfo player IDs — 0 means unknown */
const player_cricinfo   = new Int32Array(raw.player_cricinfo || new Array(nPlayers).fill(0));
/* Headshot URLs — empty string means no photo; populated by batch scraper */
const player_headshots  = raw.player_headshots || [];

/* Reverse lookups: batter/bowler/fielder index → all_players index */
const bat_to_player   = new Int16Array(nBatters).fill(-1);
const bowl_to_player  = new Int16Array(nBowlers).fill(-1);
const field_to_player = new Int16Array(nFielders).fill(-1);
for (let pi = 0; pi < nPlayers; pi++) {
  const bi = player_bat_idx[pi];  if (bi >= 0) bat_to_player[bi]   = pi;
  const wi = player_bowl_idx[pi]; if (wi >= 0) bowl_to_player[wi]  = pi;
  const fi = player_field_idx[pi];if (fi >= 0) field_to_player[fi] = pi;
}

/* goToPlayer — set by the player-profile IIFE once it initialises */
let goToPlayer = null;

/* ---- Team logo map — injected at build time by build_dashboard.py ---- */
/* TEAM_LOGOS_EMBEDDED is defined in the preceding <script> block;         */
/* it contains either base64 data URIs (if download_assets.py was run) or  */
/* Wikipedia fallback URLs. Reference it via the alias below.              */
const TEAM_LOGOS = TEAM_LOGOS_EMBEDDED;
const TEAM_COLORS = {
  'Chennai Super Kings':'#F5A623','Mumbai Indians':'#004BA0',
  'Royal Challengers Bengaluru':'#CC0000','Kolkata Knight Riders':'#3A1F6E',
  'Sunrisers Hyderabad':'#F7813A','Delhi Capitals':'#0057A8',
  'Punjab Kings':'#ED1B2F','Rajasthan Royals':'#254AA5',
  'Gujarat Titans':'#1C2951','Lucknow Super Giants':'#2B5DB5',
  'Deccan Chargers':'#00529B','Rising Pune Supergiants':'#6F006F',
  'Gujarat Lions':'#E8611B','Kochi Tuskers Kerala':'#BF0000',
  'Pune Warriors':'#1B3D6E',
};
function teamInitials(name) {
  return name.split(' ').filter(w=>/^[A-Z]/.test(w)).map(w=>w[0]).slice(0,3).join('');
}
function logoError(img) {
  const wrap = img.parentNode;
  const sz   = parseInt(wrap.style.width) || 40;
  const fs   = Math.max(8, Math.round(sz * 0.28));
  const name = img.alt;
  const color = TEAM_COLORS[name] || '#555';
  const ini   = teamInitials(name);
  wrap.innerHTML = `<span class="team-logo-fallback" style="width:${sz}px;height:${sz}px;background:${color};font-size:${fs}px">${ini}</span>`;
}
function teamLogoHtml(teamName, sizePx) {
  const url   = TEAM_LOGOS[teamName];
  const color = TEAM_COLORS[teamName] || '#555';
  const ini   = teamInitials(teamName);
  const sz    = sizePx || 40;
  const fs    = Math.max(8, Math.round(sz * 0.28));
  if (url) {
    return `<span class="team-logo-wrap" style="width:${sz}px;height:${sz}px">` +
      `<img src="${url}" alt="${escapeHtml(teamName)}" loading="lazy" onerror="logoError(this)">` +
      `</span>`;
  }
  return `<span class="team-logo-fallback" style="width:${sz}px;height:${sz}px;background:${color};font-size:${fs}px">${ini}</span>`;
}

/* ------------------------------------------------------------------ */
/*  Shared state                                                        */
/* ------------------------------------------------------------------ */
const shared = {
  selectedSeasons:  new Set(),
  innings: 'all',
  overMin: 1, overMax: 20,
  selectedVenue: new Set(),
};

const batState = {
  minBalls: 100,
  selectedOpposition: new Set(),   // bowl_team
  selectedBatTeam:    new Set(),
  selectedBowler:     new Set(),
  sortColumn: 'runs', sortDesc: true,
};

const bowlState = {
  minBalls: 120,
  selectedOpposition: new Set(),   // bat_team
  selectedBowlTeam:   new Set(),
  selectedBatter:     new Set(),
  sortColumn: 'wickets', sortDesc: true,
};


const teamState = {
  selectedTeam:    -1,
  selectedSeasons: new Set(),
  stageFilter:     'all',
  tossFilter:      'all',
  inningsFilter:   'all',
  selectedOpponent:-1,
  activeSubtab:    'season',
  contribMode:     'wins',
  contribMinBalls: 1,
  seasonSort:      {col:'season', desc:false},
  contribBatSort:  {col:'r',      desc:true},
  contribBowlSort: {col:'w',      desc:true},
};

const fieldState = {
  selectedSeasons:  new Set(),
  typeFilter:       'all',        // 'all','0','1','2'
  selectedTeam:     new Set(),    // fielding team
  selectedOpp:      new Set(),    // batting team
  minDismissals:    5,
  sortColumn:       'total',
  sortDesc:         true,
};
let fieldSearch = '';

let activeTab = 'batting';
let playerSearch = '';

/* ------------------------------------------------------------------ */
/*  Helpers                                                             */
/* ------------------------------------------------------------------ */
function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g,
    c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function fmt(v, d) { return v == null ? '&mdash;' : v.toFixed(d); }
function fmtOvers(lb) {
  if (!lb) return '0.0';
  return Math.floor(lb / 6) + '.' + (lb % 6);
}

/* ------------------------------------------------------------------ */
/*  Subtitle                                                            */
/* ------------------------------------------------------------------ */
const subtitleEl = document.getElementById('subtitle');
function updateSubtitle() {
  subtitleEl.textContent = activeTab === 'batting'
    ? 'Rank batters across any combination of seasons, oppositions, overs, venues, and more'
    : activeTab === 'bowling'
    ? 'Rank bowlers across any combination of seasons, oppositions, overs, venues, and more'
    : activeTab === 'fielding'
    ? 'Rank fielders by catches, run-outs, and stumpings across seasons and oppositions'
    : activeTab === 'player'
    ? 'Full career profile — batting, bowling, fielding and season-by-season breakdown'
    : 'Explore team performance across seasons, head-to-head, toss, and innings';
}
updateSubtitle();

/* ------------------------------------------------------------------ */
/*  Tab switching                                                       */
/* ------------------------------------------------------------------ */
const tabBar = document.getElementById('tab-bar');
const batFilters  = document.getElementById('bat-filters');
const bowlFilters = document.getElementById('bowl-filters');
const inn1Btn = document.getElementById('inn-btn-1');
const inn2Btn = document.getElementById('inn-btn-2');

const teamsSection   = document.getElementById('teams-section');
const sharedFilters  = document.getElementById('shared-filters');
const mainResults    = document.getElementById('main-results');
const fieldSection   = document.getElementById('field-section');
const playerSection  = document.getElementById('player-section');
const batbowlEls     = [sharedFilters, batFilters, bowlFilters, mainResults];

/* Delegated click handler: player-link in batting/bowling tables */
mainResults.addEventListener('click', e => {
  const span = e.target.closest('.player-link');
  if (!span) return;
  const pi = +span.dataset.pi;
  if (goToPlayer) goToPlayer(pi);
});

/* Delegated click handler: player-link in fielding table */
fieldSection.addEventListener('click', e => {
  const span = e.target.closest('.player-link');
  if (!span) return;
  const pi = +span.dataset.pi;
  if (goToPlayer) goToPlayer(pi);
});

tabBar.querySelectorAll('.tab-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    if (btn.dataset.tab === activeTab) return;
    activeTab = btn.dataset.tab;
    tabBar.querySelectorAll('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));

    const isTeams    = (activeTab === 'teams');
    const isFielding = (activeTab === 'fielding');
    const isPlayer   = (activeTab === 'player');
    teamsSection.style.display  = isTeams    ? '' : 'none';
    fieldSection.style.display  = isFielding ? '' : 'none';
    playerSection.style.display = isPlayer   ? '' : 'none';
    batbowlEls.forEach(el => { el.style.display = (isTeams || isFielding || isPlayer) ? 'none' : ''; });

    if (!isTeams && !isFielding && !isPlayer) {
      if (activeTab === 'batting') {
        batFilters.style.display  = '';
        bowlFilters.style.display = 'none';
        inn1Btn.textContent = 'Batting 1st';
        inn2Btn.textContent = 'Chasing';
      } else {
        batFilters.style.display  = 'none';
        bowlFilters.style.display = '';
        inn1Btn.textContent = 'Bowling 1st';
        inn2Btn.textContent = 'Bowling 2nd';
      }
    }
    updateSubtitle();
    recompute();
  });
});

/* ------------------------------------------------------------------ */
/*  Season chips                                                        */
/* ------------------------------------------------------------------ */
const seasonsChips = document.getElementById('seasons-chips');
seasons.forEach((s, idx) => {
  const c = document.createElement('button');
  c.className = 'chip'; c.textContent = s; c.dataset.idx = idx; c.type = 'button';
  c.addEventListener('click', () => {
    if (shared.selectedSeasons.has(idx)) shared.selectedSeasons.delete(idx);
    else shared.selectedSeasons.add(idx);
    c.classList.toggle('active');
    recompute();
  });
  seasonsChips.appendChild(c);
});

/* ------------------------------------------------------------------ */
/*  Innings toggle                                                       */
/* ------------------------------------------------------------------ */
const inningsGroup = document.getElementById('innings-toggle');
inningsGroup.querySelectorAll('button').forEach(b => {
  b.addEventListener('click', () => {
    inningsGroup.querySelectorAll('button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    shared.innings = b.dataset.value;
    recompute();
  });
});

/* ------------------------------------------------------------------ */
/*  Overs                                                               */
/* ------------------------------------------------------------------ */
const overPresets  = document.getElementById('over-presets');
const overMinInput = document.getElementById('over-min');
const overMaxInput = document.getElementById('over-max');

overPresets.querySelectorAll('button').forEach(b => {
  b.addEventListener('click', () => {
    overPresets.querySelectorAll('button').forEach(x => x.classList.remove('active'));
    b.classList.add('active');
    shared.overMin = +b.dataset.min;
    shared.overMax = +b.dataset.max;
    overMinInput.value = shared.overMin;
    overMaxInput.value = shared.overMax;
    recompute();
  });
});
function clearOverPresets() {
  overPresets.querySelectorAll('button').forEach(x => x.classList.remove('active'));
}
overMinInput.addEventListener('input', () => {
  const v = +overMinInput.value;
  shared.overMin = (!isFinite(v) || v < 1) ? 1 : (v > 20 ? 20 : Math.floor(v));
  clearOverPresets(); recompute();
});
overMaxInput.addEventListener('input', () => {
  const v = +overMaxInput.value;
  shared.overMax = (!isFinite(v) || v < 1) ? 1 : (v > 20 ? 20 : Math.floor(v));
  clearOverPresets(); recompute();
});

/* ------------------------------------------------------------------ */
/*  Player search                                                       */
/* ------------------------------------------------------------------ */
const playerSearchInput = document.getElementById('player-search');
playerSearchInput.addEventListener('input', () => {
  playerSearch = playerSearchInput.value.trim().toLowerCase();
  recompute();
});

/* ------------------------------------------------------------------ */
/*  Close dropdowns on outside click                                    */
/* ------------------------------------------------------------------ */
document.addEventListener('click', () => {
  document.querySelectorAll('.dropdown.open').forEach(d => d.classList.remove('open'));
});

/* ------------------------------------------------------------------ */
/*  Dropdown builder                                                    */
/* ------------------------------------------------------------------ */
function buildDropdown(host, items, set, placeholder, hasSearch) {
  host.classList.add('dropdown');
  const toggle = document.createElement('button');
  toggle.className = 'dropdown-toggle'; toggle.type = 'button';
  toggle.innerHTML = '<span class="toggle-label"></span><span class="arrow">&#9662;</span>';
  host.appendChild(toggle);
  const labelEl = toggle.querySelector('.toggle-label');

  const menu = document.createElement('div');
  menu.className = 'dropdown-menu';

  if (hasSearch) {
    const s = document.createElement('div');
    s.className = 'dropdown-search';
    const inp = document.createElement('input');
    inp.type = 'text'; inp.placeholder = 'Search…';
    s.appendChild(inp);
    menu.appendChild(s);
    inp.addEventListener('input', () => {
      const q = inp.value.toLowerCase().trim();
      let visible = 0;
      menu.querySelectorAll('.dropdown-item').forEach(it => {
        const show = !q || it.dataset.label.toLowerCase().includes(q);
        it.style.display = show ? '' : 'none';
        if (show) visible++;
      });
      emptyEl.style.display = visible ? 'none' : '';
    });
    s.addEventListener('click', e => e.stopPropagation());
  }

  const list = document.createElement('div');
  list.className = 'dropdown-list';
  items.forEach(it => {
    const row = document.createElement('label');
    row.className = 'dropdown-item';
    row.dataset.label = it.label;
    const cb = document.createElement('input');
    cb.type = 'checkbox'; cb.dataset.idx = it.idx;
    const sp = document.createElement('span'); sp.textContent = it.label;
    row.appendChild(cb); row.appendChild(sp);
    list.appendChild(row);
    cb.addEventListener('change', () => {
      if (cb.checked) set.add(+cb.dataset.idx); else set.delete(+cb.dataset.idx);
      updateLabel(); recompute();
    });
  });
  menu.appendChild(list);
  const emptyEl = document.createElement('div');
  emptyEl.className = 'dropdown-empty'; emptyEl.textContent = 'No matches';
  emptyEl.style.display = 'none';
  menu.appendChild(emptyEl);
  host.appendChild(menu);

  function updateLabel() {
    if (set.size === 0) {
      labelEl.textContent = placeholder; labelEl.style.color = 'var(--text-muted)';
    } else if (set.size === 1) {
      const idx = set.values().next().value;
      const item = items.find(i => i.idx === idx);
      labelEl.textContent = item ? item.label : placeholder; labelEl.style.color = '';
    } else {
      labelEl.textContent = set.size + ' selected'; labelEl.style.color = '';
    }
  }
  updateLabel();

  toggle.addEventListener('click', e => {
    e.stopPropagation();
    const wasOpen = host.classList.contains('open');
    document.querySelectorAll('.dropdown.open').forEach(d => d.classList.remove('open'));
    if (!wasOpen) host.classList.add('open');
  });

  return {
    reset() {
      set.clear();
      list.querySelectorAll('input[type=checkbox]').forEach(c => c.checked = false);
      if (hasSearch) {
        menu.querySelector('input[type=text]').value = '';
        menu.querySelectorAll('.dropdown-item').forEach(it => it.style.display = '');
        emptyEl.style.display = 'none';
      }
      updateLabel();
    }
  };
}

/* ------------------------------------------------------------------ */
/*  Build dropdown items                                                */
/* ------------------------------------------------------------------ */
const teamItems   = teams.map((t, i) => ({label: t, idx: i})).sort((a,b) => a.label.localeCompare(b.label));
const venueItems  = venues.map((v, i) => ({label: v, idx: i})).sort((a,b) => a.label.localeCompare(b.label));
const bowlerItems = bowlers.map((b, i) => ({label: b, idx: i})).sort((a,b) => a.label.localeCompare(b.label));
const batterItems = batters.map((b, i) => ({label: b, idx: i})).sort((a,b) => a.label.localeCompare(b.label));

/* ---- Shared: Venue ---- */
const ddVen = buildDropdown(
  document.querySelector('.dropdown[data-key="venue"]'),
  venueItems, shared.selectedVenue, 'All venues', true);

/* ---- Batting-specific ---- */
const minBallsInput = document.getElementById('min-balls');
minBallsInput.addEventListener('input', () => {
  batState.minBalls = Math.max(0, Math.floor(+minBallsInput.value) || 0);
  recompute();
});

const ddOpp  = buildDropdown(document.querySelector('.dropdown[data-key="opposition"]'),
  teamItems, batState.selectedOpposition, 'All oppositions', false);
const ddBat  = buildDropdown(document.querySelector('.dropdown[data-key="bat_team"]'),
  teamItems, batState.selectedBatTeam, 'All teams', false);
const ddBowl = buildDropdown(document.querySelector('.dropdown[data-key="bowler"]'),
  bowlerItems, batState.selectedBowler, 'All bowlers', true);

/* ---- Bowling-specific ---- */
const minBallsBowlInput = document.getElementById('min-balls-bowl');
minBallsBowlInput.addEventListener('input', () => {
  bowlState.minBalls = Math.max(0, Math.floor(+minBallsBowlInput.value) || 0);
  recompute();
});

const ddBowlOpp  = buildDropdown(document.querySelector('.dropdown[data-key="bowl_opposition"]'),
  teamItems, bowlState.selectedOpposition, 'All oppositions', false);
const ddBowlTeam = buildDropdown(document.querySelector('.dropdown[data-key="bowl_team"]'),
  teamItems, bowlState.selectedBowlTeam, 'All teams', false);
const ddBatter   = buildDropdown(document.querySelector('.dropdown[data-key="batter_filter"]'),
  batterItems, bowlState.selectedBatter, 'All batters', true);

/* ---- Fielding-specific dropdowns ---- */
let ddFieldTeam = null, ddFieldOpp = null;
const ftEl = document.querySelector('.dropdown[data-key="field_team"]');
const foEl = document.querySelector('.dropdown[data-key="field_opp"]');
if (ftEl) ddFieldTeam = buildDropdown(ftEl, teamItems, fieldState.selectedTeam, 'All teams', false);
if (foEl) ddFieldOpp  = buildDropdown(foEl, teamItems, fieldState.selectedOpp,  'All oppositions', false);

/* ------------------------------------------------------------------ */
/*  Reset button                                                        */
/* ------------------------------------------------------------------ */
document.getElementById('reset-button').addEventListener('click', () => {
  // Shared
  shared.selectedSeasons.clear();
  shared.innings = 'all';
  shared.overMin = 1; shared.overMax = 20;
  shared.selectedVenue.clear();
  seasonsChips.querySelectorAll('.chip').forEach(c => c.classList.remove('active'));
  inningsGroup.querySelectorAll('button').forEach(b =>
    b.classList.toggle('active', b.dataset.value === 'all'));
  overPresets.querySelectorAll('button').forEach(b =>
    b.classList.toggle('active', b.dataset.min === '1' && b.dataset.max === '20'));
  overMinInput.value = 1; overMaxInput.value = 20;
  ddVen.reset();

  // Batting
  batState.minBalls = 100; batState.sortColumn = 'runs'; batState.sortDesc = true;
  batState.selectedOpposition.clear(); batState.selectedBatTeam.clear(); batState.selectedBowler.clear();
  minBallsInput.value = 100;
  ddOpp.reset(); ddBat.reset(); ddBowl.reset();

  // Bowling
  bowlState.minBalls = 120; bowlState.sortColumn = 'wickets'; bowlState.sortDesc = true;
  bowlState.selectedOpposition.clear(); bowlState.selectedBowlTeam.clear(); bowlState.selectedBatter.clear();
  minBallsBowlInput.value = 120;
  ddBowlOpp.reset(); ddBowlTeam.reset(); ddBatter.reset();

  // Player search
  playerSearch = '';
  playerSearchInput.value = '';

  // Teams tab reset
  teamState.selectedTeam = -1;
  teamState.selectedSeasons.clear();
  teamState.stageFilter = 'all';
  teamState.tossFilter = 'all';
  teamState.inningsFilter = 'all';
  teamState.selectedOpponent = -1;
  teamState.activeSubtab = 'season';
  teamState.contribMode = 'wins';
  teamState.contribMinBalls = 1;
  teamState.seasonSort     = {col:'season', desc:false};
  teamState.contribBatSort  = {col:'r', desc:true};
  teamState.contribBowlSort = {col:'w', desc:true};
  // Clear contrib controls so they re-render with reset values
  const teamsResultsEl = document.getElementById('teams-results');
  if (teamsResultsEl) teamsResultsEl.innerHTML = '';

  // Fielding reset
  fieldState.selectedSeasons.clear();
  fieldState.typeFilter = 'all';
  fieldState.selectedTeam.clear();
  fieldState.selectedOpp.clear();
  fieldState.minDismissals = 5;
  fieldState.sortColumn = 'total'; fieldState.sortDesc = true;
  fieldSearch = '';
  const fsi = document.getElementById('field-search');
  if (fsi) fsi.value = '';
  const mdi = document.getElementById('min-dismissals');
  if (mdi) mdi.value = 5;
  document.querySelectorAll('#field-seasons-chips .chip').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('#field-type-toggle button').forEach(b =>
    b.classList.toggle('active', b.dataset.value === 'all'));
  if (ddFieldTeam) ddFieldTeam.reset();
  if (ddFieldOpp)  ddFieldOpp.reset();

  const tp = document.getElementById('team-picker');
  if (tp) tp.value = '-1';
  const to = document.getElementById('team-opponent');
  if (to) to.value = '-1';
  document.querySelectorAll('#team-seasons-chips .chip').forEach(c => c.classList.remove('active'));
  document.querySelectorAll('#team-stage-toggle button').forEach(b =>
    b.classList.toggle('active', b.dataset.value === 'all'));
  document.querySelectorAll('#team-toss-toggle button').forEach(b =>
    b.classList.toggle('active', b.dataset.value === 'all'));
  document.querySelectorAll('#team-innings-toggle button').forEach(b =>
    b.classList.toggle('active', b.dataset.value === 'all'));
  document.querySelectorAll('#subtab-bar .subtab-btn').forEach(b =>
    b.classList.toggle('active', b.dataset.subtab === 'season'));

  recompute();
});

/* ------------------------------------------------------------------ */
/*  Debounced recompute                                                 */
/* ------------------------------------------------------------------ */
let pending = false;
function recompute() {
  if (pending) return;
  pending = true;
  requestAnimationFrame(() => { pending = false; doCompute(); });
}

/* ------------------------------------------------------------------ */
/*  Main compute dispatcher                                             */
/* ------------------------------------------------------------------ */
function doCompute() {
  if      (activeTab === 'batting')  doComputeBatting();
  else if (activeTab === 'bowling')  doComputeBowling();
  else if (activeTab === 'fielding') doComputeFielding();
  else if (activeTab === 'teams')    doComputeTeams();
  // player tab has its own render path — nothing to do here
}

/* ------------------------------------------------------------------ */
/*  BATTING compute                                                     */
/* ------------------------------------------------------------------ */
function doComputeBatting() {
  const t0 = performance.now();
  const oMin = Math.min(shared.overMin, shared.overMax) - 1;
  const oMax = Math.max(shared.overMin, shared.overMax) - 1;
  const inn  = shared.innings;
  const sM   = shared.selectedSeasons.size  ? shared.selectedSeasons  : null;
  const vM   = shared.selectedVenue.size    ? shared.selectedVenue    : null;
  const oM   = batState.selectedOpposition.size ? batState.selectedOpposition : null;
  const btM  = batState.selectedBatTeam.size    ? batState.selectedBatTeam    : null;
  const bwM  = batState.selectedBowler.size     ? batState.selectedBowler     : null;

  const runs  = new Int32Array(nBatters);
  const balls = new Int32Array(nBatters);
  const outs  = new Int32Array(nBatters);

  for (let i = 0; i < N; i++) {
    const ov = e_over[i];
    if (ov < oMin || ov > oMax) continue;
    if (inn === '1' && e_innings[i] !== 1) continue;
    if (inn === '2' && e_innings[i] !== 2) continue;
    if (sM  && !sM.has(e_season[i]))    continue;
    if (vM  && !vM.has(e_venue[i]))     continue;
    if (oM  && !oM.has(e_bowl_team[i])) continue;
    if (btM && !btM.has(e_bat_team[i])) continue;
    if (bwM && !bwM.has(e_bowler[i]))   continue;
    const b = e_batter[i];
    runs[b]  += e_runs[i];
    balls[b] += e_ball_faced[i];
    outs[b]  += e_dismissed[i];
  }

  const minB = batState.minBalls;
  const rows = [];
  for (let b = 0; b < nBatters; b++) {
    if (balls[b] < minB) continue;
    if (balls[b] === 0 && runs[b] === 0) continue;
    rows.push({
      player: batters[b], bidx: b,
      runs:   runs[b],
      balls:  balls[b],
      outs:   outs[b],
      sr:  balls[b] > 0 ? (runs[b] / balls[b]) * 100 : null,
      avg: outs[b]  > 0 ? runs[b] / outs[b]          : null,
    });
  }

  rows.sort((a, b) => sortRows(a, b, batState));
  document.getElementById('results-meta').textContent =
    (performance.now() - t0).toFixed(0) + ' ms';
  renderBattingTable(rows, playerSearch);
}

/* ------------------------------------------------------------------ */
/*  BOWLING compute                                                     */
/* ------------------------------------------------------------------ */
function doComputeBowling() {
  const t0 = performance.now();
  const oMin = Math.min(shared.overMin, shared.overMax) - 1;
  const oMax = Math.max(shared.overMin, shared.overMax) - 1;
  const inn  = shared.innings;
  const sM   = shared.selectedSeasons.size      ? shared.selectedSeasons      : null;
  const vM   = shared.selectedVenue.size        ? shared.selectedVenue        : null;
  const oM   = bowlState.selectedOpposition.size  ? bowlState.selectedOpposition  : null; // bat_team
  const btM  = bowlState.selectedBowlTeam.size    ? bowlState.selectedBowlTeam    : null; // bowl_team
  const baM  = bowlState.selectedBatter.size      ? bowlState.selectedBatter      : null; // batter

  const runs    = new Int32Array(nBowlers);
  const lballs  = new Int32Array(nBowlers);  // legal balls (not wides)
  const wickets = new Int32Array(nBowlers);
  const dots    = new Int32Array(nBowlers);
  const wides   = new Int32Array(nBowlers);
  const noballs = new Int32Array(nBowlers);

  // For distinct match counting, use one Set per bowler (created lazily)
  const matchSets = new Array(nBowlers).fill(null);

  for (let i = 0; i < N; i++) {
    const ov = e_over[i];
    if (ov < oMin || ov > oMax) continue;
    if (inn === '1' && e_innings[i] !== 1) continue;
    if (inn === '2' && e_innings[i] !== 2) continue;
    if (sM  && !sM.has(e_season[i]))    continue;
    if (vM  && !vM.has(e_venue[i]))     continue;
    if (oM  && !oM.has(e_bat_team[i]))  continue;
    if (btM && !btM.has(e_bowl_team[i]))continue;
    if (baM && !baM.has(e_batter[i]))   continue;

    const bw = e_bowler[i];
    const isLegal = e_ball_faced[i];  // 1 = not wide

    runs[bw]    += e_bowl_runs[i];
    lballs[bw]  += isLegal;
    wickets[bw] += e_bowl_wicket[i];
    wides[bw]   += (1 - e_ball_faced[i]);  // wide = ball_faced is 0
    noballs[bw] += e_is_noball[i];
    if (isLegal && e_bowl_runs[i] === 0) dots[bw]++;

    if (!matchSets[bw]) matchSets[bw] = new Set();
    matchSets[bw].add(e_match[i]);
  }



  const minB = bowlState.minBalls;
  const rows = [];
  for (let b = 0; b < nBowlers; b++) {
    if (lballs[b] < minB) continue;
    if (lballs[b] === 0) continue;
    const lb = lballs[b];
    const r  = runs[b];
    const w  = wickets[b];
    const eco = lb > 0 ? (r / lb) * 6 : null;
    const avg = w  > 0 ? r / w        : null;
    const sr  = w  > 0 ? lb / w       : null;
    const dotPct = lb > 0 ? (dots[b] / lb) * 100 : null;
    const m = matchSets[b] ? matchSets[b].size : 0;
    rows.push({
      player: bowlers[b], widx: b,
      matches: m,
      lballs: lb,
      runs: r,
      wickets: w,
      eco, avg, sr, dotPct,
      wides: wides[b],
      noballs: noballs[b],
    });
  }

  rows.sort((a, b) => sortRows(a, b, bowlState));
  document.getElementById('results-meta').textContent =
    (performance.now() - t0).toFixed(0) + ' ms';
  renderBowlingTable(rows, playerSearch);
}

/* ------------------------------------------------------------------ */
/*  Generic sort                                                        */
/* ------------------------------------------------------------------ */
function sortRows(a, b, st) {
  const k = st.sortColumn;
  let va = a[k], vb = b[k];
  if (typeof va === 'string') {
    const cmp = va.localeCompare(vb);
    return st.sortDesc ? -cmp : cmp;
  }
  if (va == null && vb == null) return 0;
  if (va == null) return 1;
  if (vb == null) return -1;
  return st.sortDesc ? vb - va : va - vb;
}

/* ------------------------------------------------------------------ */
/*  Render: Batting table                                               */
/* ------------------------------------------------------------------ */
function renderBattingTable(rows, search) {
  const all = rows.length;
  const visible = search ? rows.filter(r => r.player.toLowerCase().includes(search)) : rows;
  const countEl = document.getElementById('results-count');
  countEl.innerHTML = search
    ? `<strong>${visible.length.toLocaleString()}</strong> of ${all.toLocaleString()} player${all !== 1 ? 's' : ''} match these filters`
    : `<strong>${all.toLocaleString()}</strong> player${all !== 1 ? 's' : ''} match these filters`;

  const wrap = document.getElementById('table-wrap');
  if (visible.length === 0) {
    wrap.innerHTML = all === 0
      ? '<div class="empty">No players match these filters. Try loosening them or lowering the minimum balls threshold.</div>'
      : `<div class="empty">No player named &ldquo;${escapeHtml(search)}&rdquo; in these results.</div>`;
    setFootnote('batting');
    return;
  }
  const rows2 = visible;

  const cols = [
    {key: 'player', label: 'Batter',  numeric: false},
    {key: 'runs',   label: 'Runs',    numeric: true},
    {key: 'balls',  label: 'Balls',   numeric: true},
    {key: 'outs',   label: 'Outs',    numeric: true},
    {key: 'sr',     label: 'SR',      numeric: true, digits: 1, title: 'Strike Rate = runs ÷ balls × 100'},
    {key: 'avg',    label: 'Avg',     numeric: true, digits: 1, title: 'Average = runs ÷ dismissals'},
  ];

  let html = buildTableHeader(cols, batState);
  const cap = Math.min(rows2.length, 500);
  for (let i = 0; i < cap; i++) {
    const r = rows2[i];
    const pi = bat_to_player[r.bidx];
    html += `<tr>
      <td class="rank">${i + 1}</td>
      <td class="player"><span class="player-link" data-pi="${pi}">${escapeHtml(r.player)}</span></td>
      <td class="numeric">${r.runs.toLocaleString()}</td>
      <td class="numeric">${r.balls.toLocaleString()}</td>
      <td class="numeric">${r.outs.toLocaleString()}</td>
      <td class="numeric">${fmt(r.sr, 1)}</td>
      <td class="numeric">${fmt(r.avg, 1)}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  if (rows2.length > cap) html += overflowMsg(cap, rows2.length);

  wrap.innerHTML = html;
  attachSortListeners(wrap, batState);
  setFootnote('batting');
}

/* ------------------------------------------------------------------ */
/*  Render: Bowling table                                               */
/* ------------------------------------------------------------------ */
function renderBowlingTable(rows, search) {
  const all = rows.length;
  const visible = search ? rows.filter(r => r.player.toLowerCase().includes(search)) : rows;
  const countEl = document.getElementById('results-count');
  countEl.innerHTML = search
    ? `<strong>${visible.length.toLocaleString()}</strong> of ${all.toLocaleString()} bowler${all !== 1 ? 's' : ''} match these filters`
    : `<strong>${all.toLocaleString()}</strong> bowler${all !== 1 ? 's' : ''} match these filters`;

  const wrap = document.getElementById('table-wrap');
  if (visible.length === 0) {
    wrap.innerHTML = all === 0
      ? '<div class="empty">No bowlers match these filters. Try loosening them or lowering the minimum balls threshold.</div>'
      : `<div class="empty">No bowler named &ldquo;${escapeHtml(search)}&rdquo; in these results.</div>`;
    setFootnote('bowling');
    return;
  }
  const rows2 = visible;

  const cols = [
    {key: 'player',  label: 'Bowler',  numeric: false},
    {key: 'matches', label: 'M',       numeric: true,  title: 'Matches played'},
    {key: 'lballs',  label: 'Balls',   numeric: true,  title: 'Legal balls bowled (wides excluded)'},
    {key: 'runs',    label: 'Runs',    numeric: true,  title: 'Runs conceded'},
    {key: 'wickets', label: 'Wkts',    numeric: true,  title: 'Wickets taken (bowler wickets only; run-outs excluded)'},
    {key: 'eco',     label: 'Eco',     numeric: true,  digits: 2, title: 'Economy = runs ÷ overs'},
    {key: 'avg',     label: 'Avg',     numeric: true,  digits: 1, title: 'Bowling Average = runs ÷ wickets'},
    {key: 'sr',      label: 'SR',      numeric: true,  digits: 1, title: 'Strike Rate = balls ÷ wickets (lower is better)'},
    {key: 'dotPct',  label: 'Dot%',    numeric: true,  digits: 1, title: 'Dot ball % = dot balls ÷ legal balls × 100'},
    {key: 'wides',   label: 'Wd',      numeric: true,  title: 'Wide deliveries bowled'},
    {key: 'noballs', label: 'NB',      numeric: true,  title: 'No-balls bowled'},
  ];

  let html = buildTableHeader(cols, bowlState);
  const cap = Math.min(rows2.length, 500);
  for (let i = 0; i < cap; i++) {
    const r = rows2[i];
    const pi = bowl_to_player[r.widx];
    const overs = fmtOvers(r.lballs);
    html += `<tr>
      <td class="rank">${i + 1}</td>
      <td class="player"><span class="player-link" data-pi="${pi}">${escapeHtml(r.player)}</span></td>
      <td class="numeric">${r.matches}</td>
      <td class="numeric">${overs}</td>
      <td class="numeric">${r.runs.toLocaleString()}</td>
      <td class="numeric">${r.wickets}</td>
      <td class="numeric">${fmt(r.eco, 2)}</td>
      <td class="numeric">${fmt(r.avg, 1)}</td>
      <td class="numeric">${r.wickets > 0 ? fmt(r.sr, 1) : '&mdash;'}</td>
      <td class="numeric">${fmt(r.dotPct, 1)}</td>
      <td class="numeric">${r.wides}</td>
      <td class="numeric">${r.noballs}</td>
    </tr>`;
  }
  html += '</tbody></table>';
  if (rows2.length > cap) html += overflowMsg(cap, rows2.length);

  wrap.innerHTML = html;
  attachSortListeners(wrap, bowlState);
  setFootnote('bowling');
}

/* ------------------------------------------------------------------ */
/*  Table header builder                                                */
/* ------------------------------------------------------------------ */
function buildTableHeader(cols, st) {
  let html = '<table><thead><tr><th class="numeric" data-static>#</th>';
  for (const c of cols) {
    const isSorted = st.sortColumn === c.key;
    const arrow = isSorted ? (st.sortDesc ? '↓' : '↑') : '↕';
    const titleAttr = c.title ? ` title="${escapeHtml(c.title)}"` : '';
    html += `<th class="${c.numeric ? 'numeric ' : ''}${isSorted ? 'sorted' : ''}"
      data-key="${c.key}"${titleAttr}>${c.label}<span class="sort-arrow">${arrow}</span></th>`;
  }
  html += '</tr></thead><tbody>';
  return html;
}

/* ------------------------------------------------------------------ */
/*  Sort listener attachment                                            */
/* ------------------------------------------------------------------ */
function attachSortListeners(wrap, st) {
  wrap.querySelectorAll('thead th[data-key]').forEach(th => {
    th.addEventListener('click', () => {
      const k = th.dataset.key;
      if (st.sortColumn === k) st.sortDesc = !st.sortDesc;
      else { st.sortColumn = k; st.sortDesc = (k !== 'player'); }
      recompute();
    });
  });
}

/* ------------------------------------------------------------------ */
/*  Overflow message                                                    */
/* ------------------------------------------------------------------ */
function overflowMsg(cap, total) {
  return `<div class="empty" style="border-top:1px solid var(--border);padding:.75rem;text-align:center">
    Showing top ${cap} of ${total.toLocaleString()} — tighten filters or raise the minimum balls threshold to narrow further.
  </div>`;
}

/* ------------------------------------------------------------------ */
/*  Footnote                                                            */
/* ------------------------------------------------------------------ */
function setFootnote(tab) {
  const el = document.getElementById('footnote');
  if (tab === 'batting') {
    el.innerHTML = 'SR = runs &divide; balls &times; 100. Avg = runs &divide; dismissals (&mdash; if undismissed). Wides excluded from balls faced. Super overs excluded.';
  } else {
    el.innerHTML = 'Balls = legal deliveries (wides excluded). Eco = runs &divide; overs. Avg = runs &divide; wickets. SR = balls &divide; wickets. Dot% = dot balls &divide; legal balls &times; 100. ' +
      'Run-outs are not credited to the bowler. Super overs excluded. ' +
      '<strong>Note:</strong> Ball speed data is not available in Cricsheet — fastest/slowest ball stats cannot be shown.';
  }
}


/* ================================================================== */
/*  TEAMS TAB                                                          */
/* ================================================================== */

/* ---- Build team picker UI ---- */
(function() {
  const picker   = document.getElementById('team-picker');
  const oppPicker= document.getElementById('team-opponent');
  const sorted   = teams.map((t,i) => ({label:t,idx:i}))
                        .sort((a,b) => a.label.localeCompare(b.label));

  sorted.forEach(t => {
    const o1 = document.createElement('option');
    o1.value = t.idx; o1.textContent = t.label;
    picker.appendChild(o1);
    const o2 = document.createElement('option');
    o2.value = t.idx; o2.textContent = t.label;
    oppPicker.appendChild(o2);
  });

  const teamLogoPreview = document.getElementById('team-logo-preview');
  picker.addEventListener('change', () => {
    teamState.selectedTeam = +picker.value;
    if (teamState.selectedTeam >= 0) {
      teamLogoPreview.innerHTML = teamLogoHtml(teams[teamState.selectedTeam], 36);
      teamLogoPreview.style.display = '';
    } else {
      teamLogoPreview.style.display = 'none';
    }
    recompute();
  });
  oppPicker.addEventListener('change', () => {
    teamState.selectedOpponent = +oppPicker.value;
    recompute();
  });

  // Season chips for teams tab
  const chipsEl = document.getElementById('team-seasons-chips');
  seasons.forEach((s,idx) => {
    const c = document.createElement('button');
    c.className='chip'; c.textContent=s; c.dataset.idx=idx; c.type='button';
    c.addEventListener('click', () => {
      if (teamState.selectedSeasons.has(idx)) teamState.selectedSeasons.delete(idx);
      else teamState.selectedSeasons.add(idx);
      c.classList.toggle('active');
      recompute();
    });
    chipsEl.appendChild(c);
  });

  // Stage toggle
  document.getElementById('team-stage-toggle').querySelectorAll('button').forEach(b => {
    b.addEventListener('click', () => {
      document.getElementById('team-stage-toggle').querySelectorAll('button')
        .forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      teamState.stageFilter = b.dataset.value;
      recompute();
    });
  });

  // Toss toggle
  document.getElementById('team-toss-toggle').querySelectorAll('button').forEach(b => {
    b.addEventListener('click', () => {
      document.getElementById('team-toss-toggle').querySelectorAll('button')
        .forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      teamState.tossFilter = b.dataset.value;
      recompute();
    });
  });

  // Innings toggle
  document.getElementById('team-innings-toggle').querySelectorAll('button').forEach(b => {
    b.addEventListener('click', () => {
      document.getElementById('team-innings-toggle').querySelectorAll('button')
        .forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      teamState.inningsFilter = b.dataset.value;
      recompute();
    });
  });

  // Sub-tab buttons
  document.getElementById('subtab-bar').querySelectorAll('.subtab-btn').forEach(b => {
    b.addEventListener('click', () => {
      document.getElementById('subtab-bar').querySelectorAll('.subtab-btn')
        .forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      teamState.activeSubtab = b.dataset.subtab;
      recompute();
    });
  });
})();

/* ---- Filter matches for selected team ---- */
function getTeamMatches() {
  const sel = teamState.selectedTeam;
  if (sel < 0) return [];
  const result = [];
  for (let m = 0; m < nMatches; m++) {
    const t1 = m_team1_a[m], t2 = m_team2_a[m];
    if (t1 !== sel && t2 !== sel) continue;
    if (teamState.selectedSeasons.size > 0 &&
        !teamState.selectedSeasons.has(m_season_m[m])) continue;
    const stage = stages_list[m_stage[m]];
    const sf = teamState.stageFilter;
    if (sf === 'group'   && stage !== 'Group')   continue;
    if (sf === 'final'   && stage !== 'Final')   continue;
    if (sf === 'playoffs' && !PLAYOFF_STAGES.has(stage)) continue;
    // Toss filter
    if (teamState.tossFilter !== 'all') {
      const wonToss = m_toss_win[m] === sel;
      if (teamState.tossFilter === 'won' && !wonToss) continue;
      if (teamState.tossFilter === 'lost' &&  wonToss) continue;
    }

    // Innings filter
    if (teamState.inningsFilter !== 'all') {
      const wonToss = m_toss_win[m] === sel;
      const dec = m_toss_dec[m]; // 0 = toss-winner bats
      const selBatFirst = (wonToss && dec === 0) || (!wonToss && dec === 1);
      if (teamState.inningsFilter === 'bat1'  &&  !selBatFirst) continue;
      if (teamState.inningsFilter === 'chase' &&   selBatFirst) continue;
    }

    if (teamState.selectedOpponent >= 0) {
      const opp = (t1 === sel) ? t2 : t1;
      if (opp !== teamState.selectedOpponent) continue;
    }
    result.push(m);
  }
  return result;
}

/* ---- doComputeTeams dispatcher ---- */
function doComputeTeams() {
  if (teamState.selectedTeam < 0) {
    document.getElementById('kpi-strip').innerHTML =
      '<div class="kpi-empty">Select a team above to see their stats</div>';
    document.getElementById('teams-results').innerHTML =
      '<div class="team-placeholder"><strong>Pick a team to get started</strong>Select a team using the filter above.</div>';
    return;
  }
  const ml = getTeamMatches();
  renderTeamKpis(ml);
  const sub = teamState.activeSubtab;
  if (sub === 'season') renderTeamSeasons(ml);
  else                  renderTeamContributors(ml);
}

/* ---- KPI Strip ---- */
function renderTeamKpis(ml) {
  const sel = teamState.selectedTeam;
  let played=0, won=0, lost=0, tied=0, nr=0, rf=0, ra=0, sc=0;
  for (const m of ml) {
    if (m_no_result[m]) { nr++; continue; }
    played++;
    const isT1 = m_team1_a[m] === sel;
    const mt = isT1 ? m_t1_total[m] : m_t2_total[m];
    const ot = isT1 ? m_t2_total[m] : m_t1_total[m];
    if      (m_is_tie[m])           tied++;
    else if (m_winner[m] === sel)   won++;
    else if (m_winner[m] >= 0)      lost++;
    if (mt > 0) { rf += mt; ra += ot; sc++; }
  }
  const wp   = played > 0 ? (won/played*100).toFixed(1)+'%' : '—';
  const avgF = sc > 0 ? (rf/sc).toFixed(1) : '—';
  const avgA = sc > 0 ? (ra/sc).toFixed(1) : '—';
  const kpis = [
    {l:'Played',      v:played+nr, c:''},
    {l:'Won',         v:won,       c:'win'},
    {l:'Lost',        v:lost,      c:'lose'},
    {l:'Tied / NR',   v:tied+nr,   c:''},
    {l:'Win%',        v:wp,        c: won>=lost?'win':'lose'},
    {l:'Avg For',     v:avgF,      c:''},
    {l:'Avg Against', v:avgA,      c:''},
  ];
  const teamName = teams[sel];
  const logoHtml = `<div class="kpi" style="justify-content:center;align-items:center;padding:.5rem .75rem">${teamLogoHtml(teamName, 64)}</div>`;
  document.getElementById('kpi-strip').innerHTML =
    logoHtml + kpis.map(k=>`<div class="kpi"><div class="kpi-val ${k.c}">${k.v}</div><div class="kpi-label">${k.l}</div></div>`).join('');
}

/* ---- Team Performance (Season by Season) ---- */
function renderTeamSeasons(ml) {
  const sel = teamState.selectedTeam;
  const data = {};
  for (const m of ml) {
    const si = m_season_m[m];
    if (!data[si]) data[si] = {si,p:0,w:0,l:0,tied:0,nr:0,rf:0,ra:0,sc:0,rbf:0,rba:0};
    const d = data[si];
    if (m_no_result[m]) { d.nr++; continue; }
    d.p++;
    const isT1 = m_team1_a[m] === sel;
    const mt  = isT1 ? m_t1_total[m] : m_t2_total[m];
    const ot  = isT1 ? m_t2_total[m] : m_t1_total[m];
    const bf  = isT1 ? m_t1_balls[m] : m_t2_balls[m];   // balls team faced
    const ba  = isT1 ? m_t2_balls[m] : m_t1_balls[m];   // balls team bowled
    if      (m_is_tie[m])         d.tied++;
    else if (m_winner[m] === sel) d.w++;
    else if (m_winner[m] >= 0)    d.l++;
    if (mt>0&&ot>0&&bf>0&&ba>0) {
      d.rf+=mt; d.ra+=ot; d.rbf+=bf; d.rba+=ba; d.sc++;
    }
  }

  const sortCol  = teamState.seasonSort.col;
  const sortDesc = teamState.seasonSort.desc;

  const rows = Object.values(data).map(d => {
    const nrr = (d.rbf>0&&d.rba>0) ? (d.rf/d.rbf*6 - d.ra/d.rba*6) : null;
    const rank = getGroupRank(d.si, sel);
    return {
      si: d.si,
      season: seasons[d.si]||String(d.si),
      p:d.p+d.nr, w:d.w, l:d.l, tied:d.tied, nr:d.nr,
      wp: d.p>0?(d.w/d.p*100):null,
      nrr,
      rank: rank||null,
      af: d.sc>0?d.rf/d.sc:null,
      aa: d.sc>0?d.ra/d.sc:null,
    };
  });

  // Sort
  rows.sort((a,b) => {
    let va=a[sortCol], vb=b[sortCol];
    if (va==null&&vb==null) return 0;
    if (va==null) return 1;
    if (vb==null) return -1;
    if (typeof va==='string') return sortDesc ? vb.localeCompare(va) : va.localeCompare(vb);
    return sortDesc ? vb-va : va-vb;
  });

  if (!rows.length) {
    document.getElementById('teams-results').innerHTML='<div class="empty">No matches for this selection.</div>';
    return;
  }

  const cols = [
    {key:'season', label:'Season',      num:false, title:''},
    {key:'rank',   label:'Group Rank',  num:true,  title:'Final group-stage standing (points then NRR)'},
    {key:'nrr',    label:'NRR',         num:true,  title:'Net Run Rate in these matches: (runs scored/overs faced) − (runs conceded/overs bowled)'},
    {key:'p',      label:'P',           num:true,  title:'Matches played'},
    {key:'w',      label:'W',           num:true,  title:'Won'},
    {key:'l',      label:'L',           num:true,  title:'Lost'},
    {key:'tied',   label:'T/NR',        num:true,  title:'Tied or No Result'},
    {key:'wp',     label:'Win%',        num:true,  title:'Win % (ties and NR excluded)'},
    {key:'af',     label:'Avg For',     num:true,  title:'Average runs scored per match'},
    {key:'aa',     label:'Avg Against', num:true,  title:'Average runs conceded per match'},
  ];

  function arrow(k) {
    if (sortCol!==k) return '<span class="sort-arrow">↕</span>';
    return `<span class="sort-arrow">${sortDesc?'↓':'↑'}</span>`;
  }

  let h='<table><thead><tr>';
  for(const c of cols) {
    const active = sortCol===c.key ? ' sorted':'';
    const tit = c.title ? ` title="${escapeHtml(c.title)}"` : '';
    h+=`<th class="${c.num?'numeric':''}${active}" data-skey="${c.key}"${tit}>${c.label}${arrow(c.key)}</th>`;
  }
  h+='</tr></thead><tbody>';

  for(const r of rows){
    const rankCell = r.rank ? (r.rank<=4?`<strong>#${r.rank}</strong>`:`#${r.rank}`) : '—';
    const nrrCell  = r.nrr!=null ? (r.nrr>=0?`<span class="good">+${r.nrr.toFixed(3)}</span>`:`<span class="bad">${r.nrr.toFixed(3)}</span>`) : '—';
    const wpCell   = r.wp!=null ? (r.wp>=50?`<span class="good">${r.wp.toFixed(1)}%</span>`:`<span class="bad">${r.wp.toFixed(1)}%</span>`) : '—';
    h+=`<tr>
      <td class="player">${escapeHtml(r.season)}</td>
      <td class="numeric">${rankCell}</td>
      <td class="numeric">${nrrCell}</td>
      <td class="numeric">${r.p}</td>
      <td class="numeric"><strong>${r.w}</strong></td>
      <td class="numeric">${r.l}</td>
      <td class="numeric">${r.tied+r.nr}</td>
      <td class="numeric">${wpCell}</td>
      <td class="numeric">${r.af!=null?r.af.toFixed(1):'—'}</td>
      <td class="numeric">${r.aa!=null?r.aa.toFixed(1):'—'}</td>
    </tr>`;
  }
  h+='</tbody></table>';

  const el = document.getElementById('teams-results');
  el.innerHTML = h;
  // Attach sort listeners
  el.querySelectorAll('thead th[data-skey]').forEach(th => {
    th.style.cursor='pointer';
    th.addEventListener('click', () => {
      const k = th.dataset.skey;
      if (teamState.seasonSort.col===k) teamState.seasonSort.desc=!teamState.seasonSort.desc;
      else { teamState.seasonSort.col=k; teamState.seasonSort.desc=(k!=='season'); }
      renderTeamSeasons(ml);
    });
  });
}


/* ---- Contributors ---- */
function renderTeamContributors(ml) {
  const sel = teamState.selectedTeam;
  const el  = document.getElementById('teams-results');

  if (!ml.length) {
    el.innerHTML = '<div class="empty">No matches for this selection.</div>';
    return;
  }

  // ── One-time controls render (survives recomputes so the input keeps focus) ──
  if (!el.querySelector('#contrib-controls')) {
    el.innerHTML = `
      <div id="contrib-controls" class="contrib-toggle-row">
        <span class="contrib-toggle-label">Show in</span>
        <button class="chip" data-cmode="wins">Wins</button>
        <button class="chip" data-cmode="losses">Losses</button>
        <button class="chip" data-cmode="all">All</button>
        <span class="contrib-toggle-label" style="margin-left:.5rem">Min. balls</span>
        <input type="number" id="contrib-min-balls" class="number-input"
               min="0" value="${teamState.contribMinBalls}" style="width:72px">
      </div>
      <div id="contrib-data"></div>`;

    // Wire mode buttons once
    el.querySelectorAll('button[data-cmode]').forEach(btn => {
      btn.addEventListener('click', () => {
        teamState.contribMode = btn.dataset.cmode;
        recompute();
      });
    });

    // Wire min-balls input once — 'input' is fine because the input is never destroyed
    el.querySelector('#contrib-min-balls').addEventListener('input', e => {
      const v = parseInt(e.target.value, 10);
      teamState.contribMinBalls = isNaN(v) ? 0 : Math.max(0, v);
      recompute();
    });
  }

  // Keep toggle button active state in sync
  const mode = teamState.contribMode;
  el.querySelectorAll('button[data-cmode]').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.cmode === mode);
  });

  // ── Compute ──
  const matchMask = new Uint8Array(nMatches);
  const winMask   = new Uint8Array(nMatches);
  const lossMask  = new Uint8Array(nMatches);
  for (const m of ml) {
    matchMask[m] = 1;
    if (m_winner[m] === sel) winMask[m] = 1;
    else if (m_winner[m] >= 0 && !m_is_tie[m] && !m_no_result[m]) lossMask[m] = 1;
  }
  function use(m) {
    return mode === 'wins' ? winMask[m] : mode === 'losses' ? lossMask[m] : matchMask[m];
  }

  const bRuns  = new Int32Array(nBatters);
  const bBalls = new Int32Array(nBatters);
  const bOuts  = new Int32Array(nBatters);
  const wRuns  = new Int32Array(nBowlers);
  const wLb    = new Int32Array(nBowlers);
  const wWkts  = new Int32Array(nBowlers);

  for (let i = 0; i < N; i++) {
    const m = e_match[i];
    if (!use(m)) continue;
    if (e_bat_team[i] === sel) {
      bRuns[e_batter[i]]  += e_runs[i];
      bBalls[e_batter[i]] += e_ball_faced[i];
      bOuts[e_batter[i]]  += e_dismissed[i];
    }
    if (e_bowl_team[i] === sel) {
      wRuns[e_bowler[i]]  += e_bowl_runs[i];
      wLb[e_bowler[i]]    += e_ball_faced[i];
      wWkts[e_bowler[i]]  += e_bowl_wicket[i];
    }
  }

  const minB = teamState.contribMinBalls;
  const modeLabels = {wins:'Wins', losses:'Losses', all:'All matches'};
  const mLabel = modeLabels[mode];

  const batRows = [];
  for (let b = 0; b < nBatters; b++) {
    if (bBalls[b] < minB) continue;
    batRows.push({
      p: batters[b], r: bRuns[b], bl: bBalls[b], o: bOuts[b],
      sr:  bBalls[b] > 0 ? bRuns[b] / bBalls[b] * 100 : null,
      avg: bOuts[b]  > 0 ? bRuns[b] / bOuts[b]        : null,
    });
  }

  const bowlRows = [];
  for (let b = 0; b < nBowlers; b++) {
    if (wLb[b] < minB) continue;
    bowlRows.push({
      p: bowlers[b], r: wRuns[b], lb: wLb[b], w: wWkts[b],
      eco: wLb[b]   > 0 ? wRuns[b] / wLb[b] * 6 : null,
      avg: wWkts[b] > 0 ? wRuns[b] / wWkts[b]   : null,
    });
  }

  // ── Sort helpers ──
  function sortRows(rows, s, cols) {
    const dir = s.desc ? -1 : 1;
    rows.sort((a, b) => {
      const av = a[s.col], bv = b[s.col];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'string') return dir * av.localeCompare(bv);
      return dir * (bv - av) * -1;  // numeric: desc = biggest first
    });
  }

  function applySort(rows, s) {
    const dir = s.desc ? -1 : 1;
    rows.sort((a, b) => {
      const av = a[s.col], bv = b[s.col];
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'string') return dir * av.localeCompare(bv);
      return dir * (av - bv);
    });
  }

  applySort(batRows,  teamState.contribBatSort);
  applySort(bowlRows, teamState.contribBowlSort);

  function sortArrow(s, col) {
    return s.col === col ? (s.desc ? ' ▼' : ' ▲') : '';
  }

  // ── Table builders ──
  function tblBat(rows) {
    if (!rows.length) return '<div class="empty" style="padding:1.5rem">No data — try lowering the minimum balls.</div>';
    const s = teamState.contribBatSort;
    let h = `<table><thead><tr>
      <th class="numeric">#</th>
      <th data-csort="bat" data-col="p" style="cursor:pointer">Batter${sortArrow(s,'p')}</th>
      <th class="numeric" data-csort="bat" data-col="r"  style="cursor:pointer">Runs${sortArrow(s,'r')}</th>
      <th class="numeric" data-csort="bat" data-col="bl" style="cursor:pointer">Balls${sortArrow(s,'bl')}</th>
      <th class="numeric" data-csort="bat" data-col="sr" style="cursor:pointer">Strike Rate${sortArrow(s,'sr')}</th>
      <th class="numeric" data-csort="bat" data-col="avg" style="cursor:pointer">Average${sortArrow(s,'avg')}</th>
    </tr></thead><tbody>`;
    for (let i = 0; i < Math.min(rows.length, 25); i++) {
      const r = rows[i];
      h += `<tr><td class="rank">${i+1}</td><td class="player">${escapeHtml(r.p)}</td>
        <td class="numeric">${r.r.toLocaleString()}</td>
        <td class="numeric">${r.bl.toLocaleString()}</td>
        <td class="numeric">${r.sr  != null ? r.sr.toFixed(1)  : '—'}</td>
        <td class="numeric">${r.avg != null ? r.avg.toFixed(1) : '—'}</td></tr>`;
    }
    return h + '</tbody></table>';
  }

  function tblBowl(rows) {
    if (!rows.length) return '<div class="empty" style="padding:1.5rem">No data — try lowering the minimum balls.</div>';
    const s = teamState.contribBowlSort;
    let h = `<table><thead><tr>
      <th class="numeric">#</th>
      <th data-csort="bowl" data-col="p"  style="cursor:pointer">Bowler${sortArrow(s,'p')}</th>
      <th class="numeric" data-csort="bowl" data-col="w"   style="cursor:pointer">Wickets${sortArrow(s,'w')}</th>
      <th class="numeric" data-csort="bowl" data-col="lb"  style="cursor:pointer">Overs${sortArrow(s,'lb')}</th>
      <th class="numeric" data-csort="bowl" data-col="eco" style="cursor:pointer">Economy${sortArrow(s,'eco')}</th>
      <th class="numeric" data-csort="bowl" data-col="avg" style="cursor:pointer">Average${sortArrow(s,'avg')}</th>
    </tr></thead><tbody>`;
    for (let i = 0; i < Math.min(rows.length, 25); i++) {
      const r = rows[i];
      h += `<tr><td class="rank">${i+1}</td><td class="player">${escapeHtml(r.p)}</td>
        <td class="numeric"><strong>${r.w}</strong></td>
        <td class="numeric">${fmtOvers(r.lb)}</td>
        <td class="numeric">${r.eco != null ? r.eco.toFixed(2) : '—'}</td>
        <td class="numeric">${r.avg != null ? r.avg.toFixed(1) : '—'}</td></tr>`;
    }
    return h + '</tbody></table>';
  }

  // ── Render data section only (controls row is untouched) ──
  const dataEl = el.querySelector('#contrib-data');
  dataEl.innerHTML = `
    <div class="contrib-panels" style="padding:1rem">
      <div class="contrib-card">
        <div class="contrib-card-header">Top Batters &mdash; ${mLabel}</div>
        <div class="table-wrap">${tblBat(batRows)}</div>
      </div>
      <div class="contrib-card">
        <div class="contrib-card-header">Top Bowlers &mdash; ${mLabel}</div>
        <div class="table-wrap">${tblBowl(bowlRows)}</div>
      </div>
    </div>`;

  // Wire sort headers
  dataEl.querySelectorAll('th[data-csort]').forEach(th => {
    th.addEventListener('click', () => {
      const tbl  = th.dataset.csort;   // 'bat' or 'bowl'
      const col  = th.dataset.col;
      const s    = tbl === 'bat' ? teamState.contribBatSort : teamState.contribBowlSort;
      if (s.col === col) s.desc = !s.desc;
      else { s.col = col; s.desc = (col !== 'p'); }
      if (tbl === 'bat') teamState.contribBatSort = s;
      else               teamState.contribBowlSort = s;
      recompute();
    });
  });
}



/* ================================================================== */
/*  FIELDING TAB                                                       */
/* ================================================================== */

/* ---- Build fielding filter UI ---- */
(function() {
  // Season chips
  const chipsEl = document.getElementById('field-seasons-chips');
  seasons.forEach((s, idx) => {
    const c = document.createElement('button');
    c.className='chip'; c.textContent=s; c.dataset.idx=idx; c.type='button';
    c.addEventListener('click', () => {
      if (fieldState.selectedSeasons.has(idx)) fieldState.selectedSeasons.delete(idx);
      else fieldState.selectedSeasons.add(idx);
      c.classList.toggle('active');
      recompute();
    });
    chipsEl.appendChild(c);
  });

  // Type toggle
  document.getElementById('field-type-toggle').querySelectorAll('button').forEach(b => {
    b.addEventListener('click', () => {
      document.getElementById('field-type-toggle').querySelectorAll('button')
        .forEach(x => x.classList.remove('active'));
      b.classList.add('active');
      fieldState.typeFilter = b.dataset.value;
      recompute();
    });
  });

  // Min dismissals
  document.getElementById('min-dismissals').addEventListener('input', e => {
    fieldState.minDismissals = Math.max(0, Math.floor(+e.target.value)||0);
    recompute();
  });

  // Player search
  document.getElementById('field-search').addEventListener('input', e => {
    fieldSearch = e.target.value.trim().toLowerCase();
    recompute();
  });
})();

/* ---- doComputeFielding ---- */
function doComputeFielding() {
  const t0 = performance.now();
  const sM  = fieldState.selectedSeasons.size ? fieldState.selectedSeasons : null;
  const tM  = fieldState.selectedTeam.size    ? fieldState.selectedTeam    : null;
  const oM  = fieldState.selectedOpp.size     ? fieldState.selectedOpp     : null;
  const tf  = fieldState.typeFilter;

  // Accumulators per fielder
  const ct  = new Int32Array(nFielders);   // regular catches
  const cnb = new Int32Array(nFielders);   // caught & bowled
  const ro  = new Int32Array(nFielders);   // run-outs (direct)
  const roa = new Int32Array(nFielders);   // run-out assists
  const st  = new Int32Array(nFielders);   // stumpings
  const matchSets = new Array(nFielders).fill(null);

  for (let i = 0; i < NF; i++) {
    if (sM && !sM.has(fd_season[i]))      continue;
    if (tM && !tM.has(fd_bowl_team[i]))   continue;
    if (oM && !oM.has(fd_bat_team[i]))    continue;

    const typ = fd_type[i];
    const showType = tf === 'all'
      || (tf === '0' && (typ === 0 || typ === 3))   // catches (inc C&B)
      || (tf === '1' && (typ === 1 || typ === 4))   // run-outs (direct + assist)
      || (tf === '2' && typ === 2);
    if (!showType) continue;

    const fi = fd_fielder[i];
    if      (typ === 0) ct[fi]++;
    else if (typ === 3) cnb[fi]++;
    else if (typ === 1) ro[fi]++;
    else if (typ === 4) roa[fi]++;
    else if (typ === 2) st[fi]++;

    if (!matchSets[fi]) matchSets[fi] = new Set();
    matchSets[fi].add(fd_match_a[i]);
  }

  const minD = fieldState.minDismissals;
  const rows = [];
  for (let fi = 0; fi < nFielders; fi++) {
    const total = ct[fi] + cnb[fi] + ro[fi] + roa[fi] + st[fi];
    if (total < minD) continue;
    rows.push({
      player:  fielders[fi], fidx: fi,
      matches: matchSets[fi] ? matchSets[fi].size : 0,
      ct:  ct[fi],
      cnb: cnb[fi],
      ro:  ro[fi],
      roa: roa[fi],
      st:  st[fi],
      total,
    });
  }

  // Sort
  const sc = fieldState.sortColumn, sd = fieldState.sortDesc;
  rows.sort((a, b) => {
    let va=a[sc], vb=b[sc];
    if (typeof va==='string') return sd?vb.localeCompare(va):va.localeCompare(vb);
    if (va==null&&vb==null) return 0;
    if (va==null) return 1; if (vb==null) return -1;
    return sd?vb-va:va-vb;
  });

  document.getElementById('field-meta').textContent = (performance.now()-t0).toFixed(0)+' ms';
  renderFieldingTable(rows);
}

/* ---- Render fielding table ---- */
function renderFieldingTable(rows) {
  const all = rows.length;
  const visible = fieldSearch
    ? rows.filter(r => r.player.toLowerCase().includes(fieldSearch))
    : rows;

  const countEl = document.getElementById('field-count');
  countEl.innerHTML = fieldSearch
    ? `<strong>${visible.length.toLocaleString()}</strong> of ${all.toLocaleString()} fielder${all!==1?'s':''} match these filters`
    : `<strong>${all.toLocaleString()}</strong> fielder${all!==1?'s':''} match these filters`;

  const wrap = document.getElementById('field-table-wrap');
  if (!visible.length) {
    wrap.innerHTML = all===0
      ? '<div class="empty">No fielders match these filters. Try lowering the minimum dismissals.</div>'
      : `<div class="empty">No fielder named &ldquo;${escapeHtml(fieldSearch)}&rdquo; in these results.</div>`;
    return;
  }

  const sc = fieldState.sortColumn, sd = fieldState.sortDesc;
  const cols = [
    {key:'player',  label:'Fielder',         num:false, title:''},
    {key:'matches', label:'Matches',          num:true,  title:'Matches with at least one dismissal'},
    {key:'total',   label:'Total',            num:true,  title:'Total dismissals (Catches + C&B + Run-out Direct + Run-out Assist + Stumpings)'},
    {key:'ct',      label:'Catches',          num:true,  title:'Catches (excluding caught & bowled)'},
    {key:'cnb',     label:'Caught & Bowled',  num:true,  title:'Caught & bowled — credit goes to the bowler'},
    {key:'ro',      label:'Run-out (Direct)', num:true,  title:'Direct run-out: fielder who broke the stumps or threw the ball'},
    {key:'roa',     label:'Run-out (Assist)', num:true,  title:'Run-out assist: second fielder involved in a run-out'},
    {key:'st',      label:'Stumpings',        num:true,  title:'Stumpings (wicketkeepers only)'},
  ];

  function arr(k) {
    if(sc!==k) return '<span class="sort-arrow">↕</span>';
    return `<span class="sort-arrow">${sd?'↓':'↑'}</span>`;
  }

  let h='<table><thead><tr><th class="numeric" data-static>#</th>';
  for(const c of cols) {
    const active = sc===c.key?' sorted':'';
    const tit = c.title?` title="${escapeHtml(c.title)}"`:'' ;
    h+=`<th class="${c.num?'numeric ':''}${active}" data-fkey="${c.key}"${tit}>${c.label}${arr(c.key)}</th>`;
  }
  h+='</tr></thead><tbody>';

  const cap = Math.min(visible.length, 500);
  for(let i=0;i<cap;i++){
    const r=visible[i];
    const pi=field_to_player[r.fidx];
    h+=`<tr>
      <td class="rank">${i+1}</td>
      <td class="player"><span class="player-link" data-pi="${pi}">${escapeHtml(r.player)}</span></td>
      <td class="numeric">${r.matches}</td>
      <td class="numeric"><strong>${r.total}</strong></td>
      <td class="numeric">${r.ct||'—'}</td>
      <td class="numeric">${r.cnb||'—'}</td>
      <td class="numeric">${r.ro||'—'}</td>
      <td class="numeric">${r.roa||'—'}</td>
      <td class="numeric">${r.st||'—'}</td>
    </tr>`;
  }
  h+='</tbody></table>';
  if(visible.length>cap) h+=`<div class="empty" style="border-top:1px solid var(--border);padding:.75rem;text-align:center">Showing top ${cap} of ${visible.length.toLocaleString()} — raise the minimum or use the search box.</div>`;

  wrap.innerHTML=h;

  // Sort listeners
  wrap.querySelectorAll('thead th[data-fkey]').forEach(th=>{
    th.style.cursor='pointer';
    th.addEventListener('click',()=>{
      const k=th.dataset.fkey;
      if(fieldState.sortColumn===k) fieldState.sortDesc=!fieldState.sortDesc;
      else { fieldState.sortColumn=k; fieldState.sortDesc=(k!=='player'); }
      recompute();
    });
  });
}


/* ================================================================== */
/*  PLAYER PROFILE TAB                                                  */
/* ================================================================== */

(function () {
  const searchInput  = document.getElementById('profile-search');
  const dropdown     = document.getElementById('profile-dropdown');
  const selectedName = document.getElementById('profile-selected-name');
  const kpiEl        = document.getElementById('player-kpi');
  const bodyEl       = document.getElementById('player-body');
  const cardsEl      = document.getElementById('player-cards');
  const seasonTblEl  = document.getElementById('player-season-table');

  let activePi = -1;   // index into all_players

  /* Filter state — reset each time a new player is selected */
  let pfSeasons = new Set();   // empty = all seasons
  let pfTeam    = -1;          // -1 = all teams

  const filterBar      = document.getElementById('player-filter-bar');
  const teamChipsEl    = document.getElementById('player-team-chips');
  const seasonChipsEl  = document.getElementById('player-season-chips');

  /* Expose tab-switch + render so external click handlers can call it */
  goToPlayer = function(pi) {
    if (pi < 0 || pi >= nPlayers) return;
    // Switch tab
    activeTab = 'player';
    tabBar.querySelectorAll('.tab-btn').forEach(b =>
      b.classList.toggle('active', b.dataset.tab === 'player'));
    teamsSection.style.display  = 'none';
    fieldSection.style.display  = 'none';
    playerSection.style.display = '';
    batbowlEls.forEach(el => { el.style.display = 'none'; });
    updateSubtitle();
    // Populate search box and render
    searchInput.value = all_players[pi];
    dropdown.style.display = 'none';
    renderProfile(pi, true);
    // Scroll to top of player section
    playerSection.scrollIntoView({behavior:'smooth', block:'start'});
  };

  /* ---- Player headshot + full name: Wikidata → Wikipedia pipeline ---- */
  /* Step 1: Wikidata lookup by ESPNCricinfo ID → real full name            */
  /* Step 2: Wikipedia search by full name → headshot photo                 */
  /* Returns {url, fullName}; url may be false if no photo found            */
  const _wikiCache = new Map(); // pi → {url, fullName}

  /* Resolve full name via Wikidata (property P598 = ESPNCricinfo player ID) */
  async function resolveFullName(cricinfoId, fallbackName) {
    if (!cricinfoId) return fallbackName;
    try {
      const sparql = `SELECT ?itemLabel WHERE {
        ?item wdt:P598 "${cricinfoId}" .
        SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }
      } LIMIT 1`;
      const url = 'https://query.wikidata.org/sparql?format=json&query=' + encodeURIComponent(sparql);
      const r = await fetch(url, {signal: AbortSignal.timeout(6000)});
      if (!r.ok) return fallbackName;
      const d = await r.json();
      const label = d.results?.bindings?.[0]?.itemLabel?.value;
      // Reject Wikidata Q-identifiers (no label found) and implausibly long strings
      if (label && !label.startsWith('Q') && label.split(' ').length <= 6) return label;
    } catch {}
    return fallbackName;
  }

  /* Search Wikipedia for a player by name → {url, title} or false */
  async function wikiPhotoSearch(searchName) {
    const base = 'https://en.wikipedia.org/w/api.php';
    async function tryQuery(query) {
      try {
        const q  = encodeURIComponent(query);
        const sr = await fetch(
          `${base}?action=query&list=search&srsearch=${q}&srlimit=3&srprop=&format=json&origin=*`,
          {signal: AbortSignal.timeout(6000)}
        );
        if (!sr.ok) return false;
        const sd   = await sr.json();
        const hits = sd.query?.search;
        if (!hits?.length) return false;

        const ids = hits.map(h => h.pageid).join('|');
        const ir  = await fetch(
          `${base}?action=query&pageids=${ids}&prop=pageimages|info&inprop=displaytitle&pithumbsize=200&format=json&origin=*`,
          {signal: AbortSignal.timeout(6000)}
        );
        if (!ir.ok) return false;
        const pages = (await ir.json()).query?.pages || {};
        for (const hit of hits) {
          const pg = pages[hit.pageid];
          if (pg?.thumbnail?.source) return {url: pg.thumbnail.source, title: pg.displaytitle || hit.title};
        }
        // No photo but got a hit — return title only for first result
        const fp = pages[hits[0]?.pageid];
        if (fp) return {url: false, title: fp.displaytitle || hits[0].title};
        return false;
      } catch { return false; }
    }
    return (await tryQuery(searchName + ' cricketer'))
        || (await tryQuery(searchName + ' cricket'))
        || (await tryQuery(searchName));
  }

  async function fetchPlayerPhoto(pi) {
    if (_wikiCache.has(pi)) return _wikiCache.get(pi);

    const name = all_players[pi];  // already a full name (baked in at build time)

    // Embedded headshot from build-time scraper
    const embedded = player_headshots[pi];
    if (embedded) {
      const r = {url: embedded, fullName: name};
      _wikiCache.set(pi, r); return r;
    }

    // Search Wikipedia for a photo using the full name (no runtime Wikidata lookup needed)
    const hit = await wikiPhotoSearch(name);

    const result = {url: hit ? hit.url : false, fullName: name};
    _wikiCache.set(pi, result);
    return result;
  }

  /* ---- Search dropdown ---- */
  searchInput.addEventListener('input', () => {
    const q = searchInput.value.trim().toLowerCase();
    if (!q) { dropdown.style.display = 'none'; return; }
    const hits = [];
    for (let i = 0; i < nPlayers && hits.length < 30; i++) {
      if (all_players[i].toLowerCase().includes(q)) hits.push(i);
    }
    if (!hits.length) { dropdown.style.display = 'none'; return; }
    dropdown.innerHTML = hits.map(pi =>
      `<div class="player-search-item" data-pi="${pi}">${escapeHtml(all_players[pi])}</div>`
    ).join('');
    dropdown.style.display = '';
    dropdown.querySelectorAll('.player-search-item').forEach(item => {
      item.addEventListener('click', () => {
        activePi = +item.dataset.pi;
        searchInput.value = all_players[activePi];
        selectedName.textContent = '';
        dropdown.style.display = 'none';
        renderProfile(activePi, true);
      });
    });
  });

  document.addEventListener('click', e => {
    if (!searchInput.contains(e.target) && !dropdown.contains(e.target))
      dropdown.style.display = 'none';
  });

  /* ---- Main render ---- */
  function renderProfile(pi, repopulateFilters) {
    const name     = all_players[pi];
    const batIdx   = player_bat_idx[pi];
    const bowlIdx  = player_bowl_idx[pi];
    const fieldIdx = player_field_idx[pi];

    /* --- Quick discovery pass: build matchTeam map for ALL matches --- */
    const matchTeam = {};   // match → player's team index
    if (batIdx >= 0) {
      for (let i = 0; i < N; i++) {
        if (e_batter[i] !== batIdx) continue;
        matchTeam[e_match[i]] = e_bat_team[i];
      }
    }
    if (bowlIdx >= 0) {
      for (let i = 0; i < N; i++) {
        if (e_bowler[i] !== bowlIdx) continue;
        const m = e_match[i];
        if (matchTeam[m] === undefined) matchTeam[m] = e_bowl_team[i];
      }
    }
    if (fieldIdx >= 0) {
      for (let i = 0; i < fd_fielder.length; i++) {
        if (fd_fielder[i] !== fieldIdx) continue;
        const m = fd_match_a[i];
        if (matchTeam[m] === undefined) matchTeam[m] = fd_bowl_team[i];
      }
    }

    /* --- Populate / reset filters when a new player is loaded --- */
    if (repopulateFilters) {
      pfTeam    = -1;
      pfSeasons = new Set();

      // Collect this player's unique teams and seasons (sorted)
      const playerTeamSet   = new Set(Object.values(matchTeam));
      const playerSeasonSet = new Set(Object.keys(matchTeam).map(m => m_season_m[+m]));
      const sortedTeams   = [...playerTeamSet].sort((a,b) => teams[a].localeCompare(teams[b]));
      const sortedSeasons = [...playerSeasonSet].sort((a,b) => a - b);

      // Team chips
      teamChipsEl.innerHTML = '';
      if (sortedTeams.length > 1) {
        const allTeamChip = document.createElement('button');
        allTeamChip.className = 'chip active'; allTeamChip.textContent = 'All';
        allTeamChip.dataset.team = '-1';
        teamChipsEl.appendChild(allTeamChip);
        sortedTeams.forEach(ti => {
          const c = document.createElement('button');
          c.className = 'chip'; c.textContent = teams[ti]; c.dataset.team = ti;
          teamChipsEl.appendChild(c);
        });
        teamChipsEl.querySelectorAll('button').forEach(btn => {
          btn.addEventListener('click', () => {
            pfTeam = +btn.dataset.team;
            teamChipsEl.querySelectorAll('button').forEach(b =>
              b.classList.toggle('active', b === btn));
            renderProfile(pi, false);
          });
        });
      }

      // Season chips
      seasonChipsEl.innerHTML = '';
      const allSeasonChip = document.createElement('button');
      allSeasonChip.className = 'chip active'; allSeasonChip.textContent = 'All';
      seasonChipsEl.appendChild(allSeasonChip);
      allSeasonChip.addEventListener('click', () => {
        pfSeasons.clear();
        seasonChipsEl.querySelectorAll('button').forEach(b =>
          b.classList.toggle('active', b === allSeasonChip));
        renderProfile(pi, false);
      });
      sortedSeasons.forEach(si => {
        const c = document.createElement('button');
        c.className = 'chip'; c.textContent = seasons[si]; c.dataset.si = si;
        seasonChipsEl.appendChild(c);
        c.addEventListener('click', () => {
          if (pfSeasons.has(si)) pfSeasons.delete(si); else pfSeasons.add(si);
          allSeasonChip.classList.toggle('active', pfSeasons.size === 0);
          c.classList.toggle('active', pfSeasons.has(si));
          renderProfile(pi, false);
        });
      });

      filterBar.style.display = 'flex';
    }

    /* --- Build filtered match set --- */
    const filteredMatches = new Set();
    for (const [mStr, ti] of Object.entries(matchTeam)) {
      const m  = +mStr;
      const si = m_season_m[m];
      if (pfTeam >= 0 && ti !== pfTeam) continue;
      if (pfSeasons.size > 0 && !pfSeasons.has(si)) continue;
      filteredMatches.add(m);
    }

    /* --- Pass 1: batting by innings (filtered) --- */
    // key = match*4+innings → {runs, balls, out, match}
    const batByInn = {};
    if (batIdx >= 0) {
      for (let i = 0; i < N; i++) {
        if (e_batter[i] !== batIdx) continue;
        const m = e_match[i];
        if (!filteredMatches.has(m)) continue;
        const k = m * 4 + e_innings[i];
        if (!batByInn[k]) batByInn[k] = {runs:0, balls:0, out:0, m};
        batByInn[k].runs  += e_runs[i];
        batByInn[k].balls += e_ball_faced[i];
        if (e_dismissed[i]) batByInn[k].out = 1;
      }
    }

    let batInn=0, batRuns=0, batBalls=0, batOuts=0;
    let bat50=0, bat100=0, batDucks=0, batHS=0, batNotOut=0;
    for (const inn of Object.values(batByInn)) {
      if (inn.balls === 0) continue;
      batInn++;
      batRuns  += inn.runs;
      batBalls += inn.balls;
      if (inn.out) batOuts++; else batNotOut++;
      if (inn.runs >= 100) bat100++;
      else if (inn.runs >= 50) bat50++;
      if (!inn.out && inn.runs === 0 && inn.balls > 0) { /* not-out 0, not a duck */ }
      if (inn.out && inn.runs === 0) batDucks++;
      if (inn.runs > batHS) batHS = inn.runs;
    }
    const batAvg = batOuts > 0 ? batRuns / batOuts : null;
    const batSR  = batBalls > 0 ? batRuns / batBalls * 100 : null;

    /* --- Pass 2: bowling by innings + phase (filtered) --- */
    const bowlByInn = {};
    // phase: 0=PP(1-6), 1=Middle(7-15), 2=Death(16-20)
    const phaseRuns  = [0, 0, 0];
    const phaseBalls = [0, 0, 0];
    const phaseWkts  = [0, 0, 0];
    if (bowlIdx >= 0) {
      for (let i = 0; i < N; i++) {
        if (e_bowler[i] !== bowlIdx) continue;
        const m = e_match[i];
        if (!filteredMatches.has(m)) continue;
        const k = m * 4 + e_innings[i];
        if (!bowlByInn[k]) bowlByInn[k] = {runs:0, balls:0, wkts:0, m};
        bowlByInn[k].runs  += e_bowl_runs[i];
        bowlByInn[k].balls += e_ball_faced[i];
        bowlByInn[k].wkts  += e_bowl_wicket[i];
        // phase
        const ov = e_over[i];
        const ph = ov <= 6 ? 0 : ov <= 15 ? 1 : 2;
        phaseRuns[ph]  += e_bowl_runs[i];
        phaseBalls[ph] += e_ball_faced[i];
        phaseWkts[ph]  += e_bowl_wicket[i];
      }
    }

    let bowlInn=0, bowlRuns=0, bowlBalls=0, bowlWkts=0;
    let bowl3=0, bowl4=0, bestW=0, bestR=9999;
    for (const inn of Object.values(bowlByInn)) {
      if (inn.balls === 0) continue;
      bowlInn++;
      bowlRuns  += inn.runs;
      bowlBalls += inn.balls;
      bowlWkts  += inn.wkts;
      if (inn.wkts >= 4) bowl4++;
      else if (inn.wkts >= 3) bowl3++;
      if (inn.wkts > bestW || (inn.wkts === bestW && inn.runs < bestR)) {
        bestW = inn.wkts; bestR = inn.runs;
      }
    }
    const bowlAvg = bowlWkts > 0 ? bowlRuns / bowlWkts : null;
    const bowlEco = bowlBalls > 0 ? bowlRuns / bowlBalls * 6 : null;
    const bowlSR  = bowlWkts > 0 ? bowlBalls / bowlWkts : null;

    /* --- Pass 3: fielding (filtered) --- */
    let fCatch=0, fCnB=0, fROd=0, fROa=0, fSt=0;
    if (fieldIdx >= 0) {
      for (let i = 0; i < fd_fielder.length; i++) {
        if (fd_fielder[i] !== fieldIdx) continue;
        if (!filteredMatches.has(fd_match_a[i])) continue;
        const t = fd_type[i];
        if (t === 0) fCatch++;
        else if (t === 1) fROd++;
        else if (t === 2) fSt++;
        else if (t === 3) fCnB++;
        else if (t === 4) fROa++;
      }
    }

    /* --- Match-level aggregates (filtered) --- */
    const playerMatches = [...filteredMatches];
    const matchSet = filteredMatches;
    let totalPlayed=0, totalWins=0;
    const playoffSeasons = new Set();
    let tournWins = 0;
    let momCount = 0;
    for (const m of playerMatches) {
      if (m_pom[m] === pi) momCount++;
      if (m_no_result[m]) continue;
      totalPlayed++;
      const pTeam = matchTeam[m];
      if (m_winner[m] === pTeam) totalWins++;
      const stg = stages_list[m_stage[m]];
      if (PLAYOFF_STAGES.has(stg)) {
        playoffSeasons.add(m_season_m[m]);
        if (stg === 'Final' && m_winner[m] === pTeam) tournWins++;
      }
    }
    const winPct = totalPlayed > 0 ? (totalWins / totalPlayed * 100).toFixed(1) : '—';

    /* Career span & teams — always from the full (unfiltered) matchTeam map */
    const allMatchKeys = Object.keys(matchTeam).map(Number);
    const allSeasonIdxs = [...new Set(allMatchKeys.map(m => m_season_m[m]))].sort((a,b)=>a-b);
    const allTeamIdxs   = [...new Set(allMatchKeys.map(m => matchTeam[m]).filter(t=>t!==undefined))];
    const careerSpan = allSeasonIdxs.length
      ? seasons[allSeasonIdxs[0]] + (allSeasonIdxs.length > 1 ? ' – ' + seasons[allSeasonIdxs[allSeasonIdxs.length-1]] : '')
      : '—';
    const teamNames = allTeamIdxs.map(t => teams[t]).join(', ');

    /* --- Determine role --- */
    const hasBat  = batInn > 0;
    const hasBowl = bowlInn > 0;
    const role = hasBat && hasBowl
      ? (bowlWkts >= 30 && batRuns >= 500 ? 'All-Rounder' : bowlWkts > batRuns / 30 ? 'Bowler / All-Rounder' : 'Batter / All-Rounder')
      : hasBowl ? 'Bowler' : 'Batter';

    /* ---- KPI strip ---- */
    // Initials fallback for photo
    const initials = name.split(' ').map(w=>w[0]).filter(Boolean).slice(0,2).join('');
    kpiEl.innerHTML = `
      <div class="player-kpi-strip" style="align-items:stretch">
        <div class="player-kpi-item" style="display:flex;align-items:center;justify-content:center;padding:.75rem 1.25rem">
          <div id="player-photo-el" class="player-photo-wrap" style="width:80px;height:80px">
            <div class="player-photo-fallback" style="width:80px;height:80px;font-size:1.6rem">${escapeHtml(initials)}</div>
          </div>
        </div>
        <div class="player-kpi-item" style="flex:2;text-align:left;justify-content:center;display:flex;flex-direction:column">
          <div class="player-kpi-label">Player</div>
          <div id="player-fullname-el" class="player-kpi-value" style="font-size:1.15rem">${escapeHtml(name)}</div>
          <div class="player-kpi-sub">${escapeHtml(role)} &middot; ${escapeHtml(careerSpan)}</div>
        </div>
        <div class="player-kpi-item">
          <div class="player-kpi-label">Matches</div>
          <div class="player-kpi-value">${totalPlayed}</div>
        </div>
        <div class="player-kpi-item">
          <div class="player-kpi-label">Win %</div>
          <div class="player-kpi-value">${winPct}${winPct !== '—' ? '%' : ''}</div>
        </div>
        <div class="player-kpi-item">
          <div class="player-kpi-label">MOM Awards</div>
          <div class="player-kpi-value">${momCount}</div>
        </div>
        <div class="player-kpi-item">
          <div class="player-kpi-label">Tournament Wins</div>
          <div class="player-kpi-value">${tournWins}</div>
        </div>
        <div class="player-kpi-item">
          <div class="player-kpi-label">Playoffs</div>
          <div class="player-kpi-value">${playoffSeasons.size}</div>
          <div class="player-kpi-sub">seasons</div>
        </div>
        <div class="player-kpi-item" style="flex:2;text-align:left">
          <div class="player-kpi-label">Teams</div>
          <div class="player-kpi-value" style="font-size:.85rem;font-weight:600;line-height:1.4">${escapeHtml(teamNames)}</div>
        </div>
      </div>`;

    /* Show player headshot + full name via Wikipedia API (async) */
    if (repopulateFilters) {
      fetchPlayerPhoto(pi).then(({url: photoUrl, fullName}) => {
        // Update displayed name if Wikipedia gave us a fuller version
        if (fullName && fullName !== name) {
          const nameEl = document.getElementById('player-fullname-el');
          if (nameEl) nameEl.textContent = fullName;
        }
        // Update photo
        if (!photoUrl) return;
        const el = document.getElementById('player-photo-el');
        if (!el) return;
        const img = document.createElement('img');
        img.style.cssText = 'width:80px;height:80px;object-fit:cover;border-radius:50%';
        img.alt = fullName || name;
        img.onload = () => { el.innerHTML = ''; el.appendChild(img); };
        img.onerror = () => {}; // silently keep initials fallback on error
        img.src = photoUrl;
      });
    }

    /* ---- Stat cards ---- */
    function statCard(title, items, extra) {
      const rows = items.map(([lbl, val]) => `
        <div class="player-stat-item">
          <div class="player-stat-label">${lbl}</div>
          <div class="player-stat-value">${val}</div>
        </div>`).join('');
      return `
        <div class="player-stat-card">
          <div class="player-stat-card-header">${title}</div>
          <div class="player-stat-grid">${rows}</div>
          ${extra || ''}
        </div>`;
    }

    const fmt1 = v => v != null ? v.toFixed(1) : '—';
    const fmt2 = v => v != null ? v.toFixed(2) : '—';

    const batCard = hasBat ? statCard('Batting', [
      ['Innings',      batInn],
      ['Runs',         batRuns.toLocaleString()],
      ['Average',      fmt1(batAvg)],
      ['Strike Rate',  fmt1(batSR)],
      ['Highest Score',batHS],
      ['Not Outs',     batNotOut],
      ['50s',          bat50],
      ['100s',         bat100],
      ['Ducks',        batDucks],
      ['Balls Faced',  batBalls.toLocaleString()],
    ]) : `<div class="player-stat-card"><div class="player-stat-card-header">Batting</div><div class="kpi-empty" style="padding:2rem">No batting data</div></div>`;

    // Phase breakdown table
    const phaseLabels = ['Powerplay (1–6)', 'Middle (7–15)', 'Death (16–20)'];
    let phaseHtml = '';
    if (hasBowl) {
      phaseHtml = `<table class="player-phase-table" style="margin-top:0">
        <thead><tr><th>Phase</th><th>Overs</th><th>Wkts</th><th>Economy</th></tr></thead><tbody>`;
      phaseLabels.forEach((lbl, ph) => {
        const eco = phaseBalls[ph] > 0 ? (phaseRuns[ph] / phaseBalls[ph] * 6).toFixed(2) : '—';
        phaseHtml += `<tr><td>${lbl}</td><td>${fmtOvers(phaseBalls[ph])}</td><td>${phaseWkts[ph]}</td><td>${eco}</td></tr>`;
      });
      phaseHtml += '</tbody></table>';
    }

    const bowlCard = hasBowl ? statCard('Bowling', [
      ['Innings',     bowlInn],
      ['Wickets',     bowlWkts],
      ['Average',     fmt1(bowlAvg)],
      ['Economy',     fmt2(bowlEco)],
      ['Best Figures',bestW > 0 ? `${bestW}/${bestR}` : '—'],
      ['Strike Rate', fmt1(bowlSR)],
      ['3-Wicket Hauls', bowl3],
      ['4+ Wicket Hauls', bowl4],
      ['Overs',       fmtOvers(bowlBalls)],
      ['Runs',        bowlRuns.toLocaleString()],
    ], phaseHtml ? `<div style="border-top:1px solid var(--border)"><div style="padding:.4rem 1rem;font-size:.7rem;font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--text-muted);background:#fafafa;border-bottom:1px solid var(--border)">Phase Breakdown</div>${phaseHtml}</div>` : '')
      : `<div class="player-stat-card"><div class="player-stat-card-header">Bowling</div><div class="kpi-empty" style="padding:2rem">No bowling data</div></div>`;

    const fTotal = fCatch + fCnB + fROd + fROa + fSt;
    const fieldCard = fTotal > 0 ? statCard('Fielding', [
      ['Catches',            fCatch],
      ['Caught & Bowled',    fCnB],
      ['Run-out (Direct)',   fROd],
      ['Run-out (Assist)',   fROa],
      ['Stumpings',          fSt],
      ['Total Dismissals',   fTotal],
    ]) : `<div class="player-stat-card"><div class="player-stat-card-header">Fielding</div><div class="kpi-empty" style="padding:2rem">No fielding data</div></div>`;

    cardsEl.innerHTML = batCard + bowlCard + fieldCard;

    /* ---- Season-by-season table ---- */
    // Aggregate per season
    const sData = {};  // si → {team, mat, bat:{runs,balls,outs,hs,inn}, bowl:{runs,balls,wkts}, field:{dis}}
    function getSeason(m) { return m_season_m[m]; }

    // batting
    for (const [kStr, inn] of Object.entries(batByInn)) {
      if (inn.balls === 0) continue;
      const si = getSeason(inn.m);
      if (!sData[si]) sData[si] = {si, team:-1, mat:new Set(), bat:{runs:0,balls:0,outs:0,hs:0,inn:0,no:0,s50:0,s100:0}, bowl:{runs:0,balls:0,wkts:0}, field:{dis:0}};
      sData[si].mat.add(inn.m);
      sData[si].bat.runs  += inn.runs;
      sData[si].bat.balls += inn.balls;
      if (inn.out) sData[si].bat.outs++; else sData[si].bat.no++;
      if (inn.runs >= 100) sData[si].bat.s100++;
      else if (inn.runs >= 50) sData[si].bat.s50++;
      if (inn.runs > sData[si].bat.hs) sData[si].bat.hs = inn.runs;
      sData[si].bat.inn++;
      if (!sData[si].team || sData[si].team < 0) sData[si].team = matchTeam[inn.m] ?? -1;
    }
    // bowling
    for (const [kStr, inn] of Object.entries(bowlByInn)) {
      if (inn.balls === 0) continue;
      const si = getSeason(inn.m);
      if (!sData[si]) sData[si] = {si, team:-1, mat:new Set(), bat:{runs:0,balls:0,outs:0,hs:0,inn:0,no:0,s50:0,s100:0}, bowl:{runs:0,balls:0,wkts:0}, field:{dis:0}};
      sData[si].mat.add(inn.m);
      sData[si].bowl.runs  += inn.runs;
      sData[si].bowl.balls += inn.balls;
      sData[si].bowl.wkts  += inn.wkts;
      if (!sData[si].team || sData[si].team < 0) sData[si].team = matchTeam[inn.m] ?? -1;
    }
    // fielding
    if (fieldIdx >= 0) {
      for (let i = 0; i < fd_fielder.length; i++) {
        if (fd_fielder[i] !== fieldIdx) continue;
        const si = fd_season[i];
        const m  = fd_match_a[i];
        if (!sData[si]) sData[si] = {si, team:-1, mat:new Set(), bat:{runs:0,balls:0,outs:0,hs:0,inn:0,no:0,s50:0,s100:0}, bowl:{runs:0,balls:0,wkts:0}, field:{dis:0}};
        sData[si].mat.add(m);
        sData[si].field.dis++;
      }
    }

    const sRows = Object.values(sData).sort((a,b) => a.si - b.si);
    let tbl = `<table><thead><tr>
      <th>Season</th><th>Team</th><th class="numeric">Mat</th>`;
    if (hasBat)  tbl += `<th class="numeric">Runs</th><th class="numeric">Avg</th><th class="numeric">SR</th><th class="numeric">HS</th><th class="numeric">50s</th><th class="numeric">100s</th>`;
    if (hasBowl) tbl += `<th class="numeric">Wkts</th><th class="numeric">Overs</th><th class="numeric">Eco</th>`;
    if (fTotal>0)tbl += `<th class="numeric">Dis</th>`;
    tbl += `</tr></thead><tbody>`;
    for (const r of sRows) {
      const b = r.bat, w = r.bowl, f = r.field;
      const bAvg = b.outs > 0 ? (b.runs/b.outs).toFixed(1) : b.inn > 0 ? '∞' : '—';
      const bSR  = b.balls > 0 ? (b.runs/b.balls*100).toFixed(1) : '—';
      const wEco = w.balls > 0 ? (w.runs/w.balls*6).toFixed(2) : '—';
      const teamName = r.team >= 0 ? teams[r.team] : '—';
      tbl += `<tr><td>${seasons[r.si]}</td><td>${escapeHtml(teamName)}</td><td class="numeric">${r.mat.size}</td>`;
      if (hasBat)  tbl += `<td class="numeric">${b.runs}</td><td class="numeric">${bAvg}</td><td class="numeric">${bSR}</td><td class="numeric">${b.hs}</td><td class="numeric">${b.s50}</td><td class="numeric">${b.s100}</td>`;
      if (hasBowl) tbl += `<td class="numeric"><strong>${w.wkts}</strong></td><td class="numeric">${fmtOvers(w.balls)}</td><td class="numeric">${wEco}</td>`;
      if (fTotal>0)tbl += `<td class="numeric">${f.dis}</td>`;
      tbl += `</tr>`;
    }
    seasonTblEl.innerHTML = tbl + '</tbody></table>';

    bodyEl.style.display = '';
  }

})();  /* end player profile IIFE */

/* ------------------------------------------------------------------ */
/*  Boot                                                                */
/* ------------------------------------------------------------------ */
recompute();

})();
</script>
</body>
</html>
"""


def main():
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    ap.add_argument("build_dir",   help="Folder containing deliveries.csv")
    ap.add_argument("output_html", help="Where to write the dashboard HTML")
    args = ap.parse_args()

    build_dir = Path(args.build_dir).expanduser().resolve()
    out_path  = Path(args.output_html).expanduser().resolve()
    deliveries_path = build_dir / "deliveries.csv"
    if not deliveries_path.exists():
        print(f"Missing: {deliveries_path}", file=sys.stderr)
        sys.exit(1)

    # ---- Load downloaded assets (from download_assets.py) ----
    script_dir  = Path(__file__).parent
    assets_dir  = script_dir / "assets"
    team_logos_embedded = {}   # team_name -> data URI (base64)
    player_cricinfo_map = {}   # player_name -> cricinfo numeric ID
    player_headshots_map = {}  # player_name -> full headshot URL (og:image)

    logos_json = assets_dir / "team_logos.json"
    if logos_json.exists():
        team_logos_embedded = json.loads(logos_json.read_text())
        print(f"  Loaded {len(team_logos_embedded)} embedded team logos from assets/")
    else:
        print("  No assets/team_logos.json found — run download_assets.py to embed logos")

    ids_json = assets_dir / "player_cricinfo_ids.json"
    if ids_json.exists():
        player_cricinfo_map = json.loads(ids_json.read_text())
        print(f"  Loaded {len(player_cricinfo_map)} player Cricinfo IDs from assets/")

    headshots_json = assets_dir / "player_headshots.json"
    if headshots_json.exists():
        player_headshots_map = json.loads(headshots_json.read_text())
        print(f"  Loaded {len(player_headshots_map)} player headshot URLs from assets/")

    player_fullnames_map = {}  # abbreviated_name -> full_name
    fullnames_json = assets_dir / "player_fullnames.json"
    if fullnames_json.exists():
        player_fullnames_map = json.loads(fullnames_json.read_text())
        print(f"  Loaded {len(player_fullnames_map)} player full names from assets/")

    # ---- Dictionaries for interning string values ----
    batters,  batter_idx  = [], {}
    bowlers,  bowler_idx  = [], {}
    teams,    team_idx    = [], {}
    venues,   venue_idx   = [], {}
    seasons,  season_idx  = [], {}
    matches,  match_idx   = [], {}

    def intern(value, lst, lookup):
        if not value:
            value = "(unknown)"
        if value not in lookup:
            lookup[value] = len(lst)
            lst.append(value)
        return lookup[value]

    # ---- Per-delivery event arrays ----
    e_batter, e_bowler, e_season   = [], [], []
    e_bat_team, e_bowl_team        = [], []
    e_venue, e_over, e_innings     = [], [], []
    e_runs, e_ball_faced           = [], []
    e_dismissed                    = []
    e_bowl_runs, e_bowl_wicket     = [], []
    e_is_noball                    = []
    e_match                        = []

    # Fielding event arrays (populated inside delivery loop)
    fielders_f, fielder_idx_f = [], {}
    fd_fielder_raw, fd_season_raw = [], []
    fd_bat_team_raw, fd_bowl_team_raw = [], []
    fd_type_raw, fd_match_raw = [], []
    # fd_type: 0=catch  1=run-out  2=stumping  3=caught-and-bowled

    n = 0
    with open(deliveries_path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            # Skip super overs
            if int(row.get("is_super_over") or 0):
                continue

            batter   = row["batter"]
            wides    = int(row["extras_wides"]   or 0)
            noballs  = int(row["extras_noballs"] or 0)
            runs_bat = int(row["runs_batter"]    or 0)
            is_wkt   = int(row["is_wicket"]      or 0)
            dismissed = 0

            if is_wkt and row.get("player_out") == batter:
                dismissed = 1

            # Bowl wicket: credited to bowler unless run-out / obstruction / retired
            bowl_wicket = 0
            if is_wkt:
                kind = (row.get("wicket_kind") or "").strip().lower()
                if kind and kind not in NON_BOWL_WICKETS:
                    bowl_wicket = 1

            # Runs charged to bowler = batter runs + wides + no-balls
            bowl_runs = min(runs_bat + wides + noballs, 255)

            e_batter.append(intern(batter,              batters,  batter_idx))
            e_bowler.append(intern(row["bowler"],       bowlers,  bowler_idx))
            e_season.append(intern(row["season"],       seasons,  season_idx))
            e_bat_team.append(intern(row["batting_team"],  teams, team_idx))
            e_bowl_team.append(intern(row["bowling_team"], teams, team_idx))
            e_venue.append(intern(row["venue"],         venues,   venue_idx))
            e_over.append(int(row["over"] or 0))
            e_innings.append(int(row["innings_no"] or 0))
            e_runs.append(runs_bat)
            e_ball_faced.append(0 if wides else 1)
            e_dismissed.append(dismissed)
            e_bowl_runs.append(bowl_runs)
            e_bowl_wicket.append(bowl_wicket)
            e_is_noball.append(1 if noballs else 0)
            e_match.append(intern(row["match_id"], matches, match_idx))

            # -- Fielding events --
            raw_kind     = (row.get("wicket_kind") or "").strip().lower()
            raw_fld_str  = (row.get("fielders") or "").strip()
            if int(row.get("is_wicket") or 0):
                if raw_kind == "caught and bowled":
                    fnames = [row["bowler"]]
                    ftype  = 3
                elif raw_kind == "stumped":
                    fnames = [f.strip() for f in raw_fld_str.split(";") if f.strip()]
                    ftype  = 2
                elif raw_kind == "run out":
                    fnames = [f.strip() for f in raw_fld_str.split(";") if f.strip()]
                    ftype  = 1   # overridden per-fielder below (direct vs assist)
                elif raw_kind == "caught" and raw_fld_str:
                    fnames = [raw_fld_str.strip()]
                    ftype  = 0
                else:
                    fnames = []
                    ftype  = 0
                for idx_f, fname in enumerate(fnames):
                    # Run-out: first fielder = direct (1), subsequent = assist (4)
                    actual_type = (4 if (ftype == 1 and idx_f > 0) else ftype)
                    fi = intern(fname, fielders_f, fielder_idx_f)
                    fd_fielder_raw.append(fi)
                    fd_season_raw.append(intern(row["season"], seasons, season_idx))
                    fd_bat_team_raw.append(intern(row["batting_team"], teams, team_idx))
                    fd_bowl_team_raw.append(intern(row["bowling_team"], teams, team_idx))
                    fd_type_raw.append(actual_type)
                    fd_match_raw.append(intern(row["match_id"], matches, match_idx))

            n += 1

    # Sort seasons chronologically (Cricsheet labels sort lexicographically)
    sorted_seasons = sorted(seasons)
    season_remap = {old: sorted_seasons.index(name) for old, name in enumerate(seasons)}
    e_season     = [season_remap[s] for s in e_season]
    fd_season_raw= [season_remap[s] for s in fd_season_raw]


    # ---- Load match-level metadata ----
    sorted_season_to_si = {s: i for i, s in enumerate(sorted_seasons)}
    stages, stage_idx_map = [], {}
    def intern_stage(s):
        if s not in stage_idx_map:
            stage_idx_map[s] = len(stages)
            stages.append(s)
        return stage_idx_map[s]

    n_m = len(matches)
    m_team1_arr    = [0]  * n_m
    m_team2_arr    = [0]  * n_m
    m_season_arr   = [0]  * n_m
    m_winner_arr   = [-1] * n_m
    m_toss_win_arr = [0]  * n_m
    m_toss_dec_arr = [0]  * n_m
    m_stage_arr    = [0]  * n_m
    m_t1_total_arr = [0]  * n_m
    m_t2_total_arr = [0]  * n_m
    m_is_tie_arr   = [0]  * n_m
    m_no_result_arr= [0]  * n_m
    m_t1_balls_arr = [0]  * n_m   # balls faced by team1
    m_t2_balls_arr = [0]  * n_m   # balls faced by team2
    m_pom_arr      = [-1] * n_m   # player_of_match → index into all_players (filled after)

    def overs_to_balls(s):
        if not s: return 0
        try:
            f = float(s); o = int(f); b = round((f - o) * 10)
            return o * 6 + b
        except: return 0

    matches_csv_path = build_dir / "matches.csv"
    if matches_csv_path.exists():
        with open(matches_csv_path, newline="", encoding="utf-8") as mf:
            for mrow in csv.DictReader(mf):
                mid = mrow["match_id"]
                if mid not in match_idx:
                    continue
                mi = match_idx[mid]
                m_team1_arr[mi]    = intern(mrow["team1"], teams, team_idx)
                m_team2_arr[mi]    = intern(mrow["team2"], teams, team_idx)
                m_season_arr[mi]   = sorted_season_to_si.get(mrow["season"], 0)
                winner = (mrow.get("winner") or "").strip()
                m_winner_arr[mi]   = team_idx[winner] if winner in team_idx else -1
                tw = (mrow.get("toss_winner") or "").strip()
                m_toss_win_arr[mi] = team_idx.get(tw, 0)
                m_toss_dec_arr[mi] = 0 if mrow.get("toss_decision") == "bat" else 1
                stage = (mrow.get("stage") or "").strip() or "Group"
                m_stage_arr[mi]    = intern_stage(stage)
                try: m_t1_total_arr[mi] = int(float(mrow.get("team1_total") or 0))
                except: pass
                try: m_t2_total_arr[mi] = int(float(mrow.get("team2_total") or 0))
                except: pass
                res = (mrow.get("result") or "").strip().lower()
                m_is_tie_arr[mi]    = 1 if res == "tie" else 0
                m_no_result_arr[mi] = 1 if res == "no result" else 0
                m_t1_balls_arr[mi]  = overs_to_balls(mrow.get("team1_overs") or "")
                m_t2_balls_arr[mi]  = overs_to_balls(mrow.get("team2_overs") or "")
                # store raw POM name; resolved to all_players index after that array is built
                m_pom_arr[mi] = (mrow.get("player_of_match") or "").strip()

    # ---- Compute group-stage standings and rankings per season ----
    from collections import defaultdict
    gs_pts  = defaultdict(lambda: defaultdict(int))    # [si][ti] = pts
    gs_rf   = defaultdict(lambda: defaultdict(int))    # runs for
    gs_ra   = defaultdict(lambda: defaultdict(int))    # runs against
    gs_bf   = defaultdict(lambda: defaultdict(int))    # balls faced
    gs_ba   = defaultdict(lambda: defaultdict(int))    # balls conceded

    for mi in range(n_m):
        if stages[m_stage_arr[mi]] != 'Group':
            continue
        si  = m_season_arr[mi]
        t1  = m_team1_arr[mi]
        t2  = m_team2_arr[mi]
        r1  = m_t1_total_arr[mi]
        r2  = m_t2_total_arr[mi]
        b1  = m_t1_balls_arr[mi]
        b2  = m_t2_balls_arr[mi]
        w   = m_winner_arr[mi]
        tie = m_is_tie_arr[mi]
        nr  = m_no_result_arr[mi]

        if nr:
            gs_pts[si][t1] += 1
            gs_pts[si][t2] += 1
            continue

        if tie:
            gs_pts[si][t1] += 1
            gs_pts[si][t2] += 1
        elif w == t1:
            gs_pts[si][t1] += 2
        elif w == t2:
            gs_pts[si][t2] += 2

        if b1 > 0 and b2 > 0:
            gs_rf[si][t1] += r1; gs_bf[si][t1] += b1
            gs_ra[si][t1] += r2; gs_ba[si][t1] += b2
            gs_rf[si][t2] += r2; gs_bf[si][t2] += b2
            gs_ra[si][t2] += r1; gs_ba[si][t2] += b1

    # Build season_rankings[si][ti] = rank (1-based, 0 = didn't play that season)
    n_s = len(sorted_seasons)
    n_t = len(teams)
    season_rankings_flat = [0] * (n_s * n_t)
    for si in range(n_s):
        if si not in gs_pts:
            continue
        team_scores = []
        all_tis = set(gs_pts[si]) | set(gs_rf[si])
        for ti in all_tis:
            pts = gs_pts[si][ti]
            bf  = gs_bf[si][ti]
            ba  = gs_ba[si][ti]
            rf  = gs_rf[si][ti]
            ra  = gs_ra[si][ti]
            nrr = (rf/bf*6 - ra/ba*6) if bf > 0 and ba > 0 else 0.0
            team_scores.append((ti, pts, nrr))
        team_scores.sort(key=lambda x: (-x[1], -x[2]))
        for rank, (ti, pts, nrr) in enumerate(team_scores, 1):
            season_rankings_flat[si * n_t + ti] = rank

    # ---- Build unified all_players array for player profile ----
    all_players_set = set(batters) | set(bowlers) | set(fielders_f)
    all_players_list = sorted(all_players_set)
    player_idx_map = {n: i for i, n in enumerate(all_players_list)}
    n_ap = len(all_players_list)
    # Cross-reference: index in all_players → index in batters/bowlers/fielders (-1 if not found)
    player_bat_idx_arr   = [batter_idx.get(p, -1)      for p in all_players_list]
    player_bowl_idx_arr  = [bowler_idx.get(p, -1)      for p in all_players_list]
    player_field_idx_arr = [fielder_idx_f.get(p, -1)   for p in all_players_list]
    # Resolve POM names to all_players indices
    for mi in range(n_m):
        raw_name = m_pom_arr[mi]
        if isinstance(raw_name, str) and raw_name:
            m_pom_arr[mi] = player_idx_map.get(raw_name, -1)
        else:
            m_pom_arr[mi] = -1

    # Build player_cricinfo_arr: Cricinfo numeric ID per all_players entry (0 = unknown)
    player_cricinfo_arr = [player_cricinfo_map.get(p, 0) for p in all_players_list]
    matched = sum(1 for v in player_cricinfo_arr if v)
    print(f"  Player Cricinfo IDs: {matched}/{n_ap} matched"
          + ("" if matched else " — run download_assets.py to enable player photos"))

    # Build player headshot URL array — one entry per all_players, empty string = no photo
    # Uses player_headshots.json (from batch scraper) if available; falls back to empty
    player_headshots_arr = [player_headshots_map.get(p, '') for p in all_players_list]
    hs_matched = sum(1 for v in player_headshots_arr if v)
    if hs_matched:
        print(f"  Player headshots: {hs_matched}/{n_ap} URLs embedded")
    else:
        print(f"  No player_headshots.json — run the headshot scraper command to enable photos")

    # Substitute full names across all player name arrays (stat arrays use integer indices, so safe)
    if player_fullnames_map:
        fn = player_fullnames_map.get
        all_players_list = [fn(p, p) for p in all_players_list]
        batters          = [fn(p, p) for p in batters]
        bowlers          = [fn(p, p) for p in bowlers]
        fielders_f       = [fn(p, p) for p in fielders_f]
        fn_matched = sum(1 for p in all_players_list if ' ' in p)
        print(f"  Full name substitution: {fn_matched}/{n_ap} players have full names")

    # Build team_logos_js: a JS object literal with embedded base64 data URIs
    # Use downloaded logos if available, otherwise keep the Wikipedia URLs as fallback
    TEAM_LOGO_FALLBACK_URLS = {
        'Chennai Super Kings':         'https://upload.wikimedia.org/wikipedia/en/2/2b/Chennai_Super_Kings_Logo.svg',
        'Mumbai Indians':              'https://upload.wikimedia.org/wikipedia/en/c/cd/Mumbai_Indians_Logo.svg',
        'Royal Challengers Bengaluru': 'https://upload.wikimedia.org/wikipedia/en/2/2a/Royal_Challengers_Bangalore_2020.svg',
        'Kolkata Knight Riders':       'https://upload.wikimedia.org/wikipedia/en/4/4c/Kolkata_Knight_Riders_Logo.svg',
        'Sunrisers Hyderabad':         'https://upload.wikimedia.org/wikipedia/en/3/3f/Sunrisers_Hyderabad.svg',
        'Delhi Capitals':              'https://upload.wikimedia.org/wikipedia/en/f/f5/Delhi_Capitals_Logo.svg',
        'Punjab Kings':                'https://upload.wikimedia.org/wikipedia/en/d/d4/Punjab_Kings_Logo.svg',
        'Rajasthan Royals':            'https://upload.wikimedia.org/wikipedia/en/6/60/Rajasthan_Royals_Logo.svg',
        'Gujarat Titans':              'https://upload.wikimedia.org/wikipedia/en/0/09/Gujarat_Titans_Logo.svg',
        'Lucknow Super Giants':        'https://upload.wikimedia.org/wikipedia/en/a/a9/Lucknow_Super_Giants_Logo.svg',
        'Deccan Chargers':             'https://upload.wikimedia.org/wikipedia/en/7/7e/Deccan_Chargers.svg',
        'Rising Pune Supergiants':     'https://upload.wikimedia.org/wikipedia/en/5/5e/Rising_Pune_Supergiants_Logo.svg',
        'Gujarat Lions':               'https://upload.wikimedia.org/wikipedia/en/0/07/Gujarat_Lions_Logo.svg',
        'Kochi Tuskers Kerala':        'https://upload.wikimedia.org/wikipedia/en/e/e9/Kochi_Tuskers.svg',
        'Pune Warriors':               'https://upload.wikimedia.org/wikipedia/en/d/da/Pune_Warriors_India.svg',
    }
    # Merge: embedded (downloaded) logos take priority over fallback URLs
    team_logos_final = {}
    for t in teams:
        if t in team_logos_embedded:
            team_logos_final[t] = team_logos_embedded[t]   # data URI
        elif t in TEAM_LOGO_FALLBACK_URLS:
            team_logos_final[t] = TEAM_LOGO_FALLBACK_URLS[t]  # external URL fallback

    payload = {
        "batters": batters, "bowlers": bowlers, "teams": teams,
        "venues": venues, "seasons": sorted_seasons,
        "n_events": n, "n_matches": len(matches),
        "e_batter":      e_batter,
        "e_bowler":      e_bowler,
        "e_season":      e_season,
        "e_bat_team":    e_bat_team,
        "e_bowl_team":   e_bowl_team,
        "e_venue":       e_venue,
        "e_over":        e_over,
        "e_innings":     e_innings,
        "e_runs":        e_runs,
        "e_ball_faced":  e_ball_faced,
        "e_dismissed":   e_dismissed,
        "e_bowl_runs":   e_bowl_runs,
        "e_bowl_wicket": e_bowl_wicket,
        "noball_indices": [i for i, v in enumerate(e_is_noball) if v],
        "m_t1_balls":  m_t1_balls_arr,
        "m_t2_balls":  m_t2_balls_arr,
        "season_rankings": season_rankings_flat,
        "n_teams_for_rank": n_t,
        "stages":     stages,
        "m_team1":    m_team1_arr,
        "m_team2":    m_team2_arr,
        "m_season_m": m_season_arr,
        "m_winner":   m_winner_arr,
        "m_toss_win": m_toss_win_arr,
        "m_toss_dec": m_toss_dec_arr,
        "m_stage":    m_stage_arr,
        "m_t1_total": m_t1_total_arr,
        "m_t2_total": m_t2_total_arr,
        "m_is_tie":   m_is_tie_arr,
        "m_no_result":m_no_result_arr,
        "fielders":      fielders_f,
        "n_fd":          len(fd_fielder_raw),
        "fd_fielder":    fd_fielder_raw,
        "fd_season":     fd_season_raw,
        "fd_bat_team":   fd_bat_team_raw,
        "fd_bowl_team":  fd_bowl_team_raw,
        "fd_type":       fd_type_raw,
        "fd_match":      fd_match_raw,
        "e_match":       e_match,
        # Player profile arrays
        "all_players":        all_players_list,
        "player_bat_idx":     player_bat_idx_arr,
        "player_bowl_idx":    player_bowl_idx_arr,
        "player_field_idx":   player_field_idx_arr,
        "m_pom":              m_pom_arr,
        # Player Cricinfo IDs (0 = unknown)
        "player_cricinfo":    player_cricinfo_arr,
        # Player headshot URLs (empty string = no photo); from batch scraper
        "player_headshots":   player_headshots_arr,
    }
    payload_json = json.dumps(payload, separators=(",", ":"))

    # Inject team logos as a separate JS variable so the data blob stays compact
    # (logos are large base64 strings, kept out of the main JSON parse path)
    team_logos_js = "const TEAM_LOGOS_EMBEDDED=" + json.dumps(team_logos_final, separators=(",", ":")) + ";"

    html = (HTML_TEMPLATE
            .replace("__DATA__", payload_json)
            .replace("__TEAM_LOGOS_JS__", team_logos_js))
    out_path.write_text(html, encoding="utf-8")

    size_mb = out_path.stat().st_size / 1024 / 1024
    print(f"Wrote {out_path}")
    print(f"  Events:  {n:,}")
    print(f"  Batters: {len(batters)}  Bowlers: {len(bowlers)}  Teams: {len(teams)}  Venues: {len(venues)}  Seasons: {len(seasons)}")
    print(f"  Matches: {len(matches)}")
    print(f"  Size:    {size_mb:.1f} MB")


if __name__ == "__main__":
    main()
