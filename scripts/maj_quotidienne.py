#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
📅 Robot « Quotidienne auto » — Star Academy 2026 (TF1)

1. Il lit en coulisse les titres d'actu (Google News). Rien de ça n'est affiché sur le site.
2. Il demande à l'IA gratuite de GitHub (GitHub Models) d'écrire des résumés simples.
3. Il enregistre le résultat dans quotidienne.json :
   {"maj", "empreinte", "jours": [{"date", "titre", "points"}], "aRetenir": [{"t", "jusqu"}]}

Si quelque chose rate (pas d'actu, IA en panne...), l'ancien fichier est gardé tel quel.
"""

import email.utils
import hashlib
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

FICHIER = "quotidienne.json"
PARIS = ZoneInfo("Europe/Paris")
API = "https://models.github.ai/inference/chat/completions"
# Si le 1er modèle ne répond pas, le robot essaie le suivant
MODELES = ["openai/gpt-4o-mini", "openai/gpt-4.1-mini", "openai/gpt-5-mini"]

FENETRE = 3       # l'IA retravaille aujourd'hui + les 3 jours d'avant
GARDER = 40       # nombre de jours de résumés gardés dans le fichier
MAX_TITRES = 60   # titres envoyés à l'IA (reste sous la limite gratuite)

ELEVES = ["Amel", "Antoine", "Brieuc", "Cameron", "Elija", "Félix", "Isabella",
          "Khalil", "Kylian", "Leeloo", "Maud", "Mélina", "Morgan", "Noémie",
          "Tracy", "Ydriss", "Zoé"]

RECHERCHES = [
    "Star Academy quotidienne",
    "Star Academy château élèves",
    "Star Academy nominés",
    "Star Academy évaluations",
    "Star Academy Mosimann",
    "Star Academy prime TF1",
]

JOURS_FR = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
DATE_OK = re.compile(r"^\d{4}-\d{2}-\d{2}$")

SYSTEME = (
    "Tu aides un fan à suivre la Star Academy 2026 sur TF1 (château de Dammarie-les-Lys, "
    "le directeur s'appelle Mosimann). Tu écris en français très simple, comme un pote qui "
    "raconte : phrases courtes, pas de jargon. "
    "Tu utilises UNIQUEMENT les titres fournis et les résumés déjà écrits : tu n'inventes rien. "
    "Si une info n'est pas confirmée (question, rumeur, « pourrait »), tu le dis clairement "
    "(« peut-être », « pas encore confirmé »). "
    "Jamais de nom de journal, jamais de lien, jamais « selon un article ». "
    "Prénoms des élèves, à écrire exactement comme ça : " + ", ".join(ELEVES) + ". "
    "Tu réponds uniquement avec un objet JSON valide."
)


def lire(url, donnees=None, entetes=None, delai=30):
    req = urllib.request.Request(url, data=donnees, headers=entetes or {})
    with urllib.request.urlopen(req, timeout=delai) as r:
        return r.read()


def nettoyer(txt, maxi):
    txt = re.sub(r"https?://\S+", "", str(txt or ""))
    txt = re.sub(r"\s+", " ", txt).strip()
    return txt[:maxi].strip()


def charger_ancien():
    try:
        with open(FICHIER, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def titres_actu(maintenant):
    """Récupère les titres récents. Ils servent juste à nourrir l'IA."""
    limite = maintenant - timedelta(days=FENETRE + 1)
    vus, liste = set(), []
    for q in RECHERCHES:
        url = ("https://news.google.com/rss/search?q="
               + urllib.parse.quote(q + " when:5d")
               + "&hl=fr&gl=FR&ceid=FR:fr")
        try:
            racine = ET.fromstring(lire(url, entetes={"User-Agent": "Mozilla/5.0"}))
        except Exception as e:
            print("⚠️ Recherche ratée :", q, "→", e)
            continue
        for it in racine.iter("item"):
            titre = (it.findtext("title") or "").strip()
            source = (it.findtext("source") or "").strip()
            if source and titre.endswith(" - " + source):
                titre = titre[: -(len(source) + 3)].strip()
            bas = titre.lower()
            if "star ac" not in bas and not any(n.lower() in bas for n in ELEVES):
                continue
            try:
                quand = email.utils.parsedate_to_datetime(it.findtext("pubDate") or "")
            except Exception:
                continue
            if quand.tzinfo is None:
                quand = quand.replace(tzinfo=timezone.utc)
            quand = quand.astimezone(PARIS)
            if quand < limite:
                continue
            cle = re.sub(r"\W+", "", bas)[:70]
            if not cle or cle in vus:
                continue
            vus.add(cle)
            liste.append((quand, titre))
    liste.sort(key=lambda x: x[0], reverse=True)
    return liste[:MAX_TITRES]


def message_ia(titres, anciens_jours, ancien_ar, aujourd, debut, prime):
    deja = "\n".join(
        "- " + str(j["date"]) + " « " + str(j.get("titre", "")) + " » : "
        + " | ".join(str(p) for p in j.get("points", []))
        for j in sorted(anciens_jours, key=lambda x: str(x["date"]))
    ) or "(aucun)"
    ar = "\n".join(
        "- " + str(x["t"]) + " (jusqu'au " + str(x.get("jusqu", "")) + ")" for x in ancien_ar
    ) or "(rien)"
    tt = "\n".join("- [" + q.strftime("%Y-%m-%d %H:%M") + "] " + t for q, t in titres)
    jour = JOURS_FR[aujourd.weekday()]
    auj, deb, pri = aujourd.isoformat(), debut.isoformat(), prime.isoformat()
    return f"""Nous sommes le {jour} {auj}. Prochain prime : samedi {pri} à 21h10.
La quotidienne passe à 17h30 en semaine, 17h15 le samedi et 16h05 le dimanche.
Un titre publié le soir parle en général de la quotidienne du jour ; un titre publié le matin parle souvent de celle de la veille.
Range chaque info au jour de la diffusion dont elle parle.

RÉSUMÉS DÉJÀ ÉCRITS (garde-les et complète-les, sauf si un titre plus récent les contredit) :
{deja}

« À RETENIR » ACTUEL :
{ar}

TITRES D'ACTU RÉCENTS (date et heure de Paris) :
{tt}

Réponds avec exactement ce format JSON :
{{"jours": [{{"date": "AAAA-MM-JJ", "titre": "titre court, 8 mots maxi", "points": ["un fait simple par phrase"]}}],
 "aRetenir": [{{"t": "info importante, une phrase courte", "jusqu": "AAAA-MM-JJ"}}]}}

Règles :
- "jours" : seulement des dates entre {deb} et {auj}, de 2 à 7 points par jour. Pas de jour dont on ne sait rien.
- Une quotidienne pas encore diffusée n'a pas eu lieu : écris plutôt « réponse attendue ce soir ».
- "aRetenir" : de 0 à 5 infos vraiment importantes en ce moment (élève qui veut partir ou qui part, nominés, top 3, immunité, éliminé, invités du prime...). Donne la liste complète et à jour : enlève ce qui est réglé ou dépassé.
- "jusqu" = dernier jour où l'info sert encore (souvent le jour du prime), jamais avant {auj}.
- Pas de rumeurs sur la vie privée en dehors de l'émission."""


def demander_ia(message):
    jeton = os.environ.get("GITHUB_TOKEN", "")
    if not jeton:
        raise RuntimeError("GITHUB_TOKEN absent (regarde le fichier .yml)")
    erreur = None
    for modele in MODELES:
        corps = {
            "model": modele,
            "messages": [{"role": "system", "content": SYSTEME},
                         {"role": "user", "content": message}],
            "response_format": {"type": "json_object"},
        }
        if "gpt-5" not in modele:
            corps["temperature"] = 0.2
        try:
            brut = lire(API, donnees=json.dumps(corps).encode("utf-8"), entetes={
                "Authorization": "Bearer " + jeton,
                "Content-Type": "application/json",
                "Accept": "application/json",
            }, delai=120)
            texte = json.loads(brut)["choices"][0]["message"]["content"] or ""
            texte = re.sub(r"^```(?:json)?\s*|\s*```$", "", texte.strip())
            resultat = json.loads(texte)
            if not isinstance(resultat, dict):
                raise ValueError("réponse pas au bon format")
            print("🤖 Résumés écrits par", modele)
            return resultat
        except urllib.error.HTTPError as e:
            erreur = f"{modele} → erreur {e.code} : {e.read().decode('utf-8', 'replace')[:300]}"
        except Exception as e:
            erreur = f"{modele} → {e}"
        print("⚠️", erreur)
    raise RuntimeError("IA indisponible pour l'instant (" + str(erreur) + ")")


def fusionner(ancien, ia, aujourd, debut):
    auj, deb = aujourd.isoformat(), debut.isoformat()
    jours = {}
    for j in ancien.get("jours") or []:
        ok = (isinstance(j, dict) and DATE_OK.match(str(j.get("date", "")))
              and isinstance(j.get("points"), list) and j["points"])
        if ok:
            jours[j["date"]] = {"date": j["date"],
                                "titre": str(j.get("titre") or "La quotidienne"),
                                "points": [str(p) for p in j["points"]]}
    for j in ia.get("jours") or []:
        if not isinstance(j, dict):
            continue
        d = str(j.get("date", ""))
        if not DATE_OK.match(d) or not deb <= d <= auj:
            continue
        points = [nettoyer(p, 260) for p in (j.get("points") or []) if isinstance(p, str)]
        points = [p for p in points if p][:8]
        if points:
            jours[d] = {"date": d,
                        "titre": nettoyer(j.get("titre"), 80) or "La quotidienne",
                        "points": points}
    liste = sorted(jours.values(), key=lambda x: x["date"], reverse=True)[:GARDER]
    for j in liste:
        j["articles"] = []  # vide exprès : l'ancienne version du site ne plante pas en attendant

    if isinstance(ia.get("aRetenir"), list):
        ar = []
        maxi = (aujourd + timedelta(days=10)).isoformat()
        for a in ia["aRetenir"][:6]:
            if isinstance(a, str):
                a = {"t": a}
            if not isinstance(a, dict):
                continue
            t = nettoyer(a.get("t"), 220)
            if not t:
                continue
            fin = str(a.get("jusqu", ""))
            if not DATE_OK.match(fin) or not auj <= fin <= maxi:
                fin = (aujourd + timedelta(days=2)).isoformat()
            ar.append({"t": t, "jusqu": fin})
    else:
        ar = [a for a in (ancien.get("aRetenir") or [])
              if isinstance(a, dict) and a.get("t") and str(a.get("jusqu", "")) >= auj]
    return liste, ar


def main():
    maintenant = datetime.now(PARIS)
    aujourd = maintenant.date()
    debut = aujourd - timedelta(days=FENETRE)
    prime = aujourd + timedelta(days=(5 - aujourd.weekday()) % 7)
    ancien = charger_ancien()

    titres = titres_actu(maintenant)
    print(f"📰 {len(titres)} titres lus en coulisse")
    if not titres:
        print("Rien trouvé : on garde l'ancien fichier.")
        return

    empreinte = hashlib.sha1(
        "\n".join(sorted(t for _, t in titres)).encode("utf-8")).hexdigest()[:16]
    if ancien.get("empreinte") == empreinte:
        print("Pas de nouvelle actu depuis la dernière fois : rien à faire.")
        return

    auj, deb = aujourd.isoformat(), debut.isoformat()
    anciens_jours = [j for j in (ancien.get("jours") or [])
                     if isinstance(j, dict) and isinstance(j.get("points"), list)
                     and j["points"] and deb <= str(j.get("date", "")) <= auj]
    ancien_ar = [a for a in (ancien.get("aRetenir") or [])
                 if isinstance(a, dict) and a.get("t") and str(a.get("jusqu", "")) >= auj]

    try:
        ia = demander_ia(message_ia(titres, anciens_jours, ancien_ar, aujourd, debut, prime))
    except Exception as e:
        print("❌", e, "→ on garde l'ancien fichier.")
        return

    jours, ar = fusionner(ancien, ia, aujourd, debut)
    sortie = {"maj": maintenant.isoformat(timespec="minutes"), "empreinte": empreinte,
              "jours": jours, "aRetenir": ar}
    with open(FICHIER, "w", encoding="utf-8") as f:
        json.dump(sortie, f, ensure_ascii=False, indent=1)
    print(f"✅ {len(jours)} jour(s) de résumés, {len(ar)} info(s) à retenir")


if __name__ == "__main__":
    main()
