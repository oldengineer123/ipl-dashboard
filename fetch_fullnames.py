import json, time, urllib.request, urllib.parse
from pathlib import Path

CRICINFO_IDS = json.loads(Path('/Users/raghav/Desktop/ipl_json/assets/player_cricinfo_ids.json').read_text())
OUT = Path('/Users/raghav/Desktop/ipl_json/assets/player_fullnames.json')
WD = 'https://www.wikidata.org/w/api.php'
HDR = {'User-Agent':'IPLDash/1.0 (nagarajan.raghav@gmail.com)','Accept':'application/json'}

def wd_get(params):
    req = urllib.request.Request(WD+'?'+urllib.parse.urlencode(params), headers=HDR)
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

id_to_name = {str(v): k for k,v in CRICINFO_IDS.items()}
id_list = list(id_to_name.keys())
cid_to_qid = {}

print(f'Step 1: Finding Wikidata Q-IDs for {len(id_list)} players...', flush=True)
for i, cid in enumerate(id_list):
    try:
        d = wd_get({'action':'query','list':'search','srsearch':f'haswbstatement:P2697={cid}','srlimit':1,'srprop':'','format':'json'})
        hits = d.get('query',{}).get('search',[])
        if hits:
            cid_to_qid[cid] = hits[0]['title']
    except Exception as e:
        pass
    if (i+1) % 50 == 0:
        print(f'  {i+1}/{len(id_list)} searched, {len(cid_to_qid)} found', flush=True)
    time.sleep(0.35)

print(f'Found {len(cid_to_qid)} Q-IDs. Fetching labels...', flush=True)

qid_to_label = {}
qids = list(cid_to_qid.values())
for i in range(0, len(qids), 50):
    chunk = qids[i:i+50]
    try:
        d = wd_get({'action':'wbgetentities','ids':'|'.join(chunk),'props':'labels','languages':'en','format':'json'})
        for qid, ent in d.get('entities',{}).items():
            label = ent.get('labels',{}).get('en',{}).get('value','')
            if label: qid_to_label[qid] = label
    except Exception as e:
        print(f'  [warn] {e}', flush=True)
    time.sleep(0.5)

full_names = {}
for cid, qid in cid_to_qid.items():
    label = qid_to_label.get(qid,'')
    abbrev = id_to_name[cid]
    if label and not label.startswith('Q') and len(label.split()) <= 6:
        full_names[abbrev] = label

print(f'Matched {len(full_names)}/{len(id_list)} players.')
OUT.write_text(json.dumps(full_names, indent=2, ensure_ascii=False))
print(f'Saved -> {OUT}')
unmatched = [id_to_name[c] for c in id_list if id_to_name[c] not in full_names]
if unmatched: print('Sample unmatched:', ', '.join(unmatched[:15]))
