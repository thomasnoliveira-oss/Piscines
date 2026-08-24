"""Test unitaire (hors-ligne) de la logique de découpage par titres et
d'extraction du planning jour-par-jour, avec du markdown synthétique qui
imite la structure probable des pages réelles."""
from scraper import find_section, split_combined, extract_schedule, expand_day_spec

AQUAVAL_HORAIRES_SAMPLE = """# Les horaires d'ouverture

Texte d'intro général sur les deux sites.

## Aqua'val Sèvre à Clisson

### Période scolaire
- Lundi : Fermé
- Mardi-Vendredi : 11h-13h45 et 15h-20h
- Samedi : 14h30-18h
- Dimanche : 9h-13h

### Vacances d'été
- Lundi : Fermé
- Mardi : 12h-13h45
- Mercredi : 12h-13h45 et 14h30-18h
- Jeudi-Vendredi : 12h-13h45 et 18h-21h
- Samedi : 14h30-18h
- Dimanche : 9h-13h

## Aqua'val Maine à Aigrefeuille-sur-Maine

### Période scolaire et petites vacances
- Lundi-Jeudi : 11h-13h45 et 15h-20h
- Vendredi : Fermé
- Samedi : 14h30-18h
- Dimanche : 9h-13h et 14h30-18h

## Contact
02 40 54 24 56
"""

VERTOU_SAMPLE = """# Piscine municipale de Vertou

Bienvenue sur le site de la piscine.

## Horaires d'ouverture

### Période scolaire
- Lundi, mardi, jeudi, vendredi : 12h30-13h30 et 19h15-20h30
- Mercredi : 12h30-16h et 19h15-20h30
- Samedi : 11h-12h30 et 15h15-18h30
- Dimanche : 10h15-12h30

## Tarifs d'entrée

Plein tarif : 4,10€
Tarif réduit : 2,40€

## Cartes annuelles
Plein tarif : 100€
"""

GOULAINE_TABLE_SAMPLE = """## PÉRIODE SCOLAIRE

| Jour | Horaires |
|------|----------|
| Lundi | 07:15-13:45 / 16:15-18:30 |
| Mardi | 07:15-08:30 / 11:45-13:45 / 16:15-22:00 |
| Mercredi | 07:15-13:45 |
| Jeudi | 07:15-08:15 / 11:45-13:45 / 16:15-22:00 |
| Vendredi | 07:15-08:30 / 11:45-13:45 / 16:15-18:30 |
| Samedi | 14:00-18:30 |
| Dimanche | 09:00-13:00 / 14:00-18:30 |
"""


def check(label, cond):
    status = "OK " if cond else "FAIL"
    print(f"[{status}] {label}")
    return cond


all_ok = True

sevre = find_section(AQUAVAL_HORAIRES_SAMPLE, ["Sèvre", "Clisson"])
all_ok &= check("Clisson: section trouvée", sevre is not None)
all_ok &= check("Clisson: NE contient PAS Aigrefeuille", "Aigrefeuille" not in (sevre or ""))

sched = extract_schedule(sevre)["periods"]
all_ok &= check("Clisson: période 'scolaire' détectée", "scolaire" in sched)
all_ok &= check("Clisson: période 'ete' détectée", "ete" in sched)
all_ok &= check("Clisson scolaire lundi = Fermé", sched.get("scolaire", {}).get("lundi") == "Fermé")
all_ok &= check("Clisson scolaire mardi (plage étendue) = mêmes horaires que vendredi",
                 sched.get("scolaire", {}).get("mardi") == sched.get("scolaire", {}).get("vendredi") == "11h-13h45 et 15h-20h")
all_ok &= check("Clisson été mercredi = 12h-13h45 et 14h30-18h",
                 sched.get("ete", {}).get("mercredi") == "12h-13h45 et 14h30-18h")

maine = find_section(AQUAVAL_HORAIRES_SAMPLE, ["Maine", "Aigrefeuille"])
sched_maine = extract_schedule(maine)["periods"]
all_ok &= check("Aigrefeuille: titre combiné -> présent dans 'scolaire' ET 'petites_vacances'",
                 "scolaire" in sched_maine and "petites_vacances" in sched_maine)
all_ok &= check("Aigrefeuille vendredi = Fermé (les deux périodes)",
                 sched_maine["scolaire"]["vendredi"] == "Fermé" and sched_maine["petites_vacances"]["vendredi"] == "Fermé")

h, t = split_combined(VERTOU_SAMPLE)
sched_vertou = extract_schedule(h)["periods"]
all_ok &= check("Vertou: période scolaire détectée", "scolaire" in sched_vertou)
all_ok &= check("Vertou lundi = mercredi seulement pour l'horaire du soir commun",
                 sched_vertou["scolaire"]["lundi"] == "12h30-13h30 et 19h15-20h30")
all_ok &= check("Vertou jeudi = même valeur que lundi (liste énumérée)",
                 sched_vertou["scolaire"]["jeudi"] == sched_vertou["scolaire"]["lundi"])
all_ok &= check("Vertou tarifs: contient 'Plein tarif'", "Plein tarif" in t)

sched_goulaine = extract_schedule(GOULAINE_TABLE_SAMPLE)["periods"]
all_ok &= check("Goulaine (tableau markdown): période détectée", "scolaire" in sched_goulaine)
all_ok &= check("Goulaine mardi = 07:15-08:30 / 11:45-13:45 / 16:15-22:00",
                 sched_goulaine.get("scolaire", {}).get("mardi") == "07:15-08:30 / 11:45-13:45 / 16:15-22:00")
all_ok &= check("Goulaine dimanche = 09:00-13:00 / 14:00-18:30",
                 sched_goulaine.get("scolaire", {}).get("dimanche") == "09:00-13:00 / 14:00-18:30")

all_ok &= check("expand_day_spec('Mardi-Vendredi')", expand_day_spec("Mardi-Vendredi") == ["mardi", "mercredi", "jeudi", "vendredi"])
all_ok &= check("expand_day_spec('Lundi, mardi, jeudi')", expand_day_spec("Lundi, mardi, jeudi") == ["lundi", "mardi", "jeudi"])

print("\n=== TOUT OK ===" if all_ok else "\n=== DES TESTS ONT ÉCHOUÉ ===")
raise SystemExit(0 if all_ok else 1)
