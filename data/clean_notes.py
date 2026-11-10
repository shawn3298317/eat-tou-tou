"""Clean poi_notes in the restaurant CSVs to branch/address/hours facts only.

Backports the cleanup applied to the Eat-Tou-Tou space's baked JSONs (which
unblocked the public share review): strips internal working prose, like-split
accounting, phone numbers, and sourcing references from the poi_notes field,
and neutralizes the Threads author handles in the source column so a future
batch sync from this repo cannot reintroduce the blocked identifiers.

Rules (poi_notes):
  - Drop any sentence/unit matching the dirty patterns below.
  - Keep branch lists, addresses, hours, founding year, awards, and other
    venue facts. Units that were purely working prose become empty.
  - The uniform `notes` boilerplate ("Seeded from Threads replies; ...")
    is generic provenance, not a personal identifier, and is left alone.
  - All other columns are left byte-identical.

Usage: python3 data/clean_notes.py   (run from ~/workspace/taipei-eats)
"""
import csv
import re
import sys

# Case-insensitive substrings that mark a unit as working/process prose.
DIRTY_SUBSTRINGS = [
    'task hint', 'batch hint', 'as hinted', ' hint', 'hint',
    'orchestrator',
    'sourced from', 'meta ai', 'thread summary', 'second-hand',
    'direct user mention', 'in the thread', "the thread's", 'thread',
    'shared-like', 'likes across', 'likes in one', 'price band estimated',
    'price unknown', 'not in evidence', 'is an estimate',
    'no signature dish named', 'no single signature dish named',
    'candidate name', 'is ambiguous', 'mis-transcription',
    'duplicate_of', 'outside my slice', 'unconfirmed',
    'separate candidate', 'may refer to this same',
    'real name is', 'real shop name is',
    'no such branch', 'was incorrect', 'appears incorrect',
    'not found', 'sources differ', 'confirms the move',
    'confirm the move',
    'geocoder', 'geocode', 'address_o',
    'used as canonical', 'used as representative', 'representative store',
    'no branch specified',
    'negative mention', 'in one comment',
    'facebook', 'instagram',
    'tiktok', 'blog', 'youtube',
    '無來源', 'must_try', '留空', '未採信', '疑為', '待確認', '來源',
    'canonical', '座標取自',
    '代表店とした', '支店未指定',
]

# Regexes that mark a unit as dirty.
DIRTY_RES = [
    re.compile(r'\bp\d+-\d+\b'),                       # page-comment refs (p6-43)
    re.compile(r'phone\s*\d', re.I),                   # phone + digits
    # Phone numbers. No \b before the leading 0: in CJK text the preceding
    # char (e.g. 話 in 電話02-...) is a word char in Python, so \b fails.
    # Lookarounds keep it from matching inside longer digit runs.
    re.compile(r'(?<!\d)0\d[-\s]?\d{3,4}[-\s]?\d{4}(?!\d)'),
    re.compile(r'(?<!\d)\d{2,3}-\d{3,4}-\d{4}(?!\d)'),
    re.compile(r'@\w'),                                # @handle
    re.compile(r'https?://'),                          # URL
    re.compile(r'[\w.+-]+@[\w-]+\.[\w.]+'),            # email
    re.compile(r'FB'),                                 # Facebook abbreviation
    re.compile(r'IG'),                                 # Instagram abbreviation
    re.compile(r'^採\d'),                              # lone "adopted <addr>" fragment
]

# Pre-strip: like-split accounting suffix, wherever it sits.
SUFFIX_RE = re.compile(r'\s*price band estimated from price_level[^;。]*')
# Pre-strip: parentheticals that reference the thread / hints.
PAREN_RE = re.compile(r'\s*\([^)]*(?:thread|hint)[^)]*\)', re.I)
# Neutralize author handle in source: threads:<handle>-YYYY-MM-DD -> threads:YYYY-MM-DD
SOURCE_RE = re.compile(r'threads:[^-\s]+-(\d{4}-\d{2}-\d{2})')

UNIT_SPLIT_RE = re.compile(r';\s*|。\s*|\.\s+')


def is_dirty(unit):
    low = unit.lower()
    if any(s.lower() in low for s in DIRTY_SUBSTRINGS):
        return True
    return any(p.search(unit) for p in DIRTY_RES)


def clean_notes(text):
    if not text or not text.strip():
        return ''
    text = SUFFIX_RE.sub('', text)
    text = PAREN_RE.sub('', text)
    units = [u.strip().strip(' .;。') for u in UNIT_SPLIT_RE.split(text)]
    kept = [u for u in units if u and not is_dirty(u)]
    return '; '.join(kept)


def clean_source(text):
    return SOURCE_RE.sub(r'threads:\1', text or '')


def main():
    for path in ['data/restaurants.csv', 'data/tokyo_restaurants.csv']:
        with open(path, newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
            fieldnames = list(rows[0].keys()) if rows else []
        # Keep a copy of the originals for the byte-identical check.
        with open(path, newline='', encoding='utf-8') as f:
            orig = list(csv.DictReader(f))
        changed_notes = 0
        emptied = 0
        changed_source = 0
        for r, o in zip(rows, orig):
            new_notes = clean_notes(r.get('poi_notes') or '')
            if new_notes != (o.get('poi_notes') or ''):
                changed_notes += 1
                if not new_notes:
                    emptied += 1
            r['poi_notes'] = new_notes
            new_src = clean_source(r.get('source') or '')
            if new_src != (o.get('source') or ''):
                changed_source += 1
            r['source'] = new_src
            # All other columns must be untouched.
            for col in fieldnames:
                if col not in ('poi_notes', 'source'):
                    assert r[col] == o[col], f'{path} {r["id"]} {col} changed!'
        with open(path, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=fieldnames)
            w.writeheader()
            w.writerows(rows)
        print(f'{path}: {len(rows)} rows, poi_notes changed={changed_notes} '
              f'(emptied={emptied}), source changed={changed_source}')


if __name__ == '__main__':
    main()
