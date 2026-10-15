# -*- coding: utf-8 -*-
# Robot photos : lit photos.json et telecharge chaque image dans le dossier photos/

import json
import os
import re
import unicodedata
import urllib.request

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LISTE = os.path.join(RACINE, "photos.json")
DOSSIER = os.path.join(RACINE, "photos")
ETAT = os.path.join(DOSSIER, "etat.json")
EXTENSIONS = ["jpg", "jpeg", "png", "webp"]
TAILLE_MAX = 8 * 1024 * 1024
NAVIGATEUR = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36"


def slug(nom):
    s = unicodedata.normalize("NFD", str(nom))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")
    return s


def lire_json(chemin):
    if not os.path.exists(chemin):
        return {}
    try:
        with open(chemin, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception as e:
        print("⚠️ Impossible de lire", chemin, ":", e)
        return {}


def type_image(data):
    if data[:3] == bytes([0xFF, 0xD8, 0xFF]):
        return "jpg"
    if data[:8] == bytes([0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A]):
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def telecharger(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": NAVIGATEUR,
        "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        data = r.read(TAILLE_MAX + 1)
    if len(data) > TAILLE_MAX:
        raise ValueError("image trop lourde (plus de 8 Mo)")
    ext = type_image(data)
    if not ext:
        debut = data[:300].lower()
        if b"<html" in debut or b"<!doctype" in debut:
            raise ValueError("ce lien mène à une page web, pas à une image")
        raise ValueError("format pas reconnu (il faut JPG, PNG ou WEBP)")
    return data, ext


def supprimer_autres(s, garder):
    for e in EXTENSIONS:
        nom_fichier = s + "." + e
        if nom_fichier == garder:
            continue
        chemin = os.path.join(DOSSIER, nom_fichier)
        if os.path.exists(chemin):
            os.remove(chemin)
            print("🗑️ ancien fichier supprimé :", nom_fichier)


def fichier_existe(nom_fichier):
    return bool(nom_fichier) and os.path.isfile(os.path.join(DOSSIER, nom_fichier))


def main():
    os.makedirs(DOSSIER, exist_ok=True)
    liste = lire_json(LISTE)
    etat = lire_json(ETAT)
    nouvel_etat = {}

    for nom, url in liste.items():
        url = str(url or "").strip()
        s = slug(nom)
        if not url or not s:
            continue
        ancien = etat.get(nom, {})

        if ancien.get("url") == url and ancien.get("ok") and fichier_existe(ancien.get("fichier")):
            nouvel_etat[nom] = ancien
            print("✅ déjà à jour :", nom)
            continue

        try:
            data, ext = telecharger(url)
            fichier = s + "." + ext
            supprimer_autres(s, fichier)
            with open(os.path.join(DOSSIER, fichier), "wb") as f:
                f.write(data)
            nouvel_etat[nom] = {"url": url, "fichier": fichier, "ok": True}
            print("📸", nom, "→", fichier)
        except Exception as e:
            info = {"url": url, "ok": False, "erreur": str(e)[:200]}
            if fichier_existe(ancien.get("fichier")):
                info["fichier"] = ancien.get("fichier")
            nouvel_etat[nom] = info
            print("❌", nom, ":", e)

    for nom, info in etat.items():
        if nom in nouvel_etat:
            continue
        f = info.get("fichier")
        if fichier_existe(f):
            os.remove(os.path.join(DOSSIER, f))
            print("🗑️ photo retirée :", nom)

    with open(ETAT, "w", encoding="utf-8") as f:
        json.dump(nouvel_etat, f, ensure_ascii=False, indent=2, sort_keys=True)

    print("🏁 Terminé :", len(nouvel_etat), "photo(s) suivie(s)")


if __name__ == "__main__":
    main()
