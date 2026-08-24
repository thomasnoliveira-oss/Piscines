# Piscines Clisson & alentours

Petite "app" web (gratuite) qui affiche les horaires et tarifs de 6 piscines
autour de Clisson (44), avec mise à jour automatique 2x/jour depuis les
sites officiels :

1. Aqua'val Sèvre — Clisson
2. Aqua'val Maine — Aigrefeuille-sur-Maine
3. Piscine municipale — Vertou
4. Naïadolis — Vallet
5. Divaquatic — Le Loroux-Bottereau
6. SO.POOL — Basse-Goulaine

## Mise en ligne (une seule fois, ~5 minutes)

1. Va sur https://github.com/new et crée un nouveau dépôt (repository).
   - Nom au choix, ex. `piscines-clisson`
   - Public ou privé : **Public** est nécessaire pour utiliser GitHub Pages
     gratuitement sans compte payant (Pages gratuit fonctionne aussi en privé
     si ton compte a GitHub Pro/Team, mais Public suffit et reste gratuit).
   - Ne coche PAS "Add a README" (on a déjà tous les fichiers).

2. Sur la page du nouveau dépôt vide, clique sur **"uploading an existing
   file"** et glisse-dépose TOUT le contenu de ce dossier (y compris le
   dossier `.github` et le dossier `data` — vérifie que ton navigateur
   permet bien de glisser des dossiers, sinon utilise `git` en ligne de
   commande, voir plus bas). Commit direct sur `main`.

3. Va dans **Settings → Pages** du dépôt :
   - Source : **GitHub Actions** (pas "Deploy from a branch").

4. Va dans l'onglet **Actions** du dépôt, ouvre le workflow
   "Mise à jour des horaires de piscines", et clique sur **"Run workflow"**
   pour déclencher un premier passage manuel (ne pas attendre le cron).

5. Après 1-2 minutes, ton site est en ligne à une adresse du type :
   `https://TON-PSEUDO.github.io/piscines-clisson/`
   (visible aussi dans Settings → Pages, et dans l'onglet Actions une fois
   le déploiement terminé).

6. Sur ton téléphone, ouvre cette adresse dans Safari/Chrome, puis
   "Partager" → **"Sur l'écran d'accueil"** (iPhone) ou "Ajouter à l'écran
   d'accueil" (Android). Tu as maintenant une icône comme une vraie app.

### Alternative en ligne de commande (si tu préfères `git`)

```bash
cd piscines-clisson
git init
git add .
git commit -m "Première version"
git branch -M main
git remote add origin https://github.com/TON-PSEUDO/piscines-clisson.git
git push -u origin main
```

Puis fais les étapes 3 à 6 ci-dessus.

## Comment ça marche

- `scraper.py` va lire les pages officielles de chaque piscine, en extrait
  le texte utile (horaires / tarifs) ET un planning structuré jour par jour
  pour 3 périodes (période scolaire / petites vacances / vacances d'été),
  puis écrit tout ça dans `data/pools.json`.
- `.github/workflows/update.yml` exécute ce script automatiquement 2x/jour
  (6h et 18h UTC) via GitHub Actions (gratuit), commit le résultat s'il a
  changé, puis republie le site sur GitHub Pages (gratuit aussi).
- `index.html` est la page que tu consultes : elle lit simplement
  `data/pools.json` et l'affiche, avec en haut un **tableau de synthèse**
  (jours en lignes, piscines en colonnes) — un onglet par période, avec la
  période du jour sélectionnée automatiquement (calendrier zone B
  2026-2027 codé en dur dans `index.html`, à mettre à jour l'été 2027) et
  la ligne d'aujourd'hui surlignée. En dessous, une fiche détaillée par
  piscine avec le texte complet (nuances, fermetures exceptionnelles) et
  les tarifs.
- Tu peux forcer une mise à jour à tout moment depuis l'onglet **Actions**
  du dépôt → "Run workflow", sans attendre le prochain passage automatique.

### Fiabilité du tableau de synthèse

Extraire un planning jour-par-jour automatiquement depuis 5 sites différents
est plus délicat que d'extraire un simple texte : le robot essaie de
repérer les lignes "Lundi : ..." (ou les tableaux) dans chaque section, et
n'accepte le résultat que s'il a trouvé au moins 4 jours sur 7 — sinon il
garde le planning précédent plutôt que d'afficher un tableau à moitié vide.
La toute première version (déjà dans le zip) a été vérifiée et saisie à la
main à partir des vraies pages, donc fiable dès le déploiement ; les mises
à jour automatiques suivantes prendront le relais progressivement.

## Si un site source change de structure

Le scraper est conçu pour ne jamais effacer une info existante : si un site
est injoignable ou si le texte ne peut pas être extrait proprement, l'ancien
texte est conservé et un badge "Erreur de vérification" apparaît sur la
carte concernée. Dans ce cas, dis-moi quelle piscine pose problème (avec le
message d'erreur visible dans l'onglet Actions du dépôt si possible) et
j'ajusterai le script.

## Ajouter / retirer une piscine

Modifie `pools_config.json` (ajoute ou enlève une entrée), commit, et le
prochain passage du robot (ou un "Run workflow" manuel) mettra à jour la
page automatiquement — aucune autre modification nécessaire.
