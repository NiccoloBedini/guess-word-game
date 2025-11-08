#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Crea un dizionario parola->definizione usando Wiktionary (priorità) e Wikipedia (fallback).

Input:  words.json   (array JSON di stringhe)
Output: defs.json    (mappa JSON { parola: definizione })

Uso:
  python build_defs.py --input words.json --output defs.json
  python build_defs.py -i words.json -o defs.json --append   # aggiorna senza perdere voci già presenti
"""

import argparse, json, re, time, html, sys, unicodedata
from pathlib import Path
from typing import Optional, Dict
import requests
from requests.adapters import HTTPAdapter, Retry
from tqdm import tqdm
import random

WIKTIONARY_API = "https://it.wiktionary.org/w/api.php"
WIKIPEDIA_SUMMARY = "https://it.wikipedia.org/api/rest_v1/page/summary/{}"

UA = "EreditaGame/1.0"

# ---------- util ----------

def normalize_space(s: str) -> str:
    s = html.unescape(s)
    s = re.sub(r"\s+", " ", s, flags=re.UNICODE).strip()
    return s

def strip_markup(text: str) -> str:
    """
    Pulisce wikitext semplice:
      - rimuove template {{...}}
      - converte link [[target|label]] -> label, [[target]] -> target
      - leva '' corsivi/grassetti
      - rimuove <ref>...</ref> e tag HTML
    """
    # togli <ref> e altri tag
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"</?(nowiki|ref|math|code|span|div|br|small|i|b|u|sup|sub)[^>]*>", " ", text, flags=re.IGNORECASE)
    # template {{...}} (greedy bilanciato semplice)
    text = re.sub(r"\{\{[^{}]*\}\}", " ", text)
    # link [[target|label]] o [[target]]
    def _repl_link(m):
        body = m.group(1)
        if "|" in body:
            return body.split("|", 1)[1]
        return body
    text = re.sub(r"\[\[([^\[\]]+)\]\]", _repl_link, text)
    # corsivi/grassetti wiki
    text = text.replace("'''", "").replace("''", "")
    # entità HTML e spazi
    text = normalize_space(text)
    # rimuovi parentesi iniziali troppo enciclopediche
    text = re.sub(r"^\((?:[^()]{1,120})\)\s*", "", text)
    return text

def first_sentence(s: str, min_len: int = 20) -> str:
    """
    Estrae una frase corta e definitoria (fino al primo punto 'forte').
    """
    s = normalize_space(s)
    # taglia a fine prima frase
    m = re.search(r"(.+?[.!?])(\s|$)", s)
    if m and len(m.group(1)) >= min_len:
        return m.group(1)
    return s

def target_is_italian_section(title: str) -> bool:
    # euristica: accetta tutto; potresti filtrare caratteri non-lettera se vuoi
    return True

# ---------- fetchers ----------

class Http:
    def __init__(self, rate_per_sec=3):
        self.delay = 1.0 / max(rate_per_sec, 1)
        self.last = 0.0
        self.s = requests.Session()
        retries = Retry(
            total=5,
            backoff_factor=0.6,  # base backoff
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=frozenset(["GET"])
        )
        self.s.headers.update({"User-Agent": "EreditaGame/1.0 (you@example.com)"})
        self.s.mount("https://", HTTPAdapter(max_retries=retries))

    def get(self, url, **kwargs):
        # rate limit + jitter
        now = time.time()
        wait = self.delay - (now - self.last)
        if wait > 0:
            time.sleep(wait + random.uniform(0.1, 0.3))
        self.last = time.time()
        r = self.s.get(url, timeout=30, **kwargs)

        # Rispetta Retry-After manualmente se presente
        if r.status_code in (429, 503):
            ra = r.headers.get("Retry-After")
            if ra:
                try:
                    time.sleep(int(ra))
                except:
                    time.sleep(2)
        return r

def fetch_wiktionary_definition(http: Http, term: str) -> Optional[str]:
    """
    Strategia:
      1) action=parse + wikitext -> isola sezione 'Italiano' -> prendi la prima riga di definizione che inizia con '# '
         (escludi '#:' '#*' che sono esempi/citazioni)
      2) se fallisce, usa action=query&prop=extracts (plain) e prova a estrarre la prima frase utile
    """
    params = {
        "action": "parse",
        "format": "json",
        "prop": "wikitext|sections",
        "redirects": 1,
        "page": term
    }
    r = http.get(WIKTIONARY_API, params=params)
    if r.status_code == 200:
        data = r.json()
        if "error" not in data and "parse" in data:
            wikitext = data["parse"].get("wikitext", {}).get("*", "")
            if wikitext:
                # isola sezione Italiano
                sec_re = re.compile(r"==\s*Italiano\s*==(?P<body>.*?)(?:\n==[^=].*?==|\Z)", re.DOTALL | re.IGNORECASE)
                m = sec_re.search(wikitext)
                body = m.group("body") if m else wikitext  # fallback: tutto il testo
                # cerca prima definizione "# ..."
                lines = [ln.strip() for ln in body.splitlines()]
                for ln in lines:
                    if ln.startswith("#") and not ln.startswith(("#:", "#*", "##")):
                        cand = ln.lstrip("#").strip()
                        cand = strip_markup(cand)
                        cand = first_sentence(cand)
                        if len(cand) >= 12:
                            return cand

    # fallback: extracts plaintext
    params2 = {
        "action": "query",
        "format": "json",
        "prop": "extracts",
        "explaintext": 1,
        "redirects": 1,
        "titles": term
    }
    r2 = http.get(WIKTIONARY_API, params=params2)
    if r2.status_code == 200:
        data = r2.json()
        pages = data.get("query", {}).get("pages", {})
        for _, pg in pages.items():
            ext = pg.get("extract")
            if ext:
                # prendi righe “definitorie”, scarta intestazioni '='
                lines = [ln.strip() for ln in ext.splitlines() if ln.strip() and not ln.startswith("=")]
                if lines:
                    cand = first_sentence(lines[0])
                    cand = normalize_space(cand)
                    if len(cand) >= 12:
                        return cand
    return None

def fetch_wikipedia_summary(http: Http, term: str) -> Optional[str]:
    url = WIKIPEDIA_SUMMARY.format(requests.utils.quote(term.replace(" ", "_")))
    r = http.get(url, headers={"Accept": "application/json"})
    if r.status_code == 200:
        data = r.json()
        # ignora pagine di disambiguazione
        if data.get("type") in {"disambiguation"}:
            return None
        ext = data.get("extract") or data.get("description")
        if ext:
            cand = first_sentence(strip_markup(ext))
            if len(cand) >= 12:
                return cand
    return None

# ---------- pipeline ----------

def build_defs(words_path: Path, out_path: Path, append: bool = False, save_every: int = 50) -> Dict[str, str]:
    http = Http(rate_per_sec=4)
    words = json.loads(words_path.read_text(encoding="utf-8"))

    if not isinstance(words, list):
        raise ValueError("words.json deve contenere un array JSON di stringhe.")

    existing: Dict[str, str] = {}
    if append and out_path.exists():
        try:
            existing = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            existing = {}

    out: Dict[str, str] = dict(existing)

    pbar = tqdm(words, desc="Fetching", unit="word")
    updated = 0

    for idx, raw in enumerate(pbar):
        if not raw or not isinstance(raw, str):
            continue
        term = raw.strip()
        if term in out and out[term]:
            continue  # già presente

        # Normalizza forma base (senza alterare il lemma)
        if not target_is_italian_section(term):
            continue

        # 1) Wiktionary
        definition = fetch_wiktionary_definition(http, term)

        # 2) Wikipedia (fallback)
        if not definition:
            definition = fetch_wikipedia_summary(http, term)

        # 3) Post-fix: rimuovi “In linguistica,”, “È un/una …” troppo ridondante (soft)
        if definition:
            definition = re.sub(r"^(In\s+\w+istica,\s*)", "", definition, flags=re.IGNORECASE)
            definition = re.sub(r"^\b(E|È|E')\b\s+", "", definition, flags=re.IGNORECASE)
            definition = normalize_space(definition)

        if definition:
            out[term] = definition
            updated += 1
        else:
            # salva placeholder vuoto (o salta: qui manteniamo esplicito)
            out[term] = ""

        # salvataggio incrementale
        if save_every and (idx + 1) % save_every == 0:
            out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")

    # salvataggio finale
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Fatto: {len(out)} voci totali, {updated} aggiornate.")
    return out

# ---------- CLI ----------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", "--input", required=True, help="Percorso a words.json (array di parole)")
    ap.add_argument("-o", "--output", default="defs.json", help="Percorso file output (mappa parola->definizione)")
    ap.add_argument("--append", action="store_true", help="Aggiorna defs.json senza sovrascrivere voci già presenti")
    ap.add_argument("--save-every", type=int, default=50, help="Salva parziale ogni N parole (0 per disabilitare)")
    args = ap.parse_args()

    words_path = Path(args.input)
    out_path = Path(args.output)

    try:
        build_defs(words_path, out_path, append=args.append, save_every=args.save_every)
    except KeyboardInterrupt:
        print("\nInterrotto. Salvo lo stato parziale…")
        # Non serve altro: build_defs fa salvataggi incrementali.
        sys.exit(1)

if __name__ == "__main__":
    main()
