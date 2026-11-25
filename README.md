# Station WEFAX Pro 2.11.x

Décodeur WEFAX 120 RPM piloté en CI-V (IC-705), réception RTTY/NAVTEX, archives et bulletin.
Cette version est **modulaire** : il n'y a plus de fragments à réassembler ni de script de construction.
On lance directement le programme.

**Guide illustré (français / English)** : `docs/Guide_Station_WEFAX_PRO.html`, aussi dans le menu Aide.
Il s'ouvre sans Internet.

## 1. Installation

1. Python 3.13 64 bits (version utilisée pour les essais ; Windows : cocher « Add Python to PATH »).
2. Décompresser le ZIP **dans le dossier où se trouvait l'ancien `station_wefax_pro.py`**
   (voir § 4 « Données existantes »). Faites d'abord une copie de sauvegarde de ce dossier :
   l'ancien `station_wefax_pro.py` assemblé est remplacé par le nouveau lanceur, et l'ancien
   dossier `wefax_modules/` n'est plus utilisé (vous pouvez le supprimer après essai).
3. Installer les dépendances, une seule fois :

   ```
   pip install -r requirements.txt
   ```

## 2. Lancement

Double-clic sur `lancer_station_wefax_2.11.1.bat` (il appelle Python 3.13 ; corriger le chemin dans le
fichier si Python est installé ailleurs). Autres possibilités : `py -3.13 station_wefax_pro.py`, ou
`python -m wefax_station`. Éviter le double-clic sur le .py : Windows peut l'ouvrir avec une autre
version de Python, sans les bibliothèques.

**Données (2.10.0)** : rangées dans un dossier commun à toutes les versions, à côté d'elles
(`D:\Downloads\StationWEFAXPro` si les versions sont dans `D:\Downloads`). Au premier démarrage d'une
nouvelle version, la configuration, les profils et les réceptions d'hier et d'aujourd'hui de la version
précédente y sont copiés. Supprimer un ancien dossier de version ne supprime plus les archives.

Le dossier `wefax_station/` doit rester à côté de `station_wefax_pro.py`.

### Affichage selon la taille de l'écran

* **F9** (ou le bouton « ▴ Tableau de bord ») replie le tableau de bord pour agrandir la carte.
* **F11** bascule en plein écran, **Échap** en sort. Les mêmes commandes sont dans le menu **Affichage**.
* Au démarrage, si l'IC-705 est éteint, l'application patiente et réessaie toutes les 15 s, puis lance
  le scan des fréquences dès que la radio répond.

### Plan de réception, fréquences et bulletin (2.8)

* **Plan de réception** (Réglages › 4) : choisir les bulletins texte à recevoir entre les cartes. Une
  carte en cours n'est jamais interrompue ; le bulletin est pris à son heure ou juste après la carte.
* **📋 Fréquences** : dernier résultat de chaque station ; double-clic pour accorder le poste sans
  relancer de scan, « Mesurer la sélection » pour une mesure rapide.
* **Météo & bulletin** : réceptions des dernières 24 h, bulletin rédigé automatiquement (et modifiable),
  statistiques de réception.
* **Zone d'analyse** : la case placée sur la carte. Repérer la carte une fois par type de carte
  (Réception › Repérer la carte : 3 croisements méridien / parallèle) pour que la case donne
  latitude, longitude et rayon ; ensuite tout est analysé pour cette case.
* **Lecture en clair** : fenêtre RTTY, bulletin et rapport ADRASEC commencent par « ce qu'il faut
  retenir » pour votre position (Réglages › Plan de réception) : concerné ou non, niveau 🟢🟡🟠🔴,
  heures de Paris, vent en km/h et état de la mer en mots ; le texte original est en annexe.
* **Radios** : Icom IC-705 / IC-7300 (CI-V) et Yaesu (CAT ASCII : FT-991A, FT-891, FT-710, FTDX10,
  FTDX101… ; CAT 5 octets : FT-817/818/857/897). « AUTO » essaie Icom puis Yaesu. Sur Yaesu, régler une
  fois dans le menu du poste la source audio DATA vers l'USB (FT-817/857/897 : DIG MODE = USER-U).

### Nouveautés 2.11.0
* **Bulletin synthétique** : par lieu proche, une ligne « pic » (vent, rafales, mer, heure de Paris) et une jauge
  du pire niveau jour par jour ; au plus 4 lieux détaillés ; même lieu publié sous deux noms (« GOLFE DU LION » /
  « GOLFE-LION ») fusionné ; sources, mode d'emploi et « ailleurs » en une ligne chacun ; plus d'annexe de texte
  brut (les originaux et traductions restent dans le dossier `bulletins`). Bulletin du 20/11 : 19,8 Ko → ≈ 3 Ko.
* **Traduction** : situations générales DWD (verbes de déplacement, lieux, accords « une dépression »), mistral et
  vents régionaux, avis et avertissements NAVTEX (anglais et allemand), lignes abîmées signalées « [illisible] »
  au lieu d'être mêlées au texte, heure impossible (« 56Z ») affichée « ?? h ». « NO WARNING » n'est plus présenté
  comme un avis de coup de vent.
* **Cartes plus fiables** : fin de carte reconnue quand l'image laisse place au bruit (STOP manqué : 1 000 lignes de
  bruit retirées des cartes DDK3 de 10:50 et 11:12 le 20/11) ; une carte n'est plus coupée en deux par une légende
  prise pour un phasage (40 lignes de phasage stable exigées) ; carte commencée mais perdue avant la moitié rangée
  parmi les partielles. **Règle de base** : une carte en cours n'est coupée que si elle est peu fiable (moins de
  40 % de lignes fiables sur au moins 2 min).
* **Radio moins sollicitée** : profil RF relu en contrôle léger sur une bande déjà vérifiée (30 min), une seule
  lecture CI-V par réglage déjà conforme, contrôles des autres fréquences espacés (8, 16 puis 32 min) quand ils ne
  trouvent rien, et plus de contrôle dans les 5 min qui suivent l'heure d'une carte.
* **Bouton « Stations »** sur l'écran principal : choix manuel d'une station, gardé jusqu'à la fin de la carte
  suivante ; « Rendre la main à l'automatique ».
* **Dossiers** : 5 par jour au lieu de 7 (`cartes` avec `partielles` et `details`, `bulletins`, `mes_bulletins`,
  `journaux`, `audio`) ; brouillon et logo rangés avec le profil (le logo était perdu le lendemain).
  `outils/reorganiser_archives.py` range les anciens jours (simulation par défaut).

### Nouveautés 2.10.0
* **Horloge UTC** dans l'afficheur du poste (7 segments, bleu pâle, plus discrète que la fréquence).
* **Situation actuelle et prévision à 3-6 h** du secteur, avec **indice de fiabilité** détaillé : dans le
  bulletin, le rapport en un clic et en permanence sur le bouton « Météo & bulletin » (couleur du niveau).
  Observation de l'opérateur enrichie : tendance en classes chiffrées, force du vent, état de la mer.
* **Données communes à toutes les versions** et reprise automatique de la version précédente.
* **Carte Web** affichée en consultation (bandeau, retour au direct), plus jamais à la place de la feuille
  de réception radio, et plus de carte de test fabriquée quand le serveur ne répond pas.
* **Nuit** : si aucune émission n'est reconnue, retour sur la fréquence adaptée à l'heure (et non sur la
  dernière mesurée — DDK6 13 882,5 kHz à 20 h UTC le 19/11).
* **Fiabilité Windows** : écritures retentées quand un fichier est momentanément verrouillé ; brouillon
  écrit seulement s'il change.
* **Performances** : réception et interface deux fois moins coûteuses en calcul (liste des stations,
  bargraphes, cartouche, détection START/STOP), GRIB décodé sans boucle Python.
* **Toutes les commandes des menus** vérifiées par l'autotest ; bandeau « Consultation » lisible ; guide
  illustré bilingue.

### Nouveautés 2.9.8
* Carte prise sans START ni phasage (haut manquant) : rangée dans `cartes_partielles` dès qu'il lui manque plus
  de 8 % de sa longueur (seuil de 55 % auparavant). Champ `debut_recu` dans le JSON de chaque carte.
* Analyse de surface dont le START vient d'arriver : plus de départ vers un bulletin RTTY.
* P.AMP automatique : pas d'essai quand le signal est confortable (SNR ≥ seuil + 10 dB).

### Nouveautés 2.9.7
* Cartes Northwood : le bord droit qui apparaissait replié à gauche du trait de cadre (≈ 4,5 % de la largeur)
  est remis à sa place à la sauvegarde. Les cartes DWD (marge blanche) ne sont pas concernées.
* Bulletin RTTY déjà entamé depuis plus de 5 min et carte de la station écoutée sur le point de commencer :
  la carte d'abord, le bulletin ensuite s'il est encore émis.
* P.AMP automatique : un gain de plus de 6 dB juste après des essais inutiles est attribué à la fin du fading,
  pas au préampli (journal explicite, retour au réglage de base).

### Nouveautés 2.9.6
* Une carte d'une autre famille prise en cours de route (sans START) cède la place à une carte DWD qui va
  commencer (hors rediffusion) ; elle est archivée avant le changement de fréquence.

### Nouveautés 2.9.5
* **Cartes complètes** : une carte prise en cours de route (sans START, moins de 55 % d'une carte) est rangée
  dans `cartes_partielles` et non plus parmi les cartes ; « Dernière carte » reste la dernière carte complète.
* Changement de famille (Northwood pendant le trou du DWD) : arrivée 90 s avant l'heure de la carte suivante,
  pour la recevoir dès son START.

### Nouveautés 2.9.4
* Lecture des **documents officiels réels** (essai sur la station le 19/11) : tableaux du DWD et de Northwood lus
  ligne à ligne ; sur le document NOAA réel, programmes DWD (48 cartes) et Northwood (102 cartes) **conformes**.
* Adresse du PDF DWD corrigée (dwd.de renvoyait une page HTML) ; lien PDF suivi automatiquement.
* Northwood : heure de référence de chaque produit ; seule la première analyse 00Z/06Z/12Z/18Z est prioritaire.
* Lanceur `lancer_station_wefax_2.9.4.bat` (Python 3.13 : le double-clic sur le .py ouvre Python 3.14 sans
  les bibliothèques nécessaires).

### Nouveautés 2.9.3
* **Analyse de surface prioritaire** sur tout bulletin (prévision, avis RTTY, NAVTEX).
* **Athènes conditionnelle** : quittée si sa modulation WEFAX n'est pas reconnue (retour au DWD, nouvel essai
  30 min plus tard) ; fin du créneau : retour au DWD et non plus à Northwood.
* **Programme observé** : START reçus et créneaux muets relevés chaque jour, créneaux « à vérifier » signalés.
* Journal du P.AMP automatique réparé (muet après 20 événements) ; nom de l'émetteur NAVTEX écouté.

### Nouveautés 2.9.2
* **Programmes par les sources officielles** (DWD, NOAA) : téléchargement complet en arrière-plan, comparaison,
  Accepter / Refuser par l'opérateur ; **sans Internet, rien n'est bloqué** et les programmes intégrés ou
  acceptés restent utilisés (menu Bulletins › Programmes : sources officielles).
* Programme **Northwood** complet (NOAA, 102 cartes) ; libellé DWD 07:04 corrigé.
* **Stations NAVTEX / RTTY optionnelles**, mises en sommeil après plusieurs créneaux sans texte ; La Garde
  désactivée par défaut.
* **Consultation** d'une carte pendant une réception : bandeau, bouton « Revenir au direct », retour
  automatique après 90 s ; **P.AMP auto** calme pendant les cartes ; retour du RTTY sur la station vue forte.
* Aides mises à jour (sources, hors ligne, stations texte, priorités, consultation, Winlink / VARA).

### Nouveautés 2.9.1

* **Retour au DWD selon son programme** : 2 min avant chaque carte DWD, le poste revient sur le DWD s'il
  écoute une autre station ; une simple porteuse sans modulation ne fait plus quitter le DWD ; la nuit (trou
  du programme DWD), les contrôles se font sur Northwood.
* Les changements de fréquence pendant un enregistrement sont notés dans son fichier `.json`.

### Nouveautés 2.9.0 (détail dans `CHANGEMENTS.md`)

* **Programme des cartes DWD** refait d'après le programme publié (NOAA, information du 24/07/2024) ;
  l'ancienne table enregistrée dans vos fichiers locaux est remplacée automatiquement au démarrage.
* **Carte prioritaire contre bulletin RTTY** : une analyse de surface (situation présente, isobares)
  interrompt une prévision RTTY ; une prévision de surface à 48 h au plus ne l'interrompt que si cette
  prévision a déjà été reçue dans les 12 h ; un avis de vent fort n'est jamais interrompu.
* **Scans** : P.AMP 1 pour toutes les mesures (comparaison équitable des fréquences).
* **Veille spectrale** : trames de l'IC-705 recollées d'une lecture à l'autre ; message d'arrêt juste.
* **Affichage** : « À propos » et bulles d'aide sur l'écran de l'application (multi-écran) ; ligne
  « Ensuite » avec les cartes et les bulletins, sans élément coupé ; plus de chevauchement en NAVTEX.

## 3. Arborescence

```
station_wefax_pro.py        lanceur (ne contient aucune logique)
requirements.txt            dépendances pip
README.md                   ce fichier
MODULES.md                  rôle de chaque module + correspondance avec les anciens fragments
CHANGEMENTS.md              ce qui a été modifié, supprimé, corrigé ; points à décider
validation/module_status.json   modules validés terrain (empreintes SHA-256)
outils/module_guard.py      marquer / vérifier les modules validés
outils/autotest.py          autotest de bout en bout (enregistrements simulés rejoués dans l'application)
outils/banc_hf.py           banc d'essai : chaîne de décodage face à des canaux HF simulés
outils/analyse_wav.py       analyse hors ligne d'un enregistrement WAV de terrain
wefax_station/              le programme
  version.py                numéro de version unique (SOFTWARE_VERSION)
  deps.py                   dépendances optionnelles (pyserial, sounddevice)
  core/                     données de référence : fréquences, horaires, cartes Web, bulletin
  radio/                    contrôleur CAT/CI-V, préparation RF vérifiée IC-705
  dsp/                      démodulation WEFAX continue, signature WEFAX, bande passante, restauration
  weather/                  géométrie de carte, géostrophique, indices de fiabilité
  rtty/                     démodulateur FSK, RTTY ITA2, NAVTEX SITOR-B, tables CCIR 476 / ITA2
  hybrid/                   planificateur horaires, arbitre WEFAX/RTTY, fenêtre téléscripteur
  storage/                  écritures atomiques, espace portable, enregistreur WAV
  sim/                      simulateur : signaux conformes aux normes + canal HF (essais uniquement)
  ui/                       thème, widgets, bandeau de réception, aide
  app/                      fenêtre principale, découpée par domaine (voir MODULES.md)
```

## 4. Données existantes

Rien ne change pour vos données : les dossiers sont calculés exactement comme avant.

* L'espace portable `StationWEFAXPro/` (cartes, index, journaux, préférences opérateur) est créé
  **à côté de `station_wefax_pro.py`** (ou à l'endroit indiqué par `portable_root_path.txt`
  placé à côté du lanceur). Si vous décompressez au même endroit que l'ancienne version,
  vous retrouvez tout.
* Depuis la 2.8.4, l'application est entièrement portable : plus rien n'est lu ni écrit dans
  `%LOCALAPPDATA%\StationWEFAXPro`. Ce dossier historique peut être supprimé ; les fichiers de démarrage
  vont dans `StationWEFAXPro/configuration/demarrage/`.

## 5. Modules « validés terrain »

Chaque fichier de `wefax_station/` peut être déclaré validé après essais réels. Son empreinte est
alors figée : toute modification ultérieure est signalée au démarrage (journal Diagnostics :
« ⚠️ VALIDATION : module validé MODIFIÉ ») et par l'outil de contrôle.

```
python outils/module_guard.py status                               état de tous les modules
python outils/module_guard.py validate dsp/engine.py "DDK3 14/11 OK"   valider + figer
python outils/module_guard.py check                                contrôle (code retour 1 si écart)
python outils/module_guard.py unvalidate dsp/engine.py              rouvrir un module
```

Règle de travail proposée : **une évolution = un ou deux fichiers**. On ne modifie pas un module
validé ; s'il faut le faire, on le repasse « à valider » et on refait l'essai terrain.

## 6. Faire évoluer le programme

* Chaque méthode n'existe qu'**une seule fois** dans le paquet. Pour changer un comportement,
  on modifie la méthode à l'endroit indiqué par `MODULES.md` — plus de surcouche « V26 » ni de
  patch `install_…()`.
* Le numéro de version se change uniquement dans `wefax_station/version.py`.
* Les fréquences et horaires sont dans `wefax_station/core/`.
* Après une modification : `python outils/autotest.py` (≈ 3 à 5 min, une fenêtre s'ouvre ;
  les données de test vont dans un dossier temporaire, vos archives ne sont pas touchées).

## 7. Enregistrer et rejouer une réception

Menu **Enregistrements** (ou bouton **⏺ REC** du bandeau) :

* **Démarrer / arrêter l'enregistrement** : capture l'audio brut du poste en WAV 16 bits, avec un
  fichier `.json` (fréquence, station, mode, filtre, horloge de la carte son). Fichiers dans
  `StationWEFAXPro/enregistrements/`. Durée et taille limitées par la politique de rétention (15 min / 80 Mo).
* **Enregistrer automatiquement chaque carte WEFAX** : de la détection du START jusqu'à l'archivage.
* **Rejouer un enregistrement** : le fichier passe dans la chaîne de décodage comme une réception réelle
  (WEFAX, RTTY ou NAVTEX selon le `.json`). Le flux du poste est ignoré pendant la relecture.

Les enregistrements difficiles (fading, QRN, brouillage) sont la matière première pour régler la chaîne :
envoyez-les avec leur `.json`.

## 8. Analyse hors ligne et banc d'essai

```
python outils/analyse_wav.py enregistrements/20261115_101500Z_DDK3_WEFAX.wav
python outils/banc_hf.py                (wefax / rtty / navtex : ≈ 5 à 10 min)
```

`analyse_wav.py` restitue la carte (PNG + carte de confiance) ou le texte, avec les instants START /
phasage / STOP, l'erreur d'horloge mesurée, la correction d'accord et, en NAVTEX, les messages et leur
taux d'erreur. `banc_hf.py` mesure la chaîne sur des canaux HF simulés : à relancer après toute
modification d'un module de traitement du signal, avant de le valider.

## 9. Compilation en .exe (Windows)

Le bouton « Compiler le .exe » fonctionne comme avant. En ligne de commande :

```
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onedir --windowed --name StationWEFAXPro --paths . station_wefax_pro.py
```
