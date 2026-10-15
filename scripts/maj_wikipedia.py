# -*- coding: utf-8 -*-
# 🤖 Robot Star Academy 2026 : lit Wikipédia et met à jour data.json
import datetime
import json
import re
import unicodedata
from pathlib import Path

import requests
from bs4 import BeautifulSoup

API = "https://fr.wikipedia.org/w/api.php"
TITRES = ["Saison 14 de Star Academy", "Star Academy (saison 14)", "Star Academy saison 14", "Star Academy 2026"]
FICHIER = Path(__file__).resolve().parent.parent / "data.json"
ENTETES = {"User-Agent": "StarAcFanSite/1.0 (https://simocio59-cyber.github.io/Star-Academy-/)"}

ELEVES = ["Amel", "Antoine", "Brieuc", "Cameron", "Elija", "Félix", "Isabella", "Khalil", "Kylian",
          "Leeloo", "Maud", "Mélina", "Morgan", "Noémie", "Tracy", "Ydriss", "Zoé"]
MOIS = {"janvier": 1, "fevrier": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6, "juillet": 7,
        "aout": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12}
ORDINAUX = {"premier": 1, "deuxieme": 2, "second": 2, "troisieme": 3, "quatrieme": 4, "cinquieme": 5,
            "sixieme": 6, "septieme": 7, "huitieme": 8, "neuvieme": 9, "dixieme": 10, "onzieme": 11,
            "douzieme": 12, "treizieme": 13, "quatorzieme": 14, "quinzieme": 15, "seizieme": 16,
            "dix-septieme": 17}
CLES = ["nomines", "sauve", "elimine", "abandon", "immunise", "top3", "finalistes", "gagnant"]
REGLES = [
    ("elimine", r"\belimine(?:e|s|es)?\b"),
    ("abandon", r"\b(?:abandonne\w*|quitte (?:l'aventure|le chateau|l'emission|definitivement))"),
    ("immunise", r"\bimmunise(?:e|s|es)?\b"),
    ("sauve", r"\bsauve(?:e|s|es)?\b"),
    ("nomines", r"\bnomine(?:e|s|es)?\b"),
    ("gagnant", r"\b(?:remporte la (?:saison|competition|finale|star academy)|vainqueur|gagnante? de la saison)"),
]
EXCLUS = ("eleve", "tous", "toutes", "prof", "academicien", "chorale", "troupe", "danseur")


# ---------- 🧰 Outils ----------
def norm(s):
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", s.replace("\u2019", "'")).lower().strip()


def nettoie(s):
    s = re.sub(r"\s+", " ", s or "").strip()
    s = re.sub(r"\s+([,.)])", r"\1", s)
    return re.sub(r"

$$
\s+", "(", s)


def ajoute(liste, x):
    if x and x not in liste:
        liste.append(x)


def unique(liste):
    out = []
    for x in liste:
        ajoute(out, x)
    return out


def eleves_dans(texte):
    t = norm(texte)
    trouves = []
    for e in ELEVES:
        m = re.search(r"\b" + re.escape(norm(e)) + r"\b", t)
        if m:
            trouves.append((m.start(), e))
    return [e for _, e in sorted(trouves)]


def date_iso(texte):
    m = re.search(r"(\d{1,2})(?:er)?\s+(" + "|".join(MOIS) + r")\s+(20\d\d)", norm(texte))
    if not m:
        return None
    return f"{int(m.group(3)):04d}-{MOIS[m.group(2)]:02d}-{int(m.group(1)):02d}"


def num_prime(titre):
    t = norm(titre)
    m = (re.search(r"\bprime\s*(?:n\s*[°ºo]\s*)?(\d{1,2})\b", t)
         or re.search(r"\b(\d{1,2})\s*(?:er|e|eme)?\s+prime\b", t)
         or re.search(r"\bsemaine\s*(\d{1,2})\b", t))
    if m:
        n = int(m.group(1))
        return n if 1 <= n <= 17 else None
    m = re.search(r"\b(" + "|".join(sorted(ORDINAUX, key=len, reverse=True)) + r")\s+prime\b", t)
    if m:
        return ORDINAUX[m.group(1)]
    if re.search(r"\bfinale\b", t) and "demi" not in t:
        return 17
    return None


def entier(v):
    m = re.search(r"\d+", str(v or ""))
    return max(1, min(int(m.group()), 50)) if m else 1


def grille(table):
    """Transforme un tableau Wikipédia en liste de lignes (gère les cases fusionnées)."""
    lignes, attente = [], {}
    for tr in table.find_all("tr"):
        if tr.find_parent("table") is not table:
            continue
        cellules = tr.find_all(["th", "td"], recursive=False)
        ligne, col, i = [], 0, 0
        while i < len(cellules) or col in attente:
            if col in attente:
                txt, reste = attente[col]
                ligne.append(txt)
                if reste <= 1:
                    del attente[col]
                else:
                    attente[col] = (txt, reste - 1)
                col += 1
                continue
            c = cellules[i]
            i += 1
            txt = nettoie(c.get_text(" "))
            rs, cs = entier(c.get("rowspan")), entier(c.get("colspan"))
            for _ in range(cs):
                ligne.append(txt)
                if rs > 1:
                    attente[col] = (txt, rs - 1)
                col += 1
        lignes.append(ligne)
    return lignes


# ---------- 🌐 Wikipédia ----------
def api(**params):
    params.update(format="json", formatversion=2)
    r = requests.get(API, params=params, headers=ENTETES, timeout=30)
    r.raise_for_status()
    return r.json()


def bonne_page(titre):
    return "star academy" in norm(titre) and ("14" in titre or "2026" in titre)


def charger_page():
    essais = list(TITRES)
    try:
        res = api(action="query", list="search", srsearch="Star Academy saison 14 2026", srlimit=5)
        essais += [x["title"] for x in res.get("query", {}).get("search", []) if bonne_page(x["title"])]
    except Exception as e:
        print("Recherche impossible :", e)
    for t in essais:
        try:
            d = api(action="parse", page=t, prop="text", redirects=1, disableeditsection=1)
        except Exception as e:
            print("Essai raté :", t, e)
            continue
        if "parse" in d and bonne_page(d["parse"]["title"]):
            print("📖 Page trouvée :", d["parse"]["title"])
            return d["parse"]["title"], d["parse"]["text"]
    return None, None


# ---------- 🔎 Lecture des tableaux ----------
def invites_de(texte):
    t = texte
    for e in ELEVES:
        t = re.sub(r"\b" + re.escape(e) + r"\b", ",", t, flags=re.I)
    res = []
    for m in re.split(r"\s*(?:,|;|&|\+|/|\bavec\b|\bfeat\.?|\(|
$$

)\s*", t):
        m = re.sub(r"^(?:et|avec)\s+", "", m.strip(" -–:"))
        if len(m) >= 3 and m[0].isupper() and not any(x in norm(m) for x in EXCLUS):
            res.append(m)
    return res


def chansons_de(table):
    g = grille(table)
    if len(g) < 2:
        return [], []
    h = [norm(x) for x in g[0]]

    def col(mots, sauf=()):
        for i, x in enumerate(h):
            if any(m in x for m in mots) and not any(s in x for s in sauf):
                return i
        return None

    ce = col(("eleve", "candidat", "academicien"))
    if ce is None:
        ce = col(("interprete",), ("orig",))
    ct = col(("chanson", "titre"))
    ca = col(("artiste", "original"), ("eleve",))
    cp = col(("prime",), ("chanson", "titre"))
    if ce is None or ct is None or ce == ct:
        return [], []
    out, inv = [], []
    for r in g[1:]:
        if len(r) <= max(ce, ct) or r == g[0]:
            continue
        titre = r[ct].strip(' "«»“”')
        el = eleves_dans(r[ce])
        if not titre:
            continue
        if el:
            c = {"eleves": el, "titre": titre,
                 "artiste": r[ca] if ca is not None and ca < len(r) and ca != ce else ""}
            if cp is not None and cp < len(r):
                n = num_prime("prime " + r[cp])
                if n:
                    c["num"] = n
            out.append(c)
        inv += invites_de(r[ce])
    return out, inv


def categories(cellule):
    c, res = norm(cellule), []
    if "elimin" in c: res.append("elimine")
    if "abandon" in c or "quitt" in c: res.append("abandon")
    if "gagn" in c or "vainq" in c: res.append("gagnant")
    if "finalist" in c: res.append("finalistes")
    if "immun" in c: res.append("immunise")
    if "sauv" in c: res.append("sauve")
    if "nomin" in c: res.append("nomines")
    return res


def tableau_recap(table):
    """Tableau récapitulatif : une ligne par élève, une colonne par prime."""
    g = grille(table)
    debut = next((i for i, r in enumerate(g) if r and len(eleves_dans(r[0])) == 1), None)
    if not debut:
        return {}
    lignes = [r for r in g[debut:] if r and len(eleves_dans(r[0])) == 1]
    entetes = g[:debut]
    tout = norm(" ".join(" ".join(r) for r in entetes))
    if len(lignes) < 5 or ("prime" not in tout and "semaine" not in tout):
        return {}
    cols = {}
    for j in range(1, max(len(r) for r in g)):
        h = " ".join(r[j] for r in entetes if j < len(r))
        n = num_prime(h)
        if n is None:
            der = entetes[-1][j].strip() if j < len(entetes[-1]) else ""
            if re.fullmatch(r"\d{1,2}", der) and 1 <= int(der) <= 17:
                n = int(der)
        if n:
            cols[j] = n
    res = {}
    for r in lignes:
        nom = eleves_dans(r[0])[0]
        for j, n in cols.items():
            if j < len(r):
                for cat in categories(r[j]):
                    ajoute(res.setdefault(n, {}).setdefault(cat, []), nom)
    return res


def tableau_statuts(table):
    g = grille(table)
    if len(g) < 6:
        return {}
    h = [norm(x) for x in g[0]]
    cs = next((i for i, x in enumerate(h) if any(m in x for m in ("statut", "resultat", "parcours", "situation"))), None)
    if cs is None:
        return {}
    res = {}
    for r in g[1:]:
        if not r or cs >= len(r):
            continue
        noms = eleves_dans(r[0]) or (eleves_dans(r[1]) if len(r) > 1 else [])
        if len(noms) == 1 and r[cs]:
            res[noms[0]] = r[cs]
    return res if len(res) >= 5 else {}


def analyse_phrases(p):
    for texte in p["_txt"]:
        for phrase in re.split(r"(?<=[.;!?])\s+|\s+(?:tandis que|alors que|mais)\s+", texte):
            t = norm(phrase)
            noms = sorted((m.start(), e) for e in ELEVES
                          for m in re.finditer(r"\b" + re.escape(norm(e)) + r"\b", t))
            if not noms:
                continue
            coups = sorted((m.start(), cat) for cat, rx in REGLES for m in re.finditer(rx, t))
            prec = -1
            for pos, cat in coups:
                for npos, e in noms:
                    if prec < npos < pos:
                        ajoute(p[cat], e)
                prec = pos
            m = re.search(r"top\s*3|trois meilleur", t)
            if m:
                for npos, e in noms:
                    if npos > m.start() and len(p["top3"]) < 3:
                        ajoute(p["top3"], e)
            if "finaliste" in t:
                for _, e in noms:
                    ajoute(p["finalistes"], e)


# ---------- 🧩 Analyse complète ----------
def analyser(html):
    soup = BeautifulSoup(html, "html.parser")
    for s in soup.select("sup.reference, style, script, .mw-editsection, .noprint"):
        s.decompose()
    racine = soup.select_one(".mw-parser-output") or soup
    primes, section_de = {}, {}

    def P(n):
        if n not in primes:
            primes[n] = {"num": n, **{k: [] for k in CLES}, "chansons": [], "wiki": [],
                         "invites": [], "date": None, "_txt": []}
        return primes[n]

    cur, niv = None, 0
    for el in racine.find_all(recursive=False):
        h = None
        if el.name in ("h2", "h3", "h4", "h5"):
            h = el
        elif el.name == "div" and "mw-heading" in (el.get("class") or []):
            h = el.find(["h2", "h3", "h4", "h5"])
        if h is not None:
            niveau, titre = int(h.name[1]), nettoie(h.get_text(" "))
            n = num_prime(titre)
            if n:
                cur, niv = n, niveau
                if date_iso(titre):
                    P(n)["date"] = date_iso(titre)
            elif cur and niveau <= niv:
                cur = None
            continue
        for tb in ([el] if el.name == "table" else el.find_all("table")):
            section_de[id(tb)] = cur
        if not cur:
            continue
        p = P(cur)
        textes = [el] if el.name == "p" else (el.find_all("li") if el.name in ("ul", "ol", "dl") else [])
        for t in textes:
            txt = nettoie(t.get_text(" "))
            if not txt:
                continue
            p["_txt"].append(txt)
            if el.name == "p" and len(txt) > 30:
                p["wiki"].append(txt)
            m = re.search(r"invit\w*\s*(?:d'honneur\s*)?:\s*(.+)", txt, re.I)
            if m:
                p["invites"] += [x.strip(" .") for x in re.split(r",|;", m.group(1)) if x.strip(" .")]
            if not p["date"] and "samedi" in norm(txt):
                nt = norm(txt)
                p["date"] = date_iso(nt[nt.index("samedi"):])

    recap, statuts = {}, {}
    for tb in racine.find_all("table"):
        for n, cats in tableau_recap(tb).items():
            for cat, noms in cats.items():
                for e in noms:
                    ajoute(recap.setdefault(n, {}).setdefault(cat, []), e)
        statuts.update(tableau_statuts(tb))
        ch, inv = chansons_de(tb)
        for c in ch:
            n = c.pop("num", None) or section_de.get(id(tb))
            if n:
                P(n)["chansons"].append(c)
        if inv and section_de.get(id(tb)):
            P(section_de[id(tb)])["invites"] += inv

    for n in sorted(set(primes) | set(recap)):
        p = P(n)
        analyse_phrases(p)
        if n in recap:
            for cat in ("nomines", "sauve", "elimine", "abandon", "immunise", "finalistes", "gagnant"):
                p[cat] = recap[n].get(cat, [])

    for e in ELEVES:
        if e in statuts:
            continue
        for n in sorted(primes):
            p = primes[n]
            if e in p["gagnant"]:
                statuts[e] = "Gagnant(e) 🏆"
            elif e in p["elimine"]:
                statuts[e] = f"Éliminé(e) au prime {n}"
                break
            elif e in p["abandon"]:
                statuts[e] = f"Abandon (prime {n})"
                break
        statuts.setdefault(e, "En compétition")

    sortie, calendrier, vus = [], [], set()
    for n in sorted(primes):
        p = primes[n]
        for k in CLES + ["invites"]:
            p[k] = unique(p[k])
        chans = []
        for c in p["chansons"]:
            cle = (tuple(c["eleves"]), c["titre"])
            if cle not in vus:
                vus.add(cle)
                chans.append(c)
        item = {"num": n, **{k: p[k] for k in CLES}, "chansons": chans, "wiki": p["wiki"][:8], "invites": p["invites"]}
        if any(v for k, v in item.items() if k != "num"):
            sortie.append(item)
        if p["date"]:
            calendrier.append({"num": n, "date": p["date"], "ok": True, "invites": p["invites"]})

    return {"statuts": statuts, "primes": sortie, "calendrier": calendrier, "actusAuto": actus(sortie)}


def actus(primes):
    L = []
    for p in sorted(primes, key=lambda x: -x["num"]):
        n, f = p["num"], (lambda x: ", ".join(x))
        if p["gagnant"]: L.append(f"🏆 {f(p['gagnant'])} remporte la Star Academy 2026 !")
        if p["elimine"]: L.append(f"❌ Prime {n} : {f(p['elimine'])} quitte le château.")
        if p["abandon"]: L.append(f"🚪 Prime {n} : abandon de {f(p['abandon'])}.")
        if p["sauve"]: L.append(f"🙌 Prime {n} : {f(p['sauve'])} sauvé(e) !")
        if p["nomines"]: L.append(f"⚠️ Prime {n} : nominés {f(p['nomines'])}.")
        if p["immunise"]: L.append(f"🛡️ Prime {n} : {f(p['immunise'])} immunisé(e).")
        if p["top3"]: L.append(f"🏅 Prime {n} : top 3 des évaluations {f(p['top3'])}.")
        if len(L) >= 6:
            break
    return L[:6]


# ---------- 🚀 Programme ----------
def main():
    ancien = {}
    if FICHIER.exists():
        try:
            ancien = json.loads(FICHIER.read_text("utf-8"))
        except Exception:
            ancien = {}
    try:
        titre, html = charger_page()
    except Exception as e:
        print("⚠️ Wikipédia injoignable :", e)
        return
    if not html:
        print("⚠️ Page introuvable : on garde l'ancien data.json")
        return
    try:
        nouveau = analyser(html)
    except Exception as e:
        print("⚠️ Erreur de lecture :", e)
        return
    nouveau["source"] = "https://fr.wikipedia.org/wiki/" + titre.replace(" ", "_")
    if not nouveau["primes"] and ancien.get("primes"):
        print("⚠️ Rien trouvé cette fois : on garde l'ancien data.json")
        return

    def comparer(d):
        return json.dumps({k: v for k, v in d.items() if k != "maj"}, sort_keys=True, ensure_ascii=False)

    if comparer(nouveau) == comparer(ancien):
        print("✅ Rien de neuf")
        return
    nouveau["maj"] = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
    FICHIER.write_text(json.dumps(nouveau, ensure_ascii=False, indent=1), "utf-8")
    print("✅ data.json mis à jour :", len(nouveau["primes"]), "primes")


if __name__ == "__main__":
    main()
