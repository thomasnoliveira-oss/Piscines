#!/usr/bin/env python3
"""
Scraper des horaires/tarifs de piscines pour piscines-clisson.
Lit pools_config.json, va chercher chaque page officielle, en extrait le
contenu principal (via trafilatura, qui élimine menus/footers/cookies tout
seul) et écrit le résultat dans data/pools.json.

En plus du texte brut horaires/tarifs, on essaie d'extraire un planning
structuré jour par jour (schedule) pour chaque période (scolaire / petites
vacances / été), utilisé par la page pour afficher le tableau de synthèse
en haut de page.

Conçu pour être tolérant aux pannes : si un site est injoignable, change
de structure, ou si le planning jour-par-jour ne peut pas être extrait
avec confiance, on GARDE les dernières infos connues (issues du précédent
data/pools.json) plutôt que d'écraser avec du vide/incomplet, et on marque
le statut correspondant pour que la page web affiche un avertissement.
"""
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import requests
import trafilatura

ROOT = Path(__file__).parent
CONFIG_PATH = ROOT / "pools_config.json"
OUTPUT_PATH = ROOT / "data" / "pools.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.5",
}
TIMEOUT = 25
MAX_CHARS = 6000

DAY_KEYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]
DAY_ALIASES = {
    "lundi": "lundi", "lun": "lundi",
    "mardi": "mardi", "mar": "mardi",
    "mercredi": "mercredi", "mer": "mercredi",
    "jeudi": "jeudi", "jeu": "jeudi",
    "vendredi": "vendredi", "ven": "vendredi",
    "samedi": "samedi", "sam": "samedi",
    "dimanche": "dimanche", "dim": "dimanche",
}
DAY_TOKEN_RE = re.compile(
    r"\b(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche|lun|mar|mer|jeu|ven|sam|dim)\b\.?",
    re.IGNORECASE,
)

_html_cache: dict[str, str | None] = {}
_extract_cache: dict[str, str | None] = {}


def fetch_html(url: str) -> str | None:
    if url in _html_cache:
        return _html_cache[url]
    html = None
    for attempt in range(2):
        try:
            resp = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
            resp.raise_for_status()
            html = resp.text
            break
        except Exception as exc:  # noqa: BLE001
            print(f"  [!] tentative {attempt + 1} échouée pour {url}: {exc}", file=sys.stderr)
    _html_cache[url] = html
    return html


def extract_markdown(url: str) -> str | None:
    if url in _extract_cache:
        return _extract_cache[url]
    html = fetch_html(url)
    if not html:
        _extract_cache[url] = None
        return None
    text = trafilatura.extract(
        html,
        output_format="markdown",
        include_tables=True,
        include_links=False,
        include_images=False,
        favor_recall=True,
        url=url,
    )
    _extract_cache[url] = text
    return text


def heading_level(line: str) -> int:
    m = re.match(r"^(#{1,6})\s", line.strip())
    return len(m.group(1)) if m else 0


def find_section(text: str, keywords: list[str]) -> str | None:
    """Retourne le bloc de texte markdown démarrant à la première ligne de
    titre contenant l'un des mots-clés, jusqu'au prochain titre de niveau
    égal ou supérieur (ou la fin du texte)."""
    if not text or not keywords:
        return None
    lines = text.splitlines()
    start = None
    start_level = None
    for i, line in enumerate(lines):
        lvl = heading_level(line)
        if lvl and any(kw.lower() in line.lower() for kw in keywords):
            start, start_level = i, lvl
            break
    if start is None:
        return None
    end = len(lines)
    for j in range(start + 1, len(lines)):
        lvl = heading_level(lines[j])
        if lvl and lvl <= start_level:
            end = j
            break
    return "\n".join(lines[start:end]).strip()


def split_combined(text: str) -> tuple[str, str]:
    """Pour une page qui mélange horaires + tarifs (ex: Vertou), coupe au
    premier titre contenant 'tarif'."""
    if not text:
        return "", ""
    lines = text.splitlines()
    cut = None
    for i, line in enumerate(lines):
        if heading_level(line) and "tarif" in line.lower():
            cut = i
            break
    if cut is None:
        return text.strip(), ""
    return "\n".join(lines[:cut]).strip(), "\n".join(lines[cut:]).strip()


def truncate(text: str) -> str:
    if not text:
        return text
    if len(text) <= MAX_CHARS:
        return text
    return text[:MAX_CHARS].rstrip() + "\n\n… *(texte tronqué, voir le site officiel pour le détail complet)*"


# ---------------------------------------------------------------------------
# Extraction du planning structuré (tableau jour par jour)
# ---------------------------------------------------------------------------

def classify_period(heading_text: str) -> list[str]:
    """Devine à quelle(s) période(s) normalisée(s) correspond un titre de
    section : 'scolaire', 'petites_vacances', 'ete'. Peut renvoyer plusieurs
    clés (ex: 'Période scolaire et petites vacances')."""
    h = heading_text.lower()
    keys = []
    is_ete = "été" in h or "ete" in h or "grandes vacances" in h
    is_scolaire = "scolaire" in h
    is_petites = ("vacances" in h and not is_ete) or "petites vacances" in h
    if is_ete:
        keys.append("ete")
    if is_scolaire:
        keys.append("scolaire")
    if is_petites and not is_ete:
        keys.append("petites_vacances")
    return keys


def split_into_subsections(text: str) -> list[tuple[str, str]]:
    """Découpe un bloc markdown en (titre, contenu) pour chaque ligne de
    titre trouvée (tous niveaux confondus)."""
    if not text:
        return []
    lines = text.splitlines()
    idx = [i for i, line in enumerate(lines) if heading_level(line)]
    subs = []
    for k, i in enumerate(idx):
        end = idx[k + 1] if k + 1 < len(idx) else len(lines)
        heading = re.sub(r"^#+\s*", "", lines[i]).strip()
        content = "\n".join(lines[i + 1:end]).strip()
        subs.append((heading, content))
    return subs


def parse_day_token(token: str) -> str | None:
    t = token.strip().lower().rstrip(".")
    return DAY_ALIASES.get(t)


def expand_day_spec(spec: str) -> list[str]:
    """'Mardi-Vendredi' -> [mardi, mercredi, jeudi, vendredi]
    'Lundi, mardi, jeudi' -> [lundi, mardi, jeudi]
    'Lundi' -> [lundi]"""
    spec = spec.strip()
    days: list[str] = []
    # plage avec tiret
    range_match = re.match(
        r"^\s*(lun\w*|mar\w*|mer\w*|jeu\w*|ven\w*|sam\w*|dim\w*)\s*-\s*"
        r"(lun\w*|mar\w*|mer\w*|jeu\w*|ven\w*|sam\w*|dim\w*)\s*$",
        spec, re.IGNORECASE,
    )
    if range_match:
        d1 = parse_day_token(range_match.group(1)[:3])
        d2 = parse_day_token(range_match.group(2)[:3])
        if d1 and d2:
            i1, i2 = DAY_KEYS.index(d1), DAY_KEYS.index(d2)
            if i1 <= i2:
                return DAY_KEYS[i1:i2 + 1]
    # liste séparée par virgules / "et" / "&"
    parts = re.split(r",|\bet\b|&", spec, flags=re.IGNORECASE)
    for p in parts:
        m = DAY_TOKEN_RE.search(p)
        if m:
            d = parse_day_token(m.group(1))
            if d and d not in days:
                days.append(d)
    return days


DAY_LINE_RE = re.compile(
    r"^[\s\-\*\|]*\**([A-Za-zÀ-ÿ,&\s\-]{3,40}?)\**\s*[:\|]\s*\**(.+?)\**\s*\|?\s*$"
)


def parse_schedule_days(block_text: str) -> tuple[dict[str, str], int]:
    """Essaie d'extraire {jour: horaires} à partir d'un bloc de texte
    markdown (listes à puces, lignes 'Jour : horaires', ou tableau
    markdown '| Jour | horaires |'). Renvoie (dict, nb_jours_trouvés)."""
    result: dict[str, str] = {}
    if not block_text:
        return result, 0
    for raw_line in block_text.splitlines():
        line = raw_line.strip()
        if not line or heading_level(line):
            continue
        # ligne de séparation de tableau markdown "|---|---|"
        if re.match(r"^\|?\s*:?-{2,}:?\s*\|", line):
            continue
        m = DAY_LINE_RE.match(line)
        if not m:
            continue
        day_spec, value = m.group(1), m.group(2)
        # évite de capturer des lignes non liées aux jours (ex: "Contact : 02...")
        if not DAY_TOKEN_RE.search(day_spec):
            continue
        value = value.strip().strip("|").strip()
        if not value:
            continue
        for d in expand_day_spec(day_spec):
            result[d] = value
    return result, len(result)


def extract_schedule(section_text: str) -> dict:
    """À partir du texte isolé d'une piscine (toutes périodes confondues),
    construit {periode_key: {day: horaires}} avec un niveau de confiance."""
    schedule: dict[str, dict[str, str]] = {}
    confidence: dict[str, int] = {}
    if not section_text:
        return {"periods": schedule, "confidence": confidence}

    subs = split_into_subsections(section_text)
    # certains sites n'ont pas de sous-titres par période (tout sur une
    # seule section) : on tente quand même d'extraire un planning "unique"
    candidates = subs if subs else [("scolaire", section_text)]

    for heading, content in candidates:
        keys = classify_period(heading) if subs else ["scolaire"]
        if not keys:
            continue
        days, n = parse_schedule_days(content)
        if n < 4:  # pas assez de jours détectés : on ne fait pas confiance
            continue
        for key in keys:
            # si la période existe déjà avec autant/plus de jours, on garde
            if key not in schedule or n >= confidence.get(key, 0):
                schedule[key] = days
                confidence[key] = n

    return {"periods": schedule, "confidence": confidence}


# ---------------------------------------------------------------------------


def get_section_for(pool: dict, field: str) -> tuple[str | None, bool]:
    """Retourne (texte_isolé_pour_cette_piscine, ok) pour 'horaires' ou
    'tarifs' — utilisé à la fois pour le texte affiché et pour en dériver
    le planning structuré."""
    url = pool[f"{field}_url"]
    other_url = pool["tarifs_url"] if field == "horaires" else pool["horaires_url"]

    if url == other_url:
        full = extract_markdown(url)
        if full is None:
            return None, False
        horaires_txt, tarifs_txt = split_combined(full)
        return (horaires_txt if field == "horaires" else tarifs_txt), True

    full = extract_markdown(url)
    if full is None:
        return None, False

    split_kw = pool.get("split_keywords") or []
    if split_kw:
        section = find_section(full, split_kw)
        if section:
            return section, True
        note = (
            "\n\n*(Cette page officielle regroupe plusieurs piscines ; "
            "je n'ai pas réussi à isoler automatiquement la section de "
            "celle-ci — voici la page complète, vérifie le bon paragraphe.)*"
        )
        return full.strip() + note, True

    return full.strip(), True


def main() -> None:
    pools_config = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

    previous = {}
    if OUTPUT_PATH.exists():
        try:
            prev_data = json.loads(OUTPUT_PATH.read_text(encoding="utf-8"))
            previous = {p["id"]: p for p in prev_data.get("pools", [])}
        except Exception as exc:  # noqa: BLE001
            print(f"[!] impossible de lire l'ancien data/pools.json: {exc}", file=sys.stderr)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    any_error = False

    for pool in sorted(pools_config, key=lambda p: p["priority"]):
        print(f"-> {pool['name']} ({pool['ville']})")
        horaires_section, ok_h = get_section_for(pool, "horaires")
        tarifs_section, ok_t = get_section_for(pool, "tarifs")

        prev = previous.get(pool["id"], {})
        status = "ok" if (ok_h and ok_t) else ("partiel" if (ok_h or ok_t) else "erreur")
        if status != "ok":
            any_error = True
            print(f"   [!] statut={status} — on garde les anciennes infos si besoin", file=sys.stderr)

        schedule_result = extract_schedule(horaires_section) if ok_h else {"periods": {}, "confidence": {}}
        new_periods = schedule_result["periods"]
        prev_schedule = prev.get("schedule", {})
        schedule_status = "ok"
        if len(new_periods) >= 2:
            schedule = new_periods
        elif prev_schedule:
            schedule = prev_schedule
            schedule_status = "stale"
        else:
            schedule = new_periods
            schedule_status = "incomplet"

        entry = {
            "id": pool["id"],
            "name": pool["name"],
            "ville": pool["ville"],
            "priority": pool["priority"],
            "phone": pool.get("phone", ""),
            "adresse": pool.get("adresse", ""),
            "official_url": pool["official_url"],
            "horaires_url": pool["horaires_url"],
            "tarifs_url": pool["tarifs_url"],
            "status": status,
            "schedule_status": schedule_status,
            "last_checked": now,
            "last_success": now if status == "ok" else prev.get("last_success"),
            "horaires_text": truncate(horaires_section) if ok_h else prev.get("horaires_text", ""),
            "tarifs_text": truncate(tarifs_section) if ok_t else prev.get("tarifs_text", ""),
            "schedule": schedule,
        }
        results.append(entry)

    output = {
        "generated_at": now,
        "any_error": any_error,
        "pools": results,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nOK — écrit dans {OUTPUT_PATH} (any_error={any_error})")


if __name__ == "__main__":
    main()
