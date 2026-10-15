#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📅 ROBOT QUOTIDIENNE
Va chercher tout seul les derniers articles sur la Star Academy (Google Actualités),
les range par jour et les enregistre dans quotidienne.json.
Rien à installer : uniquement des outils déjà inclus dans Python.
"""
import json
import os
import re
import unicodedata
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from email.utils import parsedate_to_datetime
from zoneinfo import ZoneInfo

PARIS = ZoneInfo("Europe/Paris")
FICHIER = "quotidienne.json"
DEBUT_SAISON = datetime(2026, 10, 10, tzinfo=PARIS)
JOURS_GARDES = 30      # on garde 30 jours d'articles
MAX_PAR_JOUR = 15      # 15 articles maximum par jour

ELEVES = ["Amel", "Antoine", "Brieuc", "Cameron", "Elija", "Félix", "Isabella", "Khalil",
          "Kylian", "Leeloo", "Maud", "Mélina", "Morgan", "Noémie", "Tracy", "Ydriss", "Zoé"]

RECHERCHES = [
    '"Star Academy" quotidienne',
    '"Star Academy" évaluations',
    '"Star Academy" nominés',
    '"Star Academy" château',
    '"Star Academy" Mosimann',
    '"Star Academy" prime',
]

# (emoji, thème, mots-clés) — le 1er thème qui correspond gagne
CATEGORIES = [
    ("💥", "Départ", r"abandon|quitte|quitter|depart|claque la porte|s'en va"),
    ("❌", "Élimination", r"elimin"),
    ("⚠️", "Nominations", r"nomin|nomme"),
    ("🛡️", "Immunité", r"immun|sauve"),
    ("🎤", "Évaluations", r"evaluation|evalue"),
    ("💃", "Danse", r"danse|chore|jenvrin"),
    ("📊", "Audiences", r"audience|telespectateur"),
    ("🎶", "Prime", r"\bprime\b|invite"),
    ("😢", "Émotions", r"larme|pleur|craque|emu|effondr|tension|clash|dispute|colere"),
    ("💕", "Love", r"couple|bisou|rapproch|flirt|amoureu|crush"),
]
DEFAUT = ("📺", "Château")


def norm(s):
    s = unicodedata.normalize("NFD", str(s or "").replace("’", "'"))
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower()


def cle_de(titre):
    return re.sub(r"[^a-z0-9]+", "", norm(titre))[:80]


def categorie(n):
    for emoji, cat, rx in CATEGORIES:
        if re.search(rx, n):
            return emoji, cat
    return DEFAUT


def eleves_dans(n):
    n = n.replace("amel bent", "")  # la chanteuse, pas notre Amel 😉
    return [e for e in ELEVES if re.search(r"(?<![a-z])" + re.escape(norm(e)) + r"(?![a-z])", n)]


def lire_flux(q):
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode(
        {"q": q + " when:7d", "hl": "fr", "gl": "FR", "ceid": "FR:fr"})
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (robot fan Star Academy)"})
    with urllib.request.urlopen(req, timeout=25) as r:
        data = r.read()
    return ET.fromstring(data).findall("./channel/item")


def analyser(it):
    titre = (it.findtext("title") or "").strip()
    lien = (it.findtext("link") or "").strip()
    s = it.find("source")
    source = (s.text or "").strip() if s is not None and s.text else ""
    if source and titre.endswith(" - " + source):
        titre = titre[: -len(" - " + source)].strip()
    elif not source and " - " in titre:
        titre, source = [x.strip() for x in titre.rsplit(" - ", 1)]
    if not titre or not lien.startswith("http"):
        return None
    n = norm(titre)
    if not re.search(r"star ?ac", n):
        return None
    # on écarte les anciennes saisons
    if re.search(r"\b20(?:0\d|1\d|2[0-5])\b", n) or re.search(r"saison (?:[1-9]|1[0-3])\b", n):
        return None
    try:
        d = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(PARIS)
    except Exception:
        return None
    if d < DEBUT_SAISON:
        return None
    emoji, cat = categorie(n)
    return {
        "cle": cle_de(titre), "titre": titre, "source": source, "lien": lien,
        "date": d.strftime("%Y-%m-%d"), "heure": d.strftime("%Hh%M"),
        "ts": d.isoformat(timespec="seconds"), "emoji": emoji, "cat": cat,
        "eleves": eleves_dans(n),
    }


def charger_ancien():
    if not os.path.exists(FICHIER):
        return {}
    try:
        with open(FICHIER, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def main():
    ancien = charger_ancien()
    tous = {}
    for j in ancien.get("jours", []):
        for a in j.get("articles", []):
            c = a.get("cle") or cle_de(a.get("titre", ""))
            if c:
                a["cle"] = c
                tous[c] = a

    nb_ok = 0
    for q in RECHERCHES:
        try:
            items = lire_flux(q)
            nb_ok += 1
        except Exception as e:
            print("⚠️ Recherche ratée :", q, "→", e)
            continue
        for it in items:
            a = analyser(it)
            if a and a["cle"] not in tous:
                tous[a["cle"]] = a

    if nb_ok == 0:
        print("😕 Aucune recherche n'a marché, je garde l'ancien fichier.")
        return

    limite = (datetime.now(PARIS) - timedelta(days=JOURS_GARDES)).strftime("%Y-%m-%d")
    par_jour = {}
    for a in tous.values():
        if a.get("date", "") < limite:
            continue
        par_jour.setdefault(a["date"], []).append(a)

    jours = []
    for d in sorted(par_jour, reverse=True):
        arts = sorted(par_jour[d], key=lambda a: a.get("ts", ""), reverse=True)[:MAX_PAR_JOUR]
        jours.append({"date": d, "articles": arts})

    if jours == ancien.get("jours"):
        print("✅ Rien de nouveau.")
        return

    sortie = {"maj": datetime.now(PARIS).isoformat(timespec="seconds"),
              "source": "Google Actualités", "jours": jours}
    with open(FICHIER, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)
    print(f"✅ {sum(len(j['articles']) for j in jours)} articles sur {len(jours)} jours.")


if __name__ == "__main__":
    main()
