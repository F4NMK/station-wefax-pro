# Version 2.14.2 (28/11/2026) — cartes WEFAX prioritaires, fichiers réduits

## Cartes WEFAX prioritaires (décision F4NMK du 28/11 : « c'est l'objectif premier de cette application »)
* Constaté le 28/11 : départ à 11:59 vers l'avis DWD de 12:00 ; la carte GYA de 12:00 n'a été reprise qu'à
  12:03:57, sans son haut (874 lignes sur ≈ 1250).
* Un bulletin RTTY n'est pris que s'il tient avant la carte suivante du programme suivi (≈ 5 min ; 10 min
  pour un créneau NAVTEX). Toute carte qui commence (analyse, prévision, vagues, rediffusion) interrompt le
  bulletin en cours, avis et NAVTEX compris. Une écoute choisie par l'opérateur n'est jamais interrompue.
* Remplace les règles 2.9.0, 2.9.3 et 2.9.7 (seule l'analyse de surface passait devant ; un avis n'était
  interrompu par aucune carte). Aide intégrée et plan de réception mis à jour.
* **Conséquence** (compté sur les programmes intégrés) : en suivant le DWD, ≈ 30 des 70 bulletins d'intérêt
  quotidiens tiennent encore entre deux cartes ; en suivant Northwood (une carte toutes les 12 min), 4.

## Fichiers images réduits (par défaut)
* La carte signée (`_carte.png`) était un PNG couleur alors que la carte est en gris : codée en palette,
  32 niveaux de gris (écart ≤ 4 niveaux sur 255, invisible) + 224 couleurs pour le bandeau.
* `details/_traitee.png` n'est plus écrit : même contenu que la carte, recalculable depuis la décodée.
* `details/_confiance.png` sur 4 niveaux (la limite « pixel fiable » ≥ 128 est conservée).
* `details/_decodee.png` (source de tout retraitement) reste **sans perte** : stockée sur 64 niveaux, elle
  ne gagnait que ≈ 23 % et une carte bruitée retraitée avait 2,7 % de pixels visiblement changés.
* Mesuré sur la même carte rejouée (autotest, 241 lignes) : 1 310 ko → ≈ 460 ko (carte 438 → 127 ko).
  Les exports demandés par l'opérateur (Exporter, copie corrigée) restent en PNG complet.

## Vérifié
* Autotest : 238/239 (nouveaux contrôles : priorité des cartes, écoute opérateur, NAVTEX, bulletin pris dans
  un trou du programme, fichiers réduits). Seul échec : « 2110 contrôles WEFAX », déjà présent en v2.14.
* Fidélité de la carte décodée inchangée (corrélation 0,973).

# Version 2.14.1 (28/11/2026) — suivi du VFO, gain RF automatique, filtre anti-brouilleur, copie Winlink

Base : v2.14 Tkinter (l'essai d'interface Qt/QML du 27/11 est abandonné : il avait cassé l'affichage).
Les améliorations de cette période ont été reprises une par une et **mesurées** avant intégration ;
deux d'entre elles, telles qu'écrites pour la version Qt, auraient dégradé la réception et ont été refaites.

## Radio (CI-V)
* **Le VFO tourné sur le poste est suivi** (`radio/controller.py`, `app/radio_link.py`) : lecture du VFO
  seul chaque seconde (une transaction, ≈ 30 ms, lecture seule). La porteuse affichée et la station
  reconnue suivent, avec le décalage USB du dernier QSY. Seuil 2 Hz (une retouche de 50 Hz est vue).
  Avant : la fréquence affichée ne bougeait pas quand l'opérateur changeait de fréquence sur le poste.
* QSY de l'application tenu sous verrou ; le polling saute son cycle pendant un QSY (pas de figeage, pas de
  faux « changement manuel »).
* Mode lu sur le poste : table des modes Icom corrigée et mode Data lu (0x1A 0x06) → « USB-D » exact.
* OVF, P.AMP, ATT et gain RF relus à chaque cycle du chien de garde (6 s).
* `set_rf_gain()` : encodage BCD correct (255 → 02 55 ; la version Qt envoyait 02 37, soit 237).

## Gain RF automatique (option, désactivée par défaut — Réglages › Radio)
* Nouveau `radio/auto_rf_gain.py`, sur le modèle du P.AMP automatique : essais par paliers de 10 % hors
  tracé de carte, **gardés seulement si le SNR ne baisse pas** (tolérance 0,5 dB) ; surcharge OVF en
  P.AMP 0 → paliers de 20 % avant l'ATT ; remontée sur fading ; jamais au-dessus du gain choisi par
  l'opérateur, jamais sous 50 % ; pause 15 min si l'opérateur touche au gain ; retour au gain de
  l'opérateur à la désactivation et au changement de station.
* L'« AGC-RF » de la version Qt n'est pas repris : il visait un niveau audio de −18 dBFS que l'AGC FAST
  du poste maintient quel que soit le gain RF ; il aurait descendu le gain jusqu'à son plancher.
* Testé : 9 scénarios de l'automate + IC-705 simulé (`sim/fake_rigs.FakeIcom705`). **Non testé sur l'air.**

## Filtre anti-brouilleur WEFAX (option, désactivée par défaut — Réglages › Image)
* Passe-bande 1250–2550 Hz, ordre 4, **après** le suppresseur d'impulsions (`dsp/wefax_demod.py`).
* Banc HF avec filtre FI du poste (corrélation carte décodée / émise, sans → avec) : brouilleur 2 kHz
  0,720 → 0,781 ; brouilleur 700 Hz 0,876 → 0,925 ; QRN (orages) 0,895 → 0,860 ; signal propre
  0,962 → 0,952. À activer contre une station voisine, à couper par temps orageux.
* Le filtre de la version Qt (ordre 6, 1400–2400 Hz, **avant** le suppresseur) a été mesuré et écarté :
  QRN 0,688, signal propre 0,942, détection START/STOP sous fading en baisse.

## Copie compacte Winlink / VARA HF (option, désactivée par défaut — Réglages › Image)
* `cartes/winlink/<carte>_winlink.png` : carte en 4 niveaux de gris + bandeau en couleurs (PNG 16
  couleurs). Mesuré : carte signée 1809×1200 ≈ 2,3 Mo → ≈ 175 ko en pleine largeur, ≈ 100 ko réduite à
  1200 px. La carte de référence `_carte.png` est inchangée (archives, comparaison, reprise intactes).
* Les chiffres annoncés par la version Qt étaient faux : le PNG « optimisé » ne gagne que ≈ 1 %, un
  JPEG de carte pèse 0,4 à 1 Mo (et non 40–80 ko) et crée des halos autour des isobares.

## Vérifié / non vérifié
* Autotest `outils/autotest.py` : 236/237, identique à la v2.14 d'origine (valeurs mesurées identiques).
  Le seul échec, « 2110 contrôles WEFAX : 8, 16, 32, 32 min », existait déjà : le test attend encore
  l'intervalle de 32 min que la 2.11.3 a ramené à 16 min.
* Réception WEFAX rejouée avec filtre et copie Winlink activés : 12/12, copie écrite (29,6 ko contre 445 ko).
* Garde-fou TX inchangé (0x1C et 0x17 bloquées) ; aucune trame d'émission vue par le poste simulé.
* **Rien n'a été testé avec le vrai IC-705** : suivi du VFO, mode Data et gain RF automatique sont à
  confirmer sur la station.

# Version 2.11.3 (25/11/2026) — correctif : cartes DWD non reçues malgré signal fort (régressions 2.11.x)

## Constaté sur la station (25/11/2026, signal S9+15 dB, qualité 79 %)
* Aucune carte DWD reçue entre 08:34 et 09:34 alors que le signal DDK3 était à S9+15 dB.
* Diagnostic : trois régressions introduites en 2.11.0 cumulaient leurs effets sur la fenêtre 08:42–09:06.

### Régression #1 — Backoff exponentiel trop agressif (`hybrid/scheduler.py`, 2.11.0)
* `RECHECK_MAX_STEPS = 2` → intervalle de recheck pouvait atteindre **32 min** (8×2×2) après 2 scans sans
  carte. Pendant cette fenêtre de 32 min, le scheduler retournait `STAY` sans émettre de décision WEFAX :
  les créneaux 08:42, 08:54, 09:00, 09:06 tombaient tous dans cette fenêtre silencieuse.

### Régression #2 — Veille initiale au démarrage déplaçant la radio (`hybrid/arbiter.py`, 2.11.0)
* `startup_survey_pending` déclenchait un scan RTTY (~1 min) dès que le poste était libre, sans vérifier si
  une carte DWD était imminente. Si un créneau DWD tombait pendant le scan, le START n'était pas vu.

### Régression #3 — `chart_drawing` jamais True si retour du RTTY juste après un START (`hybrid/arbiter.py`)
* La condition `rx_image_armed` dans `chart_drawing` nécessitait 8 lignes d'`image_evidence` pour se lever.
  Un retour du RTTY dans les 4 s suivant un START pouvait déclencher un nouveau WEFAX_RECHECK avant que
  `rx_image_armed` soit True, interrompant la carte naissante.

## Corrections
* **`RECHECK_MAX_STEPS = 1`** (`hybrid/scheduler.py`) : backoff max ramené à 16 min (8×2). Un seul
  palier supplémentaire est raisonnable ; 32 min causait des pertes sur les émissions cadencées à 12 min.
* **Veille initiale protégée** (`hybrid/arbiter.py`) : `startup_survey_pending` ne déclenche plus le scan
  RTTY si une carte de la famille courante est prévue dans les 10 prochaines minutes.
* **Grâce de 10 lignes** (`hybrid/arbiter.py`) : `chart_drawing` est True dès 10 lignes tracées même si
  `rx_image_armed` n'est pas encore levé, évitant qu'un recheck interrompe une carte naissante.

## Vérifié / non vérifié
* Les 3 corrections ne touchent pas au décodage DSP (`dsp/`, `radio/`), ni au CI-V ; le garde-fou
  des commandes 1C et 17 est intact.
* Autotests 237/237 ✓ (aucun test ne couvrait ces trois scénarios de timing → à ajouter).
* **Non vérifié en direct** (simulateur uniquement) — à valider par F4NMK sur la prochaine fenêtre DWD.

---

# Version 2.11.2 (25/11/2026) — corrections interface

## Corrections
* Flèche sous-menu masquée : `_remove_toolbar_dropdowns` limité au cadre `map_toolbar_frame`.
* Bouton orange sous le tableau de bord : `grid_remove()` sur les boutons hérités du cadre `band`.
* `btn_stations` rebranché sur `btn_freqs_cockpit` pour l'indicateur visuel du choix opérateur.

---

# Version 2.11.1 (25/11/2026) — correctif : automatisme figé après un choix au bouton « Stations »

## Constaté sur la station (journal de la nuit du 24 au 25/11, lecture seule)
* 22:22 : stations choisies au bouton « Stations », puis DDH3 gardé à 22:24. Ensuite, plus aucune ligne
  « AUTOMATISME » jusqu'au matin : ni contrôle des fréquences, ni changement de famille, ni libération après
  45 min. Le poste est resté toute la nuit sur DDH3 (3855 kHz) sans recevoir de START ni de phasage.
* Cause : le choix opérateur de la 2.11.0 utilisait l'attribut `manual_hold`, qui existait déjà pour la pause
  manuelle et le mode MANUEL et qui arrête TOUTE la décision automatique (`evaluate_hybrid_schedule`). La limite
  de 45 min, évaluée plus loin dans cette même fonction, n'était donc jamais atteinte. Défaut de la 2.11.0, non
  vu par l'autotest (il vérifiait le choix opérateur seul, pas l'automatisme pendant ce choix).

## Correction
* Choix opérateur rangé dans son propre attribut `operator_choice` (`hybrid/arbiter.py`,
  `app/reception_plan.py`) : l'automatisme continue de décider, sans changer de fréquence tant que le choix
  tient ; la limite de 45 min est évaluée à chaque tour.
* Autotest `test_2111` : décisions évaluées pendant le choix, libération à 45 min, bouton revenu à « Stations ».

## Vérifié / non vérifié
* Décodage (START, phasage, image) : aucune ligne modifiée entre 2.10.0 et 2.11.x dans `dsp/` hors
  `chart_end.py` ; le même enregistrement rejoué donne le même résultat en 2.10.0 et en 2.11.0.
* Pic à ≈ 2 320 Hz sur DWD : déjà présent les 20 et 23/11 avec la 2.10.0 (porteuse blanche DWD ±425 Hz,
  ≈ 2 325 Hz, rattrapée par l'AFC) : pas un nouveau décalage. Non vérifié sur l'écran de la station.
* Absence de cartes la nuit sur DWD : non expliquée par le code ; à confirmer en direct.

# Version 2.11.0 (24/11/2026) — bulletin synthétique, traduction, fiabilité des cartes, radio ménagée

## Constaté sur la station (journaux et archives des 20 et 23/11, lecture seule)
* Bulletin opérateur du 20/11 : 19,8 Ko, chaque zone détaillée échéance par échéance, « GOLFE DU LION » et
  « GOLFE-LION » (même lieu, deux bulletins) listés deux fois, « ⚠ NO WARNING. » affiché comme un avis, situation
  générale tirée d'un flux brouillé à 47 %, annexe de 3 000 caractères (un avis NAVTEX abîmé sans rapport).
* Traductions : « Un dépression 1014 UKRAINE MOVES A BIT TO THE NORTH WHILE WEAKENING », lignes de tableau abîmées
  fondues dans la prose, heure « 56Z » reprise telle quelle.
* 20/11 10:50 et 11:12 (DDK3) : STOP non entendu, bruit « au-dessus du squelch » : cartes enregistrées avec 2 400
  lignes, dont ≈ 1 000 de bruit.
* 20/11 07:17 (DDK3) : 6 lignes prises pour un phasage à L.1182 : une carte complète coupée en deux fichiers.
* 20/11 15:12 (DDK6) : START reçu, signal perdu après 327 lignes : rangée parmi les cartes complètes.
* 20/11 : 88 vérifications complètes du profil RF (≈ 40 échanges CI-V chacune) ; de 08:43 à 10:45 un contrôle des
  fréquences toutes les 8 min sans résultat.
* 23/11 16:38 : contrôle des fréquences 2 min après l'heure de l'analyse de 16:36 : analyse prise sans son haut.
* Logo personnalisé enregistré dans le dossier des cartes du jour : introuvable le lendemain.

## Corrections et nouveautés
* **Rapport en clair synthétique** (`weather/plain_language.py`, `detail=True` pour l'ancien texte complet) ;
  fusion des lieux en double (le plus sévère gardé à échéance égale) ; situation générale : premier paragraphe
  lisible, celui du secteur de l'opérateur d'abord ; sources résumées ; plus d'annexe brute
  (`hybrid/arbiter.py`, `app/bulletin_desk.py`) ; justification de l'indice de fiabilité sur une ligne.
* **Avis** (`weather/rtty_parse.gale_warnings`) : titres, mentions négatives et avertissements de navigation exclus ;
  traduits.
* **Traduction** (`weather/marine_translate.py`) : tables `PLACES` (≈ 70 pays et lieux) et `SYNOPTIC` (verbes,
  tournures, NAVTEX anglais / allemand) ; vents régionaux ; « vents de secteur X à Y de force N » ; accords
  féminins ; lignes abîmées signalées ; heure illisible.
* **Fin de carte par perte de structure** (`dsp/chart_end.py`, nouveau) : corrélation entre lignes lissées, médiane
  sur 100 lignes ; 1 min de bruit au-delà de 60 % de la durée normale ; queue de bruit retirée. Vérifié en rejouant
  les cartes réelles du 20/11 : fin trouvée à L.1440 et L.1297, cartes complètes non touchées.
* **Phasage en cours de carte** : 40 lignes (20 s) avec impulsion immobile (± 3 %) au lieu de 6.
* **Carte partielle** : START reçu mais moins de la moitié de la durée normale.
* **Règle de base** (`hybrid/scheduler.py`) : `LOW_RELIABILITY_PCT = 40` ; une carte en cours ne cède la place que
  sous ce seuil (mesuré sur au moins 2 min). Seuil proposé, à valider par F4NMK.
* **Radio** (`radio/rf_verify.py`) : une lecture si déjà conforme ; contrôle léger (mode, P.AMP de référence,
  surcharge, fréquence) sur une bande vérifiée depuis moins de 30 min. Contrôles WEFAX espacés 8 / 16 / 32 min ;
  pas de contrôle dans les 5 min qui suivent l'heure d'une carte.
* **Fréquences RTTY DWD** vérifiées : 147,3 / 4583 / 7646 / 10100,8 / 11039 / 14467,3 kHz conformes au programme DWD
  et à l'annonce « CQ DE DDH47 DDH9 DDH8 FREQUENCIES 147.3 11039 14467.3 KHZ ». Programme 1 (anglais) : DDK2, DDH7,
  DDK9 ; programme 2 (allemand) : DDH47, DDH9, DDH8.
* **Bouton « Stations »** (`app/layout.py`, `app/reception_plan.py`, `hybrid/arbiter.py`) : choix gardé jusqu'à la
  fin de la carte suivante ou 45 min ; « Rendre la main à l'automatique ».
* **Arborescence** (`storage/layout.py`, nouveau) : `cartes/` (carte + fiche), `cartes/partielles/`,
  `cartes/details/` (images techniques, registres), `bulletins/` (original + traduction), `bulletins/details/`,
  `mes_bulletins/`, `journaux/`, `audio/` ; anciens noms toujours lus ; brouillon dans `<opérateur>/brouillons`,
  logo avec le profil, plus de copie de `preferences.json` par jour ; `outils/reorganiser_archives.py`.
* **Aide** : rubriques « Bouton Stations » et arborescence 2.11.0.
* **Interface Qt / QML** : non faite dans cette version (réécriture complète de l'interface) ; la séparation
  cœur / interface, préalable, se poursuit (`storage/layout.py`, `dsp/chart_end.py` sont sans Tk).

# Version 2.10.0 (19/11/2026) — fiabilité, prévision 3-6 h, horloge UTC, guide illustré

## Constaté sur la station (2.9.8, 19:20 → 20:40 UTC)
* Aucune carte en 1 h 20 : à la tombée de la nuit, seule une raie à ≈ 1 900 Hz sur 7 880 et 8 040 kHz, sans
  modulation WEFAX (scans « 1900 à confirmer ») ; cartes DWD de 19:13 / 19:26 / 19:39 non vues.
* 20:01 UTC : retour sur DDK6 13 882,5 kHz (fréquence de jour) parce que c'était la dernière fréquence mesurée.
* 19:38 UTC : « Brouillon non sauvé : PermissionError(13, 'Accès refusé') » (fichier tenu par un autre programme).
* 19:23 → 20:40 UTC : la carte téléchargée sur le site de la DWD restait affichée à la place de la feuille de
  réception, sans bandeau ; un échec de téléchargement aurait affiché une carte de TEST fabriquée.
* Dossiers des versions précédentes supprimés sur le PC : chaque version gardait ses données dans son propre
  dossier ; les archives de la journée et la configuration ont disparu avec eux.

## Corrections et nouveautés
* **Racine de données commune** (`storage/portable.py`) : `<dossier parent>/StationWEFAXPro` quand le programme
  est dans un dossier `station_wefax_pro_X.Y.Z` ; reprise (copie) de la configuration, des profils et des
  réceptions d'hier et d'aujourd'hui de la version précédente, index des réceptions reconstruit, ligne au journal.
* **Écritures sous Windows** (`storage/atomic.py`) : remplacement retenté 6 fois (≈ 1 s) si le fichier est verrouillé ;
  brouillon du bulletin écrit seulement s'il a changé.
* **Choix de fréquence la nuit** (`hybrid/arbiter.py`) : sans émission reconnue ni station vue forte sur le spectre,
  fréquence adaptée à l'heure (période JOUR / NUIT, bonus de propagation) au lieu de la dernière mesurée.
* **Carte Web** (`app/weather_desk.py`) : affichée en consultation (bandeau, retour au direct), feuille radio intacte,
  rien n'est tenté si l'accès Internet est coupé, jamais de carte fabriquée en cas d'échec.
* **Situation actuelle et prévision 3-6 h** (`weather/nowcast.py`, nouveau) : faits datés (SYNOP / SHIP proches,
  observation de l'opérateur, prévision en vigueur, dernière analyse), prévision reçue pour la fenêtre (texte, GRIB,
  avis de coup de vent), estimation (évolution du vent, tendance barométrique en classes des bulletins marins),
  niveau d'attention et **indice de fiabilité** détaillé point par point (fraîcheur, distance, accord des sources,
  lisibilité ; plafonné avec une seule source ; 0 % sans donnée). Dans le rapport 1 clic, la fenêtre Météo & bulletin
  et sur le bouton « Météo & bulletin » (couleur du niveau, recalcul toutes les 10 min hors de l'interface).
* **Observation de l'opérateur** : tendance sur 3 h en classes chiffrées, direction (8 secteurs), force Beaufort,
  état de la mer (Douglas), listes non modifiables (plus de saisie libre ambiguë).
* **Fiches des cartes** : `utc_debut`, `programme_code`, `programme` (carte du programme reconnue à l'heure de début).
* **Horloge UTC** (`ui/vfo_display.py`) : 7 segments bleu pâle entre les puces et le S-mètre, HH:MM:SS ou HH:MM selon
  la place, seule redessinée chaque seconde.
* **Bandeau « Consultation »** : nom du fichier seulement ; bouton « ⟲ Revenir au direct » toujours entier.
* **Performances** (réception simulée de 340 lignes, temps de calcul cumulé) : 27,0 s → 12,7 s.
  Liste des stations : polices de mesure à part, rien recalculé sans changement (11,3 s → 0,2 s) ; bargraphes :
  redessinés seulement s'ils changent, polices en cache (4,1 → 1,5 s) ; cartouche : police et logo en cache ;
  détection START / STOP : 38 fréquences en un produit matriciel (2,0 → 0,2 s) ; GRIB : distances vectorisées.
* **Aide** : rubriques « Situation actuelle et prévision à 3-6 h », « Horloge UTC », « Où sont rangées les données » ;
  menu Aide › **Guide illustré (français / English)** (`docs/Guide_Station_WEFAX_PRO.html`, hors ligne).
* Outils : `outils/captures.py` (captures des fenêtres sans poste), `outils/construire_guide.py` (guide autonome).

## Vérifications
* Autotests 2.10.0 : toutes les commandes des menus (47 entrées), situation et prévision 3-6 h (6), racine commune,
  écritures verrouillées, fréquence de nuit, carte Web, horloge (7) ; batterie complète 195/195.
* Captures des fenêtres relues ; guide rendu dans un navigateur (français et anglais).
* Non vérifié en réel à ce stade : reprise des données sur le PC de F4NMK (sera vue au premier démarrage),
  IC-7300 et Yaesu (simulateur seulement, comme avant).

# Version 2.9.8 (19/11/2026) — une carte sans son haut n'est pas une carte complète

## Constaté sur la station (2.9.6)
* Carte GYA H+48 de 17:24 reprise en cours de route à 17:26:49 (retour du RTTY) : 1 016 lignes sans START,
  haut manquant, rangée parmi les cartes car au-dessus du seuil de 55 %.

## Correction (décision F4NMK du 19/11 : « les cartes doivent être complètes »)
* Sans START ni phasage, une carte n'est rangée parmi les cartes que si elle a au moins 92 % de la longueur d'une
  carte (≈ 1 150 lignes : START manqué par fading alors que le poste écoutait déjà). Sinon : `cartes_partielles`,
  journal « haut de carte manquant ».
* Nouveau champ `debut_recu` (START ou phasage reçu) dans le JSON de chaque carte.
* Analyse de surface dont le START vient d'arriver (aucune ligne encore tracée) : plus de départ vers un
  bulletin RTTY. Le 19/11 à 18:00:07, START de l'analyse DWD reçu à 18:00:02, départ vers l'avis de 18:00 puis
  retour à 18:00:22 (avis coupé à 85 caractères, deux changements de fréquence). La garde « analyse imminente »
  couvre maintenant jusqu'à 60 s après l'heure.
* P.AMP automatique : aucun essai de montée quand le SNR reste confortable (≥ seuil + 10 dB). Le 19/11 à 18:00:53,
  essai de P.AMP 2 à 31,4 dB de SNR sur DDK3 : −23,8 dB pendant l'essai, image marquée pour rien.

## Vérifications
* Autotest « 2.9.5 » adapté (1 016 lignes sans START → partielle ; 1 200 lignes sans START → carte) ; autotest
  « 2.9.8 » (2 vérifications) ; batterie complète 179/179.

# Version 2.9.7 (19/11/2026) — cadre Northwood, bulletin entamé, faux gain du P.AMP

## Constaté sur la station (2.9.6 lancée à 17:00 UTC)
* Report du changement de famille efficace : contrôle de GYA reporté de 17:08 à 17:10:30, arrivée sur GYA3 à
  17:10:53, carte de 17:12 reçue entière (START → STOP, 1 319 lignes, 99,8 % exploitables).
* Cette carte est complète mais **mal coupée** : ses 82 derniers px (bord droit) sont à gauche de son trait de
  cadre. La colonne 0 est du dessin, continu avec la dernière colonne. Les cartes DWD du matin commencent par une
  marge blanche : non concernées.
* À 17:23, départ vers l'avis aux navigateurs de 17:15 (DDK9, propagation mesurée 18 min plus tôt) : 3 min de
  texte surtout illisible, rien d'archivé, et le début de la carte GYA de 17:24 (prévision H+48) perdu.
* À 17:30, « P.AMP 2 gardé : SNR 0,0 → 9,6 dB » pendant la carte, alors que la référence était à 11,1 dB et que
  les essais de 17:12 et 17:19 donnaient +0,2 et +0,3 dB : c'était la fin d'un fading.
* Pente propre à Northwood : −0,06 px/ligne (DWD : 0). Les cartes sauvegardées sont redressées (trait de cadre
  vertical à 1 px près) ; seul le tracé en direct reste penché (non corrigé dans cette version).

## Corrections
* Sauvegarde d'une carte : si un trait de cadre net et vertical se trouve dans les 8 % de gauche (pente
  compensée) avec du dessin à sa gauche, la carte est tournée horizontalement pour que ce trait soit au bord
  gauche (ligne « 📐 Bord droit replié à gauche du cadre … » au journal).
* Bulletin RTTY (hors NAVTEX) commencé depuis plus de 5 min et carte non rediffusée de la station écoutée
  dans les 3 min : on reste pour la carte ; le bulletin est repris après le STOP s'il est encore dû.
* P.AMP automatique : un gain de plus de 6 dB après un essai inutile dans les 30 dernières minutes (même mode)
  n'est pas attribué au préampli. Pendant une carte, le cran reste jusqu'au STOP (pas de commutation de plus sur
  l'image) puis redescend normalement ; hors carte, retour immédiat au cran précédent.

## Vérifications
* Détecteur de cadre essayé sur les cartes réelles du 19/11 (lecture seule) : GYA3 17:12 → 82 px, carte GYA en
  cours → trouvé ; 8 cartes DWD du matin → aucun déclenchement.
* Autotest « 2.9.7 » (4 vérifications) ; batterie complète 177/177.

# Version 2.9.6 (19/11/2026) — une carte prise en cours de route cède la place à la carte DWD

## Constaté sur la station (2.9.5 lancée à 12:48 UTC)
* Au démarrage, le contrôle a retenu Northwood (carte en cours, modulation reconnue) et le poste y est arrivé
  au milieu d'une carte (aucun START) ; la règle « carte en cours jamais interrompue » l'y a gardé pendant la
  carte DWD de 12:56 (rediffusion, sans conséquence ce jour-là).

## Corrections
* Carte d'une autre famille prise sans START : elle cède la place à une carte de la famille de référence qui
  commence dans les 2 min (jamais pour une rediffusion, jamais une carte prise depuis son START). Elle est
  archivée avant le changement de fréquence (fragment ou carte selon sa longueur).

## Vérifications
* Autotest « 2.9.5 » complété (règle de cession) ; batterie complète 173/173.

# Version 2.9.5 (19/11/2026) — cartes complètes

## Constaté (remarque de F4NMK du 19/11 à 13:25 : « certaines cartes sont tronquées »)
* Les cartes DWD reçues depuis leur START (07:17, 07:43, 08:04, 08:17, 10:50…) sont **entières** : ≈ 1 300 lignes,
  marges blanches à gauche et à droite, cadre inférieur sur la dernière ligne (le traitement d'image l'affaiblit,
  d'où l'impression d'une coupe sous « © Deutscher Wetterdienst »).
* Les cartes réellement tronquées étaient des **cartes prises en cours de route**, rangées comme des cartes :
  07:04 (505 lignes : le poste était sur le NAVTEX jusqu'à 07:11) et Northwood vue à 11:57 (arrivée au milieu
  de la carte lors du passage DWD → Northwood à 11:56).
* Les captures d'écran prises pendant les contrôles montrent des cartes **en cours de tracé** (haut seulement).

## Corrections
* Fragment = carte sans START (ni phasage en début de feuille) et de moins de 55 % d'une carte (≈ 690 lignes) :
  rangé dans `cartes_partielles` (non indexé parmi les cartes), « Dernière carte » garde la dernière carte
  complète, ligne « 🧩 Carte prise en cours de route … » au journal. Une carte presque entière reste une carte.
* Un phasage reçu en tout début de feuille compte comme le début de la carte.
* Changement de famille lors du contrôle « 8 min sans carte » : reporté pour arriver 90 s avant l'heure de la
  carte suivante de la nouvelle famille (ligne « ⏳ Contrôle de … reporté »).

## Vérifications
* Autotest « 2.9.5 » (5 vérifications) ; batterie complète 172/172 ; tests de relecture « prise en cours de route » inchangés.

# Version 2.9.4 (19/11/2026) — documents officiels réels, installation sur la station

## Constaté sur la station (2.9.3 lancée à 10:01 UTC)
* Les deux documents ont été téléchargés au démarrage. **dwd.de** a renvoyé une page HTML (47 Ko) et non le PDF :
  l'adresse exige « ?__blob=publicationFile&v=1 » (adresse donnée par le document NOAA lui-même).
* **NOAA** (1,5 Mo, texte extrait par l'extracteur intégré) : la comparaison « heures au fil du texte » se
  trompait. DWD : heures de référence (00.00, 03.00, 06.00…) et plages de phonie comptées comme des cartes.
  Northwood : la suppression des « années » effaçait les heures 19:00-20:48, et la date « Jan 05, / 2022 »
  coupée sur deux lignes n'était pas reconnue. Rien n'avait été accepté : aucune conséquence sur la réception.
* Le double-clic sur `station_wefax_pro.py` lance Python 3.14, dépourvu de numpy / OpenCV : l'application
  s'arrête aussitôt. La station tourne avec Python 3.13.

## Corrections
* Lecture structurée des tableaux : DWD (« HH.MM », 120 / 576, IOC, heure de référence, intitulé ; phonie
  écartée) et Northwood (deux colonnes, intitulé puis heure, créneaux vides ignorés). Sur le document NOAA réel :
  DWD 48 cartes et Northwood 102 cartes, **conformes** au programme intégré, dates d'information reconnues.
  Sans tableau reconnu : aucune proposition de modification (ouvrir le document).
* Adresse du PDF DWD corrigée, y compris dans `sources_officielles.json` déjà écrit par la 2.9.3 ; page HTML
  reçue : le lien PDF du même site est suivi une fois.
* PDF du DWD lui-même (30 Ko, téléchargé par la station à 11:48 UTC) : cellules séparées par « x-none » et
  « 120 / 576 » d'un seul tenant, désormais reconnus ; ses 48 cartes sont conformes au programme intégré.
* Les heures proposées portent l'intitulé du document (« Carte au programme officiel : … »).
* Programme Northwood reconstruit depuis le document réel : heure de référence de chaque produit ; la première
  analyse 00Z (02:36), 06Z (09:00), 12Z (14:36) et 18Z (21:00) est prioritaire, les suivantes sont des
  rediffusions (elles ne coupent qu'un bulletin déjà reçu).
* `lancer_station_wefax_2.9.4.bat` : lancement avec Python 3.13.

## Vérifications
* Autotest « 2.9.4 » (8 vérifications) ; batterie complète 167/167 ; « 2.9.2 » adapté à la mise en page réelle ; analyse des documents réels
  téléchargés par la station : DWD et Northwood conformes.

# Version 2.9.3 (19/11/2026) — session réelle du 19/11 (2.9.1, 06:25-09:31 UTC) et enregistrement de 06:43

## Ce que montrent le journal et l'enregistrement
* **Cartes reçues, lisibles** (DDK3, fiabilité 99 %) : 07:04 température 850 hPa (prise en cours), 07:17 H+36,
  07:43 H+60, 08:04 H+84, 08:17 H+108. Intitulés conformes au programme intégré.
* **Créneaux sans START** alors que DDK3 était fort (veille spectrale +29 à +54) : 07:30 (H+48), 08:30 et
  08:42 (vagues). Non émis ou START manqué : impossible à trancher sur une matinée → relevé du programme
  observé (ci-dessous).
* **Athènes** : bascule à 08:43, « Qualité déjà optimale sur SVJ4 (79 %) — Scan évité » calculé sur l'ancienne
  station (DDK3) ; contrôles de 08:51, 09:03 et 09:11 : aucune structure WEFAX (rang 0), mais le poste est resté
  sur Athènes → cartes DWD de 08:54, 09:06, 09:30, 09:45… perdues. Après le bulletin de 09:00, retour sur SVJ4B.
* **P.AMP automatique** : changements sans aucune ligne au journal après 07:21 (liste d'événements plafonnée à
  20 : l'appelant ne voyait plus les nouveaux).
* **NAVTEX** (07:54-08:01 sur 518 kHz, 09:19-09:30 sur 490 kHz) : aucun caractère. L'enregistrement de 06:43
  (518 kHz de 06:49 à 07:00, 490 kHz de 07:00 à 07:01) ne contient que du bruit large bande parfaitement plat,
  sans aucune raie : pas même une FSK faible. S-mètre S9+8 à S9+10 en P.AMP OFF : bruit local probable en
  ondes moyennes ou antenne inadaptée à 518/490 kHz (à vérifier sur la station).
* **Enregistrement, partie WEFAX (06:43-06:49, DDK3)** : porteuse de repos à 1475 Hz (noir, accord −25 Hz),
  aucune carte (06:38 « tempêtes tropicales » non émise). Une raie à 1895 Hz entourée d'un peigne espacé
  d'environ 125 Hz y est présente, comme le 18/11 sur 8040 kHz (« porteuse de Northwood ») : la même raie
  audio sur deux fréquences différentes désigne plutôt une source côté réception (poste, PC, USB) qu'un
  émetteur. L'essai « antenne débranchée » reste le moyen de trancher.

## Corrections
* **Analyse de surface prioritaire sur tout bulletin** (décision F4NMK du 19/11) : elle interrompt aussi un avis
  RTTY et un créneau NAVTEX, et aucun bulletin n'est commencé à moins de 3 min de son heure. Un avis n'est
  interrompu par aucune autre carte.
* **Athènes conditionnelle** : contrôle forcé à l'arrivée (plus de « Scan évité » sur un indice périmé) ; rang < 2
  → retour à la famille de référence (DWD) et nouvel essai 30 min plus tard ; pas de départ vers Athènes à moins
  de 3 min d'une carte DWD ; fin du créneau : retour sur la meilleure fréquence DWD (et non plus Northwood).
  Contrôle forcé aussi au retour d'Athènes et avant une carte DWD (GO_FAMILY).
* **Journal du P.AMP automatique** : compteur total d'événements, chaque changement est de nouveau journalisé.
* **Programme observé** (`hybrid/observed_programme.py`, `configuration/programme_observe.json`) : START rattaché
  à l'heure du programme (±4 min) ; créneau « muet » si le poste écoutait la famille avec un bon signal, sans
  carte en cours, sans START dans les 4 min (ligne « 🗓️ [PROGRAMME OBSERVÉ] ») ; muet 3 jours et jamais reçu →
  « à vérifier » dans la fenêtre des sources officielles. Rien n'est retiré du programme automatiquement.
* Ligne d'écoute NAVTEX : nom de l'émetteur attendu (« NAVTEX La Maddalena (I) » au lieu de « NAVTEX-FR »).
* Autotest 2.9.0 : la règle « un avis n'est jamais interrompu » est remplacée par la décision du 19/11.

## Reste à confirmer sur la station
* Athènes : retour au DWD dans la minute qui suit un contrôle sans modulation (journal « 🏛️ Athènes non
  identifiée … »). Programme observé : premières lignes « muet » attendues à 07:30, 08:30, 08:42 si le constat
  se répète. Toutes les corrections 2.9.2 et 2.9.3 n'ont été testées qu'au simulateur.

## Vérifications
* Autotest « 2.9.3 » (9 vérifications) ; batterie complète 158/158.

# Version 2.9.2 (19/11/2026) — sources officielles sans dépendre d'Internet, stations texte en sommeil, consultation

## Analyse du 18/11 au soir et du 19/11 au matin (« je ne reçois plus de carte »)
* **Pas de régression de réception en 2.9.1** : le 19/11 (démarrage 06:25 UTC), les cartes DWD sont reçues et
  lisibles (07:04 température 850 hPa, STOP 07:15:25, nouvelle carte à 07:17). Le 18/11 au soir (2.9.0), le
  poste était resté sur Northwood (porteuse sans modulation) : corrigé en 2.9.1.
* **Cartes perdues le 19/11** : écoute NAVTEX de 06:49 à 07:11 (La Maddalena R, La Garde S : aucune FSK, Mark et
  Space au même niveau) pendant les cartes DWD de 06:51 et 07:04 → stations texte optionnelles et mise en
  sommeil (ci-dessous), La Garde désactivée par défaut.
* **Carte en réception masquée** vers 07:17-07:19 : l'écran montrait la carte précédente (« Dernière carte »)
  pendant que la nouvelle se traçait ; l'étiquette « Consultation » est masquée depuis la 2.8 → bandeau.
* **P.AMP auto** : oscillation 1 ↔ 2 toutes les 30 à 40 s pendant les cartes (gains de +2,2 dB, S9+9).
* **Retour du RTTY à 06:33** : QSY vers DDK6 (ancienne mesure) alors que DDK3 était fort sur le spectre.

## Programmes par les sources officielles, autonomie totale hors ligne
* Nouveau module `hybrid/official_sources.py` : registre modifiable `configuration/sources_officielles.json`
  (DWD broadcast_fax_102020.pdf, NOAA rfax.pdf ; https uniquement), téléchargement COMPLET dans un fil séparé
  (délai de connexion 10 s, délai total 90 s, 12 Mo au plus), conservation dans `configuration/sources`
  (date, taille, SHA-256, texte extrait), lecture du PDF (pypdf s'il est installé, sinon extracteur intégré),
  relevé des heures de chaque station et de la date « INFORMATION DATED », comparaison avec le programme
  utilisé : conforme / différences / texte peu exploitable.
* Rien n'est modifié sans l'opérateur : fenêtre « Programmes : sources officielles » (menu Bulletins et menu
  hybride) avec Accepter / Refuser / Ouvrir le document. Programme accepté conservé dans
  `configuration/programmes_acceptes.json` et utilisé ensuite hors ligne (prime sur les copies locales).
* **Hors ligne** : aucun blocage, aucune fenêtre ; une seule ligne « 📴 [SOURCES] Internet non joignable … la
  réception continue normalement, sans Internet ». L'ancien téléchargement partiel (256 Ko, document jamais lu)
  et le registre `registre_horaires_web.json` sont remplacés.
* **Programme Northwood** refait d'après la NOAA (information du 05/01/2022) : 102 cartes, une toutes les 12 min
  (l'ancienne table de 12 cartes n'était pas sourcée et est remplacée sur disque). Les analyses sans heure de
  référence publiée sont traitées comme des rediffusions (elles ne coupent pas un bulletin non reçu) ; la carte
  d'avis de coup de vent est prioritaire.
* Libellé DWD de 07:04 corrigé : température 850 hPa (et humidité 700 hPa selon la NOAA).

## Stations NAVTEX / RTTY optionnelles (`hybrid/text_station_health.py`)
* Activation par station dans Réglages › Plan de réception (La Maddalena R/I, Cabo la Nao X, La Garde W/S,
  programmes RTTY 1 et 2 du DWD), état affiché et bouton Réactiver.
* Créneau écouté jusqu'au bout sans 40 caractères = échec (créneau écourté non compté ; le texte d'un créneau
  précédent ne compte plus). 3 échecs (NAVTEX) ou 5 (RTTY) → sommeil, nouvel essai toutes les 24 h (NAVTEX) ou
  6 h (RTTY), réactivation à la première réception. La Garde W/S désactivée par défaut (OHI 2023-2024).

## Fiabilité
* **Consultation** (« Dernière carte » ou archive) : bandeau orange sur l'image avec « Revenir au direct » ;
  retour automatique au direct après 90 s sans action si une carte est en réception (et toujours au START
  d'une nouvelle carte). « Réception directe » efface aussi l'état de consultation.
* **P.AMP auto pendant une carte** : au plus un essai toutes les 3 min (après 3 mesures en fading), cran gardé
  seulement pour +3 dB, aucune descente avant la fin de la carte.
* **Retour aux cartes** : une station de la famille vue forte sur le spectre (≤ 5 min) l'emporte sur une mesure
  de propagation plus ancienne ou sans émission reconnue ; la raison est notée au journal.
* Aides mises à jour : sources officielles, fonctionnement sans Internet, stations texte, priorités, consultation,
  Winlink / VARA (réglages à faire soi-même : DATA MOD, carte son, Radio Setup, ALC / USB MOD Level / Drive).

## Reste à confirmer sur la station
* Téléchargement réel des deux PDF depuis le PC (non testable ici : l'accès à dwd.de et weather.gov est bloqué
  dans mon environnement) et qualité de l'extraction du texte sur les vrais documents : si le texte est peu
  exploitable, la fenêtre le dit et propose d'ouvrir le document, sans rien modifier.
* Programme Northwood : sa réception au Cannet reste à démontrer (le 18/11, porteuse sans modulation).
* Bandeau de consultation, P.AMP calme et mise en sommeil NAVTEX : testés au simulateur seulement.
* Réglages Winlink / VARA de l'aide : à vérifier sur le poste (ALC et puissance sous les yeux).

## Vérifications
* Autotest « 2.9.2 » (19 vérifications) ; batterie complète 149/149 : table Northwood, priorités, PDF officiel simulé (extraction, dates,
  différences), démarrage sans réseau non bloquant, coupe-circuit, téléchargement simulé, Accepter / Refuser,
  rechargement hors ligne, stations en sommeil puis réactivées, bandeau et retour au direct, P.AMP pendant une
  carte, choix de la fréquence au retour du RTTY, aides.

# Version 2.9.1 (18/11/2026) — retour au DWD selon le programme (aucune carte reçue le 18/11 au soir)

## Analyse de la soirée du 18/11 (2.9.0, 20:43-21:31 UTC) et de l'enregistrement GYA2 de 25 min
* **Logiciel** : au démarrage (20:44) le DWD était dans un trou de son programme (rien entre 19:51 et 21:00) ;
  le scan n'a trouvé aucune modulation WEFAX, et une **porteuse fixe à 1900 Hz sur 8040 kHz** (rang 1) a
  envoyé le poste sur Northwood. Les contrôles « 8 min sans carte » ne scannaient ensuite que Northwood :
  **le poste n'est jamais revenu au DWD**, cartes de 21:00, 21:15 et 21:36 manquées, alors que la veille
  spectrale voyait DDK3 « net » (+13 à +17) à plusieurs reprises. À 21:00:00, un contrôle des fréquences est
  même parti à la seconde où une carte était prévue.
* **Signal** : l'enregistrement (20:56-21:21) ne contient aucune modulation WEFAX. 4610 kHz (20:56-21:00) :
  bruit seul ; 8040 kHz (21:00-21:19) : porteuse fixe à 1895 Hz, 13 à 17 dB au-dessus du bruit, accompagnée d'un
  peigne de raies espacées d'environ 125 Hz, sans modulation (ni blanc 2300 Hz, ni noir 1500 Hz, ni START 300 Hz, ni STOP 450 Hz) ; analyse hors ligne :
  aucun START, phasage ou STOP, image de bruit. Northwood n'a donc pas été reçu, alors que son programme
  (NOAA, janvier 2022) prévoit une carte toutes les 12 min sur 4610 et 8040 kHz.
* La veille spectrale corrigée en 2.9.0 **fonctionne sur le poste réel** (premier balayage à 20:44:44).
* NAVTEX 490 kHz (21:19-21:29) : Mark et Space au même niveau (+9 dB) = bruit, pas de FSK.
* L'enregistrement était étiqueté « GYA2 » alors que le poste est passé sur GYA3 puis sur NAVTEX 490 kHz.

## Corrections
* **Famille de référence DWD** (`PREFERRED_WEFAX_FAMILY`, seul programme intégré vérifié) :
  * 2 min avant l'heure d'une carte DWD, si le poste est sur une autre famille (hors créneau d'Athènes),
    retour sur la meilleure fréquence DWD puis contrôle rapide du DWD (« GO_FAMILY ») ;
  * « 8 min sans carte » : contrôle du DWD quand une carte DWD est en cours ou prévue dans les 30 min, même
    depuis Northwood ; dans un trou du programme DWD (nuit 22:12-04:30), contrôle de Northwood ;
  * fin de scan sans aucune modulation WEFAX (rang < 2) : une simple porteuse sur une autre famille ne fait
    plus quitter le DWD quand une carte DWD est au programme (ligne « SCAN_PREFERENCE » au journal).
* **Pas de contrôle des fréquences** dans les 2 min qui suivent l'heure d'une carte prévue.
* **Enregistrement** : chaque changement de fréquence pendant l'enregistrement est noté dans le `.json`
  (`changements` : instant, station, fréquence, mode).

## Reste à confirmer sur la station
* Retour automatique au DWD avant 21:00 / 22:00 (journal : « 🗓️ Carte DWD prévue à … : retour de GYA vers DWD »).
* Northwood : porteuse fixe sur 8040 kHz = émetteur sans modulation ou perturbation locale ? Essai simple :
  débrancher l'antenne ; si la raie à 1895 Hz reste, elle est produite localement (PC, alimentation, USB).
* Programme de Northwood dans le logiciel (12 créneaux) non conforme au programme publié (une carte toutes
  les 12 min) : à refaire avec la mise à jour des programmes officiels (version suivante, en attente du Go).

## Vérifications
* Autotest « 2.9.1 » : retour au DWD à 20:58:30 (et pas à 20:50, ni sur Athènes, ni déjà sur DWD), contrôle
  reporté après l'heure d'une carte, famille contrôlée (DWD / Northwood selon le programme), porteuse fixe
  écartée en fin de scan, changement de fréquence noté dans l'enregistrement.

# Version 2.9.0 (18/11/2026) — programme DWD réel, carte prioritaire, veille spectrale réparée, affichage

## Audit de la soirée du 18/11 (journaux 2.8.8 de 18:03 à 19:30 et 2.8.9 de 19:29 à 19:46, poste réel)
* **Programme des cartes DWD faux** : la table intégrée ne correspondait pas aux émissions. Programme publié
  (NOAA, information du 24/07/2024, d'après le plan DWD 10/2020) : 18:00 analyse, 18:21, 18:34 H+36,
  18:47 H+48, 19:00 H+84, 19:13 / 19:26 / 19:39 vagues, phonie 19:55-20:35, 21:00, 21:15, 21:36, 22:00.
  Correction de l'audit 2.8.9 : la « FSXX48 de 18:30 perdue » était la prévision H+48 de **18:47**, perdue
  parce que le poste est parti à 18:49:13 sur le NAVTEX de 18:50 (il n'a repris que les 72 dernières lignes
  à 19:01) ; la carte « en cours à 19:01 » était la fin de cette H+48, et celle de 19:11-19:15 la H+84.
* **Cartes non reconnues après un scan de contrôle** : de 18:35 à 18:49 (2.8.8) puis de 19:29 à 19:46
  (2.8.9), DDK3 émettait (S9, modulation vue au scan) mais ni START (18:47, 19:39) ni carte en cours
  n'ont été détectés ; après un retour direct du RTTY la carte était reconnue en 4 s (19:01:18, 19:11:04).
  **Non reproduit au simulateur** (START, phasage et STOP détectés après un scan comme après un retour du
  RTTY) : cause encore inconnue, un enregistrement audio (⏺ REC) autour d'une carte est nécessaire.
* **NAVTEX** : aucun caractère et aucune ligne d'état de 18:49 à 19:01 (518 kHz) et de 19:02 à 19:11
  (490 kHz). Le 18/11 à 20:01 le poste affichait sur 518 kHz P.AMP OFF (réglage mémorisé par bande dans
  l'IC-705), S9+7 dB et 19 % de fiabilité. Cause encore inconnue (bruit local en ondes moyennes, antenne,
  émission absente ?) : pas d'enregistrement audio de ces créneaux.
* **Veille spectrale** : l'IC-705 envoyait bien son spectre, au format prévu (en-tête : centre 7 878,1 kHz,
  ±250 kHz, 11 trames ; 50 points par trame), mais les trames coupées entre deux lectures du port série
  étaient perdues : aucun balayage complet, puis arrêt avec un message accusant à tort le poste.
* **Régressions** : Aide › À propos invisible sur le poste multi-écran (position ramenée dans l'écran
  principal) ; bulle d'aide de « Démarrer en auto » affichée sur un autre écran ; méthode
  `_return_to_live_rx_view` appelée mais absente (branche inactive : le retour automatique à la vue en
  direct ne fonctionnait pas).
* **Affichage** (captures de F4NMK) : en NAVTEX, « SITOR-B 100 Bd · 170 Hz » chevauchait « NAVTEX-INT » ;
  la ligne « Ensuite : » revenait à la ligne au milieu d'un bulletin et ne citait pas les cartes.
* **Messages trompeurs** : « Fréquences à jour… Horaires vérifiés » alors que le document en ligne est
  seulement téléchargé ; « Flux Audio USB connecté » annoncé pour le micro du PC (19:32:38).
* **Scan** : le P.AMP mémorisé par bande (0 sur 2,6 / 3,8 / 4,5 / 4,6 MHz, 1 ailleurs) faussait la
  comparaison des fréquences.

## Corrections
* **Programme DWD** (`core/schedules.py`) refait (48 cartes) ; une copie locale d'une autre révision
  (`configuration/horaires_wefax_rtty_officiels.json`, `programmes_wefax.json` du profil) est remplacée au
  chargement pour la famille DWD, les autres familles enregistrées sont conservées.
* **Carte prioritaire contre bulletin RTTY** (règle validée par F4NMK) :
  * analyse de surface (situation présente, isobares) : interrompt une prévision RTTY ; dans les 3 min qui
    précèdent une analyse, un bulletin non urgent attend la fin de la carte ;
  * prévision de pression de surface ≤ 48 h, rediffusion d'analyse : n'interrompt une prévision que si
    celle-ci a été reçue en entier dans les 12 dernières heures (`configuration/bulletins_recus.json`) ;
  * avis (coup de vent, tempête) : jamais interrompu ; NAVTEX et écoute choisie par l'opérateur : jamais ;
  * on rejoint la carte 45 s avant son heure (START puis phasage).
* **Contrôle « 8 min sans carte »** reporté quand une carte est prévue dans les 3 min.
* **Scans : P.AMP 1** imposé pendant toutes les mesures ; la protection contre la surcharge (P.AMP 0 puis
  atténuateur) reste prioritaire.
* **Veille spectrale** : octets recollés d'une lecture à l'autre (`FrameStream`), seule une trame terminée
  par FD est analysée ; balayage entièrement à zéro écarté (on attend le suivant) ; message d'arrêt selon
  ce qui est reçu (octets mais format inattendu / aucune donnée) ; `_scope_cmd` refuse toute commande
  autre que 27 xx (garde-fou d'émission).
* **Fenêtres** : « À propos » et bulles d'aide placées par rapport à la fenêtre principale
  (`ui/placement.py`), coordonnées négatives acceptées ; « À propos » passée au premier plan.
* **Vue directe** : une archive consultée reste affichée ; dès qu'une nouvelle carte a commencé et compte
  5 lignes, retour automatique à la vue en direct.
* **Afficheur du poste** : l'indicatif commence après le texte de service ; nom de station raccourci
  avant le S-mètre. **Ligne « Ensuite »** : prochaines cartes et bulletins mêlés dans l'ordre des heures,
  éléments entiers sur deux lignes au plus (`ui/text_fit.py`).
* **Journal** : pendant une écoute texte silencieuse, une ligne par minute (« 📡 Écoute NAVTEX-INT 518.0
  kHz : aucune FSK 170 Hz reconnue (Mark … dB · Space … dB) · 0 car. · P.AMP OFF · S-mètre … ») ; entrée
  audio nommée avec son interface Windows et avertissement si ce n'est pas l'entrée du poste ; WEB_SYNC :
  « le document en ligne n'est pas lu automatiquement » (alerte si le document a changé).

## Reste à confirmer sur la station
* Veille spectrale : ligne « 🔭 Veille spectrale ±250 kHz autour de … » avec DDH7 / Northwood / Athènes.
* « À propos » et bulles d'aide sur l'écran PL2480H (cause multi-écran déduite, pas observée directement).
* Règle carte prioritaire, P.AMP 1 au scan, contrôle reporté : vérifiés au simulateur seulement.
* Programme DWD : à comparer à la carte « programme d'émission » diffusée par le DWD à 14:25 et 14:45 UTC.
* Cartes non reconnues après un scan et NAVTEX muet : causes inconnues, enregistrements nécessaires.

## Vérifications
* Autotest « 2.9.0 » : placement multi-écran, À propos, méthodes appelées toutes définies, retour à la vue
  directe, trames réelles du 18/11 coupées à toutes les positions, octets par morceaux et balayage vide,
  garde-fou 27 xx, message d'arrêt, programme DWD et mise à niveau des fichiers locaux, règle de priorité
  (analyse, prévision ≤ 48 h reçue ou non, avis, vagues, analyse imminente), contrôle reporté, bulletins
  reçus, P.AMP de référence et surcharge, entrée audio, ligne d'état NAVTEX, afficheur NAVTEX, ligne
  « Ensuite ».

# Version 2.8.9 (18/11/2026) — bascules WEFAX ⇄ RTTY fiabilisées, veille spectrale

## Audit de la soirée du 18/11 (journal de la 2.8.8 sur le poste de l'opérateur)
* 18:04 bascule en RTTY pour la « Prévision 5 jours Atlantique Est » (DDH7, 78 %) : correcte.
* 18:05:15 NNNN de la note de service qui précède le bulletin : correctement ignoré.
* 18:33:33 NNNN du bulletin (8 916 caractères, archivé) … puis l'émetteur enchaîne sans boucle RY / CQ
  sur un autre bulletin (« ZCZC 022 SMEN43 », observations SYNOP, hors plan). L'automatisme attendait
  30 s de boucle de service ou la fin d'un texte qui ne venait pas : **il est resté en RTTY**. Retour
  manuel à 18:35:43 ; la carte FSXX48 de 18:30 était perdue (bulletin plus long que son créneau).
* Le P.AMP automatique était en essai de P.AMP 2 au moment du retour : **le poste est resté en P.AMP 2
  sur les cartes** (relu à 18:44:19 sur DDK3).
* Les décisions de l'automatisme n'étaient pas écrites au journal : impossible de savoir pourquoi il
  restait.
* Suivi en direct de 18:49 à 19:02 : NAVTEX La Maddalena (518 kHz) écouté de 18:49 à 19:01, aucun
  caractère décodé (réception MF à confirmer : antenne HF sur 518 kHz) ; retour aux cartes correct
  (carte prise en cours de route, STOP 19:02:24) ; mais le créneau NAVTEX La Garde de 19:00 n'a été
  rejoint qu'à 19:02:29, en passant par les cartes.

## Corrections
* **Fin de bulletin** : 12 s après le NNNN du bulletin d'intérêt, on passe au bulletin d'intérêt suivant
  s'il est dû (même fréquence si même programme), sinon retour aux cartes — sans attendre la boucle de
  service. Un NNNN ne clôt le bulletin que s'il ferme un vrai texte (≥ 500 caractères) ou si le créneau
  a commencé depuis plus de 4 min : la note de service qui précède le bulletin ne le coupe toujours pas.
* **Créneaux NAVTEX consécutifs** (18:50 → 19:00, 06:50 → 07:00) enchaînés directement ; le message
  en cours éventuel est archivé avant le changement de station.
* **Garde-fou** : jamais plus de 6 min au-delà du créneau prévu (fin NNNN perdue, texte sans fin).
* **« Revenir aux cartes »** (téléscripteur) passe par le même chemin que le retour automatique : le
  bulletin est marqué fait (avant, s'il restait plus de 2 min de créneau, l'automatisme repartait aussitôt
  en RTTY).
* **P.AMP automatique** : à chaque changement de station, un P.AMP posé par l'automatisme (ou un essai en
  cours) est ramené au réglage de base P.AMP 1.
* **Journal** : chaque changement de décision de l'automatisme est écrit (« 🤖 AUTOMATISME [RTTY] STAY —
  Bulletin RTTY en cours ») et la raison s'affiche dans le téléscripteur.

## Veille spectrale (nouveau)
* L'IC-705 n'a qu'un récepteur, mais son spectre (±250 kHz) est lu par CI-V toutes les 2 min, dans un fil
  séparé, **sans changer de fréquence ni couper la réception** ; l'écran du poste est remis comme avant.
  Réglé sur DDK3 7880 kHz, on voit DDH7 7646 (RTTY), Northwood 8040 et Athènes 8105 ; sur 4583 kHz,
  Northwood 4610 et Athènes 4481.
* Mesure : écart de la station au bruit (échelle 0-160 du spectre) → fort / net / faible / rien. Ce n'est
  pas la qualité de décodage : le scan reste juge.
* Utilisation : colonne « Vu sur le spectre » dans la fenêtre « Fréquences » ; un bulletin RTTY dont la
  station est vue forte depuis moins de 5 min est pris directement, sans scan ; journal à chaque
  changement. Option dans Réglages › Plan de réception › Veille de propagation.
* Aucune commande d'émission. Si le poste n'envoie pas son spectre, la veille s'arrête d'elle-même après
  3 essais (message au journal avec les octets reçus, pour diagnostic). Format de trame programmé
  d'après le guide CI-V Icom : **à confirmer sur le poste réel**.

## Vérifications
* Autotest « Bascules 2.8.9 » (enchaînement NNNN → SYNOP, avis → prévision, NAVTEX → NAVTEX,
  débordement, note de service, retour manuel, P.AMP au changement de station) et « Veille spectrale » (BCD, analyse, échange CI-V avec
  un IC-705 simulé, remise en l'état de l'écran, prise directe d'un bulletin). Ensemble : 100/100.

# Version 2.8.8 (18/11/2026) — radio branchée à chaud, P.AMP automatique, Winlink et téléscripteur simplifiés

## IC-705 branché après le lancement (bug)
* Câble USB oublié au démarrage puis branché : la CAT revenait, mais l'entrée audio restait « SIMU » et le
  scan était refusé (« Scan impossible ») — seul un redémarrage du logiciel réglait le problème.
  Cause : la bibliothèque audio (PortAudio) ne relit la liste des cartes son qu'à son lancement ; le
  « USB Audio CODEC » apparu ensuite restait invisible.
* La liste des cartes son est maintenant relue à chaque recherche automatique ; après une CAT réussie
  sans audio, l'application cherche l'entrée USB du poste pendant 30 s (elle apparaît souvent après le
  port COM), puis lance le scan.
* Surveillance du câble toutes les 5 s : plus aucun son pendant 6 s (câble arraché) → passage propre en
  « attente de la radio », reconnexion seule dès que le câble revient (CAT + audio + scan), sans boîte
  d'erreur. Une reconnexion ne coupe plus un flux audio qui fonctionne.

## P.AMP automatique (RTTY et WEFAX)
* Nouveau module `radio/auto_preamp.py`, piloté par « AUTO RF (P.AMP + ATT) » (ex-« Contre-réaction auto »).
* Le préampli amplifie aussi le bruit : il n'aide que si le bruit du récepteur domine celui de la bande.
  Donc l'application **essaie et mesure** au lieu de supposer :
  * fading (SNR en chute de 4 dB sous sa valeur habituelle, ou sous le seuil du mode) → essai du cran
    supérieur ; gardé si le SNR gagne au moins 1,5 dB, sinon retour et pas de nouvel essai avant 5 min ;
  * signal revenu depuis 1 min → retour vers P.AMP 1, refusé (et bloqué 10 min) si le SNR y perd ;
  * surcharge (OVF) → descente immédiate, puis atténuateur si nécessaire ;
  * l'opérateur change lui-même le P.AMP → automatisme en pause 15 min.
* SNR mesuré : raies Mark/Space en RTTY, SNR de la porteuse en WEFAX ; rien n'est tenté sans émission
  entendue depuis 3 min. Chaque décision est écrite dans le journal (« 📶 P.AMP auto »).

## Winlink : un assistant en trois étapes (plus d'onglets)
* Une seule fenêtre : **1** choisir la passerelle (la meilleure pour l'heure est présélectionnée) ;
  **2 « CONNEXION À WINLINK »** : poste réglé et libéré, Winlink Express ouvert s'il est fermé, indicatif
  de la passerelle copié, puis les gestes à faire dans Winlink Express affichés pas à pas ;
  **3 « DÉCONNEXION · RÉCUPÉRER LE GRIB · RETOUR WEFAX / RTTY »** : GRIB reçus lus et résumés, réception
  météo reprise. Les deux boutons s'activent tour à tour.
* Si la fenêtre « Vara HF Winlink » tient encore le port de l'IC-705, l'application le dit et réessaie
  seule toutes les 15 s, sans boîte d'erreur.
* Diagnostic de l'installation, demande GRIB, fichiers reçus et premiers pas : petits boutons
  secondaires. Le menu « Winlink » ouvre directement l'assistant (ses six sous-entrées sont supprimées).

## Téléscripteur : retrouver les bulletins reçus
* Nouvelle colonne **« Bulletins reçus »** : par jour (Aujourd'hui, Hier…), heure UTC, station, nature
  du bulletin en clair (« Avis de vent fort (WODL45) », « Prévision marine (FQME10) »…), fiabilité ;
  avis en rouge ; période 24 h / 3 jours / 7 jours ; recherche par station, code ou mot du texte.
* Un clic affiche le bulletin archivé (texte reçu + lecture en français) ; le direct continue en fond,
  « Revenir au direct » y ramène. Double-clic : ouvrir le fichier. Depuis « Météo & bulletin », un
  bulletin texte s'ouvre désormais dans le téléscripteur.
* Haut de fenêtre réduit à l'essentiel : émetteur, « Chercher la meilleure fréquence », « Revenir aux
  cartes », état du signal, programme. Les commandes générales (dernier scan, horaires Internet,
  rapport, mode de réception) restent dans les menus ; le bulletin d'essai passe dans les réglages du
  décodeur.

## Menus remis en ordre
* Règle : le menu ouvre les fenêtres et porte les commandes générales ; une fenêtre ne garde que les
  actions de sa tâche. Retirés car doublés : scan RTTY (téléscripteur), vent géostrophique (Météo &
  bulletin), sous-menu Winlink ; dans Réglages › Radio, « Horaires Web » et « Scanner RTTY ».

## Vérifications
* Autotest « 2.8.8 » : radio branchée après le lancement, câble arraché puis rebranché, quatre scénarios
  de P.AMP automatique, enchaînement des boutons Winlink, menu, archive du téléscripteur et recherche.
  Ensemble : 88/88 vérifications conformes.

# Version 2.8.7 (17/11/2026) — plateforme multi-sources : SYNOP, Athènes, Winlink et GRIB

## Observations SYNOP, navires et bouées
* Nouveau décodeur (`weather/synop.py`) des relevés codés OMM que la DWD diffuse entre ses prévisions :
  stations terrestres (AAXX), navires et bouées (BBXX, position lue dans le message). Vent, mer du vent,
  houle, pression et tendance sur 3 h, temps présent, visibilité, températures de l'air et de l'eau.
* Le rapport gagne une rubrique **« Observations récentes »** (les plus proches d'abord) et une alerte en
  tête quand on **mesure** force 7 ou plus, 4 m de mer, ou une baisse de pression de 3 hPa en 3 h.
* Les messages d'observations vides (« NIL ») restent écartés.

## Cartes d'Athènes
* Station SVJ4 (8105 kHz le jour, 4481 kHz) : seules cartes centrées sur la Méditerranée. Créneau
  quotidien 08:45-10:45 UTC, écouté automatiquement (jamais au détriment d'une carte en cours), retour
  aux cartes habituelles ensuite. Option dans Réception › Plan de réception. Réception au Cannet à
  confirmer : ces fréquences sont prévues pour la Grèce.

## Winlink (nouveau menu)
* **Assistant** (`app/winlink_desk.py`, `winlink/`) : lit l'installation de Winlink Express et de VARA HF,
  sans jamais la modifier.
  * **État** : diagnostic de VARA HF pour l'IC-705 (carte son, port de commande d'émission, version
    gratuite, journal), avec la marche à suivre.
  * **Passerelles** : les meilleures passerelles HF à l'heure choisie, d'après l'indice de liaison que
    Winlink Express calcule depuis le locator ; fréquence d'affichage USB-D ; passerelles « VARA HF »
    standard d'abord pour la version gratuite ; trop proches (< 60 km) écartées.
  * **Session** : un bouton règle l'IC-705 sur la passerelle, met la réception en pause et libère le
    port CI-V et la carte son pour VARA ; « Reprendre la réception météo » reconnecte tout.
  * **Météo par Winlink** : demande GRIB Saildocs prête à copier (zone autour du QTH, taille et durée
    de transfert estimées).
  * **Fichiers reçus** : les réponses de Saildocs sont lues dans les messages Winlink (toutes les 10 min
    et à la fin de chaque session), le GRIB est copié dans le dossier de l'application.
  * **Premiers pas** : guide pas à pas en français.
* **Décodeur GRIB 1** intégré (`weather/grib.py`, sans bibliothèque externe) : vent au point le plus proche
  et maximum dans le secteur, pression, vagues ; rubrique **« Prévision numérique »** dans le rapport
  (moins de 36 h), présentée comme prévision brute de modèle à comparer aux bulletins.

## Vérifications
* Nouvelle série d'autotest « Sources 2.8.7 » : bouée et SYNOP décodés, alerte de baisse de pression,
  GRIB encodé puis relu, diagnostic VARA, classement des passerelles, réponse Saildocs lue une seule
  fois, demande Saildocs, créneau d'Athènes.

# Version 2.8.6 (17/11/2026) — bulletin rédigé sur tous les bulletins reçus, NAVTEX réel, cartes entières

Constats faits sur la nuit du 16 au 17/11 (12 cartes GYA3, 8 bulletins DDH7, écoute NAVTEX 518 kHz de
07:37 à 07:57 UTC), journal, fichiers produits et enregistrements audio à l'appui.

## Rédaction du bulletin (sécurité)
* **Le rapport se fondait sur le dernier message reçu.** Le 17/11 à 07:05 c'était une synop vide
  (« SMEN43 … NIL ») : le rapport concluait « aucune prévision à moins de 500 km » alors que la prévision
  Méditerranée de 04:14 annonçait en mer Ligure (112 km) force 7-8, rafales 10, mer 5 m. Il s'appuie
  maintenant sur un **dossier** (`weather/dossier.py`) : tous les bulletins archivés des 30 dernières
  heures, messages sans prévision écartés (synops AAXX/BBXX, NIL, informations de service), prévision la
  plus récente pour chaque zone. Même méthode dans « Météo & bulletin ».
* **Source exacte** : chaque bulletin est cité avec sa station, sa fréquence, son heure et son âge (le
  rapport indiquait « NAVTEX-FR 490 kHz », la fréquence d'écoute du moment).
* **Zones reçues mais illisibles** listées, les proches en premier (« ⚠ GOLFE-LION, à 237 km — reçu mais
  ILLISIBLE »). Sans prévision proche, le texte dit « aucune prévision reçue… cela ne signifie PAS que la
  mer est calme » au lieu de « ce bulletin ne concerne pas votre secteur ».
* **Tendance jour par jour** (pire niveau du jour dans votre secteur).
* Rapport : qualité des cartes mesurée sur les cartes archivées (pixels fiables), messages écartés comptés.
* Noms espagnols et italiens des zones NAVTEX reconnus (LEON, PROVENZA, LIGURIA, CORCEGA…).

## Lecture des bulletins RTTY
* **Réparation prudente des tableaux** (`weather/rtty_repair.py`) : lignes coupées recollées, inversion
  lettres/chiffres perdue corrigée (« 23 18. 00TC » = « WE 18. 00Z »), jour et heure déduits de la
  séquence des échéances. Une force ou une mer illisible n'est jamais devinée : la ligne est écartée.
* Un en-tête de point illisible n'attribue plus ses échéances au point précédent (le golfe du Lion était
  lu comme une suite du Skagerrak) ; en-tête abîmé rapproché d'un point connu quand c'est sûr.
* **Fiabilité = proportion de lignes réellement lisibles** : le bulletin Méditerranée au tiers illisible
  était noté 99 % [A]. La lisibilité figure dans l'en-tête de chaque fichier archivé.
* **Un nouveau ZCZC ferme le bulletin précédent** quand son NNNN a été perdu (fin du bulletin mer du Nord et
  prévision Méditerranée étaient dans un seul fichier de 39 min).
* Points nommés par leur position (« 38N 16W ») et en-têtes précédés d'un caractère parasite lus.

## NAVTEX
* **Créneaux réels** : La Maddalena R (518 kHz, 06:50 / 18:50), Cabo la Nao X (518 kHz, 07:50 / 19:50),
  La Garde W (518 kHz, 11:40 / 23:40), La Garde S (490 kHz, 07:00 / 19:00), La Maddalena I (490 kHz,
  09:20 / 21:20). Les anciens « H+50 / H+40 toutes les 4 h » ne correspondaient à aucune émission météo.
  La Garde est signalé « temporairement suspendu » par l'OHI (2023-2024) : les deux autres émetteurs
  couvrent aussi Provence, Ligure, Lion et Corse.
* **Écoute jusqu'à la fin du créneau** (10 min) : elle était abandonnée après 6 s à 1 min sans signal.
  Un choix manuel de fréquence texte ouvre un créneau de 15 min.

## Cartes WEFAX
* **Une carte n'est plus coupée par un évanouissement** : après un START, 4 min sans signal sont tolérées
  avant la durée normale de la carte (80 s auparavant), et une ligne qui garde la structure d'une carte
  compte comme du signal. Cinq cartes de la nuit avaient été coupées en deux (premier morceau jeté).
* Un bulletin DWD est ignoré quand toutes ses fréquences ont été mesurées muettes dans les 45 dernières
  minutes : la carte GYA de 03:00 avait été perdue pour un texte illisible sur DDK9 (9 %).

## Interface
* **Téléscripteur intégré** : pendant une écoute RTTY ou NAVTEX, la zone centrale affiche le texte reçu en
  direct (papier sombre, caractères ambre), la station, ce qui est attendu et l'heure de fin d'écoute,
  avec un bouton « Revenir aux cartes ». La carte revient d'elle-même au retour en WEFAX.
* **Aide › À propos** : logo F4NMK, auteur, rappel que les repères ne remplacent pas les bulletins
  officiels. 73 !
* La liste des fréquences décrit les émetteurs NAVTEX réellement écoutés.

## Vérifications
* Nouvelle série d'autotest « Nuit du 17/11 » (ligne réparée, zone illisible, synop vide ignorée, NAVTEX,
  ZCZC sans NNNN, rapport 1 clic).

# Version 2.8.5 (16/11/2026) — bulletins lus correctement, traduction réelle, menus simplifiés

Constats faits sur l'application en fonctionnement le 16/11 (DDK9 10100,8 kHz en RTTY, DDK3 7880 kHz en
WEFAX), journal, fichiers produits et enregistrement audio à l'appui.

## Lecture des bulletins (sécurité)
* **Échéances du mardi, mercredi, jeudi et dimanche ignorées** (`weather/rtty_parse.py`). Le programme 1 du
  DWD est en anglais (MO TU WE TH FR SA SU) ; seules MO, FR et SA étaient reconnues.
* **Lignes avec rafales rejetées** : la colonne rafales (« W 7  9-10  3.5 M ») n'existait pas dans le
  motif de lecture ; toute échéance comportant des rafales disparaissait. Le 16/11, la mer Ligure à
  112 km (force 7, rafales 9-10, mer 3,5 m) était résumée en « jolie brise, force 4 ».
* Les rafales entrent dans le niveau (rafales de force 9 = vent établi de force 8) et sont écrites en
  clair, avec leur vitesse.
* **« Aucune prévision à moins de 500 km »** n'est plus affiché tant que le bulletin est en cours : les
  zones arrivent l'une après l'autre. Le message devient « réception en cours », puis une conclusion
  seulement après le NNNN.
* Un point proche n'apparaît plus deux fois (les tableaux étaient relus comme un bulletin par zones, avec
  une plage de vent fausse « force 2-7 »).
* La **situation générale** du bulletin est reprise, traduite, dans « ce qu'il faut retenir ».

## Repère de niveau
* Les pastilles de couleur s'affichaient sous Windows en ronds gris de tailles différentes. Remplacées
  par une jauge : **■□□□ 1/4, ■■□□ 2/4, ■■■□ 3/4, ■■■■ 4/4 — plus il y a de cases pleines, plus le risque
  est élevé** — colorée dans la fenêtre, avec la légende en toutes lettres.

## Traduction
* Nouveau traducteur hors ligne par expressions (`weather/marine_translate.py`) : phrases réellement
  traduites, tableaux réécrits ligne à ligne (« mar. 17  12 h UTC : SO  force 6  rafales 8  mer 2,5 m »).
  Un mot inconnu reste en MAJUSCULES dans sa langue d'origine. L'ancien glossaire ne remplaçait que
  quelques mots (« ISOLATED SEVERE ORAGES WITH HEAVY PLUIE »).
* Le panneau de droite ne revient plus en haut à chaque ligne reçue.

## Archivage des bulletins
* **Un bulletin = un fichier, une seule fois** (`hybrid/window.py`, `hybrid/arbiter.py`). Le 16/11 chaque
  bulletin DDK9 a été archivé trois fois, et chaque fichier reprenait tous les bulletins précédents de la
  session. Fins de ligne RTTY normalisées (plus de ligne vide entre chaque ligne).

## Cartes
* **Netteté à la réception** (Réglages › Image) : Automatique, Détail ou Robuste. La fiche de chaque carte
  indique le réglage, le SNR estimé et le filtre utilisé.
* Enregistrement audio : la limite (15 min) arrêtait l'enregistrement en silence, bouton resté sur
  « REC ON », sans fiche. Limite portée à 25 min au moins, arrêt annoncé, bouton mis à jour.

## Interface
* **Cinq menus au lieu de six menus et deux listes** : Réception, Cartes, Bulletins, Réglages, Aide
  (`app/menus.py`). Chaque commande à un seul endroit ; les listes « Cartes ▾ » et « Réception ▾ » de la
  barre de commandes sont supprimées.
* **Profil « Membre ADRASEC »** (Réglages › Opérateur & observations) : coché, le rapport en un clic est le
  « Rapport ADRASEC » au format cellule ORSEC ; décoché, un « Rapport météo » sans mention ADRASEC. Un
  profil créé avant la 2.8.5 reste en mode ADRASEC.
* En mode bulletins, le bandeau d'étapes indique la réception du texte au lieu de « WEFAX non identifié ».
* Fenêtre téléscripteur : titres raccourcis.

## Dossiers
* Plus de dossier `StationWEFAXPro/Operateurs/` (doublon vide de `donnees/operateurs/`), ni un journal de
  démarrage de plus à chaque lancement (`configuration/demarrage/journal_demarrage.csv`, réécrit).

## Vérifications
* `outils/autotest.py` : 61 vérifications sur 61, dont 6 nouvelles sur le bulletin DWD anglais.
* Décodeur RTTY rejoué sur l'enregistrement réel de DDK9 (15 min) : 59 lignes de tableau bien formées
  sur 87 contre 54 avec le décodeur de la 2.8.2 ; en fin d'enregistrement (signal dégradé) un NNNN est
  perdu que l'ancien décodait.

## Reste à faire
* Netteté : aucun enregistrement audio d'une carte DDK n'a pu être obtenu ; le mode « Détail » n'est pas
  validé sur signal réel.
* Carte reprise en cours de route après un bulletin (pas de phasage) : le recadrage automatique laisse
  parfois une bande du bord droit à gauche.
* RTTY : après une inversion lettres / chiffres perdue, des groupes chiffrés sont rendus en lettres.

# Version 2.8.4 (16/11/2026) — cartes complètes, bulletins conservés, RTTY fiabilisé, application portable

Base : 2.8.2 telle qu'installée. Deux séries de corrections : celles tirées de la réception réelle du
15/11, et celles du rapport `AUDIT_2.8.3.md` qui ont pu être reproduites puis vérifiées par la mesure.

## Corrections retenues du rapport d'audit
* **D1 — filtres WEFAX adaptés au signal** (`dsp/wefax_demod.py`, `BW_PROFILES`). Trois largeurs
  (650/800, 900/1200, 1100/1500 Hz), choisies d'après un SNR estimé sur la fluctuation rapide de
  l'enveloppe (écart mesuré avec le SNR réel du banc : 1 dB au-dessus de 10 dB). Seuils mesurés et non
  ceux du rapport : 19 dB et 24 dB (à 14–17 dB le filtre large dégradait la carte), plus une garde de
  stabilité du niveau (sous fading l'étroit reste meilleur). Banc : PSNR 27,7 → 28,9 dB à 30 dB,
  27,7 → 28,3 dB à 20 dB, identique en dessous et sous fading. Sur vos enregistrements GYA3 du 15/11 le
  SNR estimé reste sous 19 dB : le profil étroit est conservé, les cartes sont inchangées.
* **D2 — RTTY : caractères fantômes pendant un repos sur mark** (`rtty/fsk.py`) : plancher de bruit
  commun aux deux voies.
* **D3 — RTTY : suivi de seuil sous fading** : oubli de crête en 5 bits au lieu de 16 (8 et 12 bits
  essayés sur 16 tirages, moins bons sous fading fort).
  Mesure des deux corrections ensemble, message de 170 caractères avec 3 s de repos, 8 tirages, taux
  d'erreur avant → après : bruit blanc 20 dB 5,1 → 0,0 % ; 6 dB 8,9 → 0,0 % ; fading moyen 12 dB
  8,0 → 0,2 % ; fading fort 12 dB 12,8 → 1,8 % ; fading moyen 6 dB 11,6 → 0,9 % ; parasites 12 dB
  10,2 → 0,4 %.
* **D5 — START / STOP sous fading sélectif** (`dsp/wefax_demod.py`) : second critère, amplitude ≥ 20 %
  et raie ≥ 20 fois le fond. Banc, fading moyen 12 dB : START 5,3 → 7,3 et STOP 3,7 → 5,0 sur 10.
  Aucune fausse détection sur vos deux enregistrements (2 727 lignes).
* **D6 — horloge** : seuil de couverture à 60 % (voir plus bas). La régression sur les deux fronts de
  l'impulsion n'est pas reprise.
* **D9 — `ZCZC` / `NNNN` à un caractère près** (`rtty/segmenter.py`, `find_marker`), en mot isolé
  uniquement ; en direct, le mot doit être terminé.
* Test « Bulletin lu pour la zone de la case » : il dépendait de l'heure d'exécution, corrigé.

## Corrections de l'audit NON retenues
* **D4 — détection automatique des images satellite.** Le critère proposé (plus de 35 % de gris moyens)
  classe vos cartes au trait réelles en images satellite : elles contiennent 27 à 52 % de gris moyens à
  cause du bruit. Appliqué tel quel, il aurait supprimé le traitement « carte au trait » sur les cartes
  du 15/11. À reprendre avec un critère validé sur une vraie image satellite.
* **D7 — IOC 288** : aucune station de votre plan n'émet en IOC 288 ; non vérifiable ici.
* **D8 — garde d'inversion lettres / chiffres** : elle réécrit le texte reçu d'un bulletin de sécurité
  sur une heuristique, sans signal réel pour la valider.
* Combinaison souple NAVTEX : le rapport lui-même ne mesure aucun gain.

## Corrections issues de la réception réelle du 15/11 (préparées sous le nom 2.8.3, jamais diffusées seules)

Constats faits sur la réception réelle du 15/11 (GYA3 8040 kHz, DDH7 7646 kHz), journal et
enregistrements WAV à l'appui.

### Décodage WEFAX
* **Plus aucune ligne remplacée par du gris** (`app/reception.py`). Le squelch (SNR spectral moins
  « pénalité de fading », jusqu'à 14 dB) passait sous le seuil sur un tiers des lignes d'une carte reçue
  S9 : 404 lignes sur 1250 effacées sur la carte de 19:36 UTC, 17 à 20 % sur deux autres. Le
  démodulateur les avait décodées. Le squelch ne sert plus qu'à attendre une carte et à détecter la
  perte du signal (80 s) ; la queue sans signal est alors retirée de la carte archivée.
* **Phasage reçu en cours de carte** : 6 lignes de phasage consécutives après la ligne 100 closent la
  carte en cours et ouvrent la suivante, calée sur ce phasage (STOP et START manqués pendant un fading).
* **Horloge de la carte son** (`dsp/wefax_demod.py`) : lignes de phasage retenues dès 60 % de couverture
  (85 % auparavant, jamais atteint sur signal réel : la mesure ne démarrait pas). Mesuré sur
  l'enregistrement de 19:36 : −25 ppm, pente résiduelle −0,015 px/ligne au lieu de −0,061.
* **Fiabilité d'une carte** (`weather/reliability.py`) : calculée sur toutes les lignes de la carte
  (SNR moyen, lignes exploitables, phasage, START) et non plus à l'instant de l'archivage, où le signal
  a déjà disparu (toutes les cartes étaient notées 8 % [D]). Fiche JSON : `snr_proxy_db` = moyenne de la
  carte, nouveau champ `lignes_exploitables_pct`.

### Bulletins RTTY
* **Un fichier par bulletin** (`hybrid/arbiter.py`). Tous les bulletins d'une même session RTTY portaient
  le même identifiant et s'écrasaient : le 15/11, WODL45 (avis de coup de vent), NODL41 et FEAE75
  (8983 caractères) ont été remplacés par le « NIL » reçu en dernier. Un fichier existant n'est plus
  jamais remplacé.

### Portabilité
* Plus rien dans `%LOCALAPPDATA%` (`app/main_window.py`, `storage/portable.py`) : le journal CSV de
  démarrage, `last_operator.json` et les préférences provisoires vont dans
  `StationWEFAXPro/configuration/` à côté du programme.

### Affichage et ergonomie
* **Textes illisibles** (`app/styling.py`) : le contraste texte / fond est vérifié sur toute fenêtre qui
  s'ouvre ; un texte noir ou gris sur fond sombre passe en clair (fenêtre « Analyse physique assistée »
  notamment). Conteneurs défilants et onglets au thème sombre.
* Bandeau d'étapes : « 3. APT START » et « 4. Phasage » restent validés avec l'heure pendant le tracé ;
  « 2. Signal Radio » affiche le SNR mesuré.
* Carte : le cartouche « MODE : IMAGE BRUTE » (qui masquait le titre de la carte) est supprimé ;
  l'étiquette de tracé est sous la ligne en cours ; elle n'affiche plus « TEST_BLANC » en pleine carte.
* Réglages › 3 devient « Opérateur & observations » : les commandes en double avec « Météo & bulletin »
  (Annoter, Repérer, Copier, Enregistrer) sont retirées, un bouton ouvre cette fenêtre.
* Météo & bulletin › Bulletin : barre d'outils sur deux rangées (elle débordait de la fenêtre).


## Vérifications
* `outils/autotest.py` : 55 vérifications (54 de la 2.8.2, dont une qui échouait, plus le contrôle
  « deux bulletins = deux fichiers »).
* Rejeu dans l'application des deux enregistrements GYA3 du 15/11 : 0 ligne effacée, fiabilité 78 % [B].
* `outils/banc_hf.py` : WEFAX et NAVTEX comparés à la 2.8.2 (NAVTEX inchangé à la variance du banc près).
* Limite : essais faits sous Linux avec écran virtuel, pas sur Windows ni avec l'IC-705.

## Reste à faire
* Sur un tirage simulé (fading moyen 5 dB) le nouveau suivi de seuil RTTY perd un `NNNN` final que
  l'ancien décodait ; en moyenne sur 16 tirages il fait mieux. À confirmer sur un enregistrement réel.
* La queue d'une carte dont le STOP est manqué garde encore quelques dizaines de lignes bruitées.
* Origine de ligne à vérifier (40 à 90 px du bord droit repliés à gauche sur les cartes GYA3).
* Suivi d'horloge pendant l'image, décodage SYNOP / SHIP, NAVTEX sur signal réel.

# Version 2.8.2 (15/11/2026) — la zone d'analyse est la case de l'opérateur

* La CASE placée sur la carte (Réception › Placer la zone d'analyse) est désormais LA zone d'analyse
  pour tout : lecture en clair des bulletins RTTY / NAVTEX, bulletin « Météo & bulletin », rapport ADRASEC.
* Repérage de la carte (Réception › Repérer la carte, ou Réglages › Analyse météo, ou Météo & bulletin) :
  3 clics (ou plus) sur des croisements méridien / parallèle dont on saisit les coordonnées
  (« 40N 10E », « 45 N 5 O », « 43.5, -7 »). L'écart résiduel est affiché en km. Le repérage est
  mémorisé par famille d'émetteur et type de carte (configuration/reperage_cartes.json).
* Le centre et le rayon de la case sont alors calculés automatiquement et affichés sur la case
  (« ZONE 43,6°N 7,0°E, rayon 215 km ») ; chaque bulletin indique d'où vient sa zone.
* La case dessinée est mémorisée (centre + taille) et reprise au lancement suivant.
* Tant que la carte n'est pas repérée : repli sur la position déclarée (Réglages › Plan de réception),
  signalé dans le bulletin.

# Version 2.8.1 (15/11/2026) — bulletins lisibles par tous

Constat : le rapport ADRASEC et la fenêtre RTTY recopiaient le texte reçu (« MO 16. 00Z: S-SW 4
0.5 M ») et une « traduction » identique : illisible pour un opérateur non spécialiste ou un
destinataire, et sans dire si cela concerne le secteur (l'exemple portait sur la mer du Nord).

Nouveau module `weather/plain_language.py`, utilisé par la fenêtre RTTY, le bulletin et le rapport ADRASEC :
* **Est-ce que ça me concerne ?** Chaque point ou zone est situé (mer, distance à votre position) :
  « votre côte » jusqu'à 150 km, « votre bassin » jusqu'au rayon choisi (500 km par défaut), le reste
  en une ligne. Un bulletin hors secteur le dit clairement et indique les prochains bulletins utiles.
* **Est-ce dangereux ?** Niveau 🟢 / 🟡 / 🟠 / 🔴 calculé sur le vent (Beaufort) et la mer, avec la
  conduite à tenir ; mention claire que ce n'est pas une vigilance officielle.
* **Quand ?** Jours et moments de la journée en heure de Paris.
* **En mots courants** : « jolie brise (20-28 km/h, force 4) ; mer peu agitée (1 m) », avec un encadré
  « Comment lire ».
* Bulletins par zones en anglais / allemand (golfe du Lion, Provence, Ligure, Corse, Baléares…) et
  avis de coup de vent reconnus.
* Rapport ADRASEC réorganisé : ce qu'il faut retenir, puis cartes, qualité de réception expliquée en
  mots, et le texte original en annexe seulement (retours à la ligne doublés du RTTY supprimés).
* Réglages › Plan de réception : votre position (Le Cannet par défaut) et le rayon d'intérêt.

# Version 2.8.0 (15/11/2026) — plan de réception, Yaesu, image, interface et bulletin

Analyse du journal de 08:54-10:06 UTC et des données du 15/11 (GYA4, DDK6, DDH9).

## Ce que montrait la journée
* 08:59 → 09:28 : 29 min sans rien faire après le STOP de GYA4 ; à 09:28, scan avant une carte
  « ICE/BALT » qui n'a jamais été émise, puis 11 min d'attente ; le scan RTTY a dû être lancé à la main.
* 09:42 : fin du bulletin DDH9 (NNNN), puis 8 min de boucle « RYRY / CQ » enregistrées dans le bulletin.
* 09:50 → 10:02 : carte « Sea Surface Temperatures » coupée à L.1496 par le filet « porteuse blanche »
  alors que son cartouche arrivait ; le reste (271 lignes) a été jeté au STOP ; recadrage à −524 px faux.

## Plan de réception (nouveau, `hybrid/scheduler.py`)
* Programmes RTTY réels du DWD (P1 anglais : DDK2, DDH7, DDK9 ; P2 allemand : DDH47, DDH9, DDH8) et
  créneaux météo NAVTEX de La Garde (518 kHz W : 11h40 / 23h40 ; 490 kHz S : 07h00 / 19h00).
* Réglages › 4 · Plan de réception : catégories voulues (avis, Méditerranée, NAVTEX, Atlantique…),
  programmes, veille. Par défaut : avis, Méditerranée, NAVTEX, Atlantique, programme 1.
* Règles : une carte en cours n'est jamais interrompue ; le bulletin est pris à son heure ou juste
  après le STOP ; retour aux cartes sur NNNN, 30 s de boucle de service, 60 s sans signal ou fin du
  créneau ; bulletin archivé sans la boucle de service.
* Plus de « Pré-carte » sur des horaires WEFAX inventés : sans carte depuis 8 min, contrôle des autres
  fréquences de la même famille.
* Au démarrage, après le scan WEFAX, mesure des fréquences RTTY (dès que le poste est libre).

## Table de propagation et veille légère
* Chaque fréquence garde sa dernière qualité mesurée, son heure et sa source (scan, veille, réception).
* Veille au plus toutes les 30 min (45 min la nuit), uniquement dans le temps mort après un STOP,
  ≤ 4 fréquences de 3 s, retour sur la fréquence de départ : ≤ 8 changements de fréquence par heure.
* La bascule RTTY va directement sur la meilleure fréquence si sa mesure a moins de 30 min.
* Fenêtre « 📋 Fréquences » (barre de commandes, menu Bulletins, Réglages, téléscripteur) : toutes les
  stations avec leur dernier résultat ; double-clic = accorder sans rescanner ; « Mesurer la sélection ».

## Yaesu (nouveau, `radio/yaesu.py`)
* CAT ASCII : FT-991/991A, FT-891, FT-710, FTDX10, FTDX101D/MP, FT-450D, FT-950, FT-2000, FTDX3000/5000
  (modèle identifié par « ID ») : DATA-USB, AGC FAST, NR et notch auto coupés, fréquence relue.
* CAT 5 octets : FT-817/818, FT-857, FT-897 : mode DIG, fréquence relue, S-mètre.
* Modèle « AUTO (Icom puis Yaesu) » par défaut ; garde-fou : aucune commande d'émission envoyée.
* Le scan WEFAX fonctionne avec les Yaesu (il sautait toutes les stations hors Icom).
* Testé sur postes simulés (pas de Yaesu disponible) : à valider sur un vrai poste.

## Image
* Fin de carte : plus de coupure sur une zone blanche interne. Fin sur STOP, ou 2 min de porteuse
  uniforme, ou 80 s sans signal ; hauteur maximale 2400 lignes.
* Lignes uniformes retirées en tête et en queue à l'archivage (jamais une ligne avec du dessin).
* Recadrage : coupe au milieu de la bande blanche verticale (vote par blocs de 50 lignes) ; rien si la
  bande n'est pas nette (carte partielle). Avec phasage reçu, rien n'est déplacé.
* Restauration guidée par la carte de confiance : pixels peu fiables réparés à partir des lignes
  voisines, stries supprimées, fond blanc, netteté renforcée à l'horizontale ; un pixel bien reçu n'est
  jamais modifié par la réparation (pointillés et petits caractères préservés).
* Indicateurs de début / preuve de carte conservés lors de l'initialisation de la feuille (une carte
  prise en cours de route n'est plus refusée à l'archivage).

## Interface
* Afficheur façon façade de poste : fréquence en 7 segments, indicatif, puces (VFO, mode, filtre, AGC,
  préampli), S-mètre à segments, fiabilité ; remplace la ligne « station · fréquence » et le bandeau
  orange ; se compacte sur petit écran.
* Barre de commandes allégée : « Rapport ADRASEC » (menu Bulletins, fenêtre Météo & bulletin),
  « Réseau » (menu Automatisation), « Aide qualité » (menu Aide) ; ajout de « 📋 Fréquences ».
* Menu Automatisation : mode d'exploitation (cartes + bulletins, cartes seules, bulletins seuls,
  manuel) et accès Internet.
* Ligne « Ensuite » : prochains bulletins réellement planifiés (plus de texte tronqué).

## Météo & bulletin (nouveau, `app/bulletin_desk.py`)
* Réceptions 24 h (cartes et bulletins, fiabilité, ouverture du fichier, choix pour le bulletin).
* Bulletin compilé et modifiable : cartes reçues, bulletins texte analysés (prévisions ponctuelles
  lues et résumées en français : vent dominant, force maximale et échéance, mer, phénomènes ;
  avertissements repérés), observations et évolution de l'opérateur, qualité de réception.
* Statistiques par station et table de propagation.

## Tests
* Autotest : zone blanche interne et recadrage, plan de réception (décisions, veille, bascule et retour),
  Yaesu FT-991A / FT-817 simulés. Rejeu des trois enregistrements DDK6 : cartes complètes, droites.

# Version 2.7.1 (15/11/2026) — corrections issues du premier essai terrain et interface adaptative

Analyse du journal et des cartes du 15/11/2026 (DDK3 7880 kHz, DDK6 13882,5 kHz).

## Démarrage et radio
* Au lancement, la connexion CAT est suivie du **scan complet des fréquences** (meilleure carte retenue),
  comme « Démarrer en auto ».
* **Radio éteinte au démarrage** : plus de boîte d'erreur bloquante. L'application l'indique dans la barre
  d'état et réessaie toutes les 15 s ; dès que l'IC-705 répond, connexion puis scan automatiques.
* Contrôle de liaison CAT : 3 essais (la première trame après ouverture du port est parfois perdue).

## Réception WEFAX
* **Porteuse de repos du DWD** (blanc continu entre deux cartes) : elle n'est plus tracée. Rien n'est
  dessiné tant qu'aucune carte n'est identifiée (START, phasage ou 8 lignes ayant la structure d'une
  carte). Cause de la feuille blanche de 1492 lignes archivée à 07:40.
* STOP reçu sur une feuille quasi vide (≤ 100 lignes) : feuille abandonnée, attente du START suivant.
* Porteuse non modulée pendant 60 s : fin de carte (archivée seulement si ≥ 200 lignes).
* Une feuille sans contenu WEFAX identifiable n'est plus archivée (fragment de 41 lignes de bruit DDK3
  archivé à 07:27 lors de la relance).
* La fin de la salve START n'est plus tracée en haut de carte (bande hachurée sur la carte de 07:54).
* L'enregistrement automatique démarre bien au START (il était arrêté par l'archivage précédent).
* **Correction de pente** mesurée sur la carte entière à l'archivage, et seulement si elle dépasse
  0,008 px/ligne (≈ 10 px sur une carte). L'estimation précoce (lignes 120-300) inclinait à tort une carte
  droite : 0,035 px/ligne estimés sur l'enregistrement DDK6 de 08:04 pour < 0,005 réels.
* Relecture d'un enregistrement : la carte archivée porte la station et la fréquence du WAV (et non
  plus celles du poste).

Mesures sur les trois enregistrements DDK6 du 15/11 (07:43, 08:04, 08:17, 683 s chacun) :
START, phasage et STOP détectés sur les trois ; horloge de la carte son de l'IC-705 < 2 ppm (aucune
correction nécessaire) ; écart d'accord constant de −7 à −9 Hz corrigé par l'AFC ; 91 à 95 % de
pixels fiables.

## Interface — adaptée à toutes les tailles d'écran (1024×600 à 4K)
* Barre de commandes « en flux » : les boutons passent à la ligne au lieu d'être coupés.
* Tableau de bord sur 3 colonnes (largeur ≥ 1180 px) ou empilé en dessous ; bandeau des étapes compacté
  sur les écrans bas (détail affiché dans la barre d'état au survol).
* Bouton « ▴ Tableau de bord » et touche **F9** pour le replier (carte agrandie) ; **F11** plein écran ;
  menu **Affichage**. Sur un écran de 600 px de haut, le tableau de bord est replié d'office.
* Barre d'état toujours visible en bas ; la carte est redessinée à chaque redimensionnement et le
  repérage souris/zoom suit la taille réelle.
* La zone « ZONE MANUELLE » n'est plus superposée à la carte hors de l'outil de sélection.
* Panneau de qualité redessiné (RF brut, bande, pic, qualité WEFAX, qualité RTTY) lisible à toute taille.

# Version 2.7.0 (15/11/2026) — chaîne de décodage alignée sur les spécifications, pour la HF perturbée

Références appliquées : caractéristiques OMM des émissions fac-similé HF (porteuse 1900 Hz, ±400 Hz
— ±425 Hz pour le DWD —, IOC 576, 120 lignes/min, START 5 s à 300 Hz, phasage 60 lignes de « 25 ms
blanc + 475 ms noir », marge blanche de 25 ms en tête de chaque ligne, STOP 5 s à 450 Hz puis 10 s de
noir) ; ITA2 (RTTY DWD 50 Bd, shift 450 Hz, 85 Hz sur DDH47) ; CCIR 476 / ITU-R M.476-M.625
(NAVTEX SITOR-B, 100 Bd, shift 170 Hz, contrôle 4B/3Y, répétition DX/RX).

## WEFAX — nouveau démodulateur continu (`dsp/wefax_demod.py`)

* Traitement en flux, sans rupture d'une ligne à l'autre (l'ancien démodulait chaque bloc de 0,5 s isolément).
* Suppresseur d'impulsions (QRN) adapté à un signal à enveloppe constante.
* Canal en bande de base 1250–2550 Hz, discriminateur continu, **confiance par échantillon** :
  les creux de fading et les parasites ne pèsent plus sur l'image ; les trous courts sont comblés par
  leurs voisins, les trous longs sont signalés.
* **Carte de confiance** archivée avec chaque carte (`_confiance.png`) et proportion de pixels fiables
  dans le JSON : on sait quelles zones de la carte sont mesurées et lesquelles sont reconstituées.
* START / STOP détectés par l'amplitude cohérente de la tonalité de commutation (pleine excursion
  noir/blanc) : un brouilleur ou un battement ne déclenche plus de faux STOP. START IOC 288 (675 Hz) reconnu.
* Phasage : impulsion blanche de 5 % (spécification), position mesurée à l'échantillon près ; l'origine
  de ligne est calée sur le **front** de l'impulsion (début de ligne), plus sur son milieu.
* **Horloge de la carte son mesurée** pendant le phasage (dérive de l'impulsion ligne à ligne, pente
  robuste, correction seulement si elle est statistiquement sûre) puis appliquée au découpage des lignes :
  la carte sort droite, sans slant. La valeur est mémorisée par périphérique audio
  (`configuration/horloge_audio.json`).
* **AFC** sur des références normalisées (fond noir du phasage, marge blanche des lignes), sélectionnées
  par position et non par valeur (aucun biais) : corrige une erreur d'accord jusqu'à ±100 Hz.
* Plus aucune perte d'audio quand l'interface est momentanément occupée (sauvegarde d'une carte…) :
  l'ancien code jetait l'audio au-delà de 1,1 s de retard, ce qui décalait les lignes suivantes.

Mesures au banc (carte de test, 3 tirages, démodulateur seul ; corrélation avec la carte émise) :

| Condition | Ancien | Nouveau | START (sur 10 lignes) ancien → nouveau | STOP ancien → nouveau |
|---|---|---|---|---|
| Propre | 0,979 | 0,981 | 10 → 10 | 10 → 10 |
| SNR 10 dB | 0,934 | **0,955** | 10 → 10 | 10 → 10 |
| SNR 3 dB | 0,795 | **0,819** | 10 → 10 | 10 → 10 |
| Fading moyen, 12 dB | 0,789 | **0,873** | 3,7 → 5,3 | 2,7 → 3,7 |
| Fading fort, 10 dB | 0,680 | **0,760** | 4,3 → 6,0 | 8,0 → 8,7 |
| Flutter, 15 dB | 0,894 | 0,885 | 10 → 10 | 9 → 10 |
| Parasites QRN, 15 dB | 0,867 | **0,962** | 10 → 10 | 10 → 10 |
| Erreur d'accord +40 Hz | 0,968 | 0,968 | 10 → 10 | 10 → 10 |
| Horloge carte son +120 ppm | 0,772* | **0,980** | 10 → 10 | 10 → 10 |
| Brouilleur 2 kHz | 0,909 | 0,918 | 10 → 10 | **16 (faux) → 10** |

\* avant la correction de slant de fin de carte, qui rattrapait en partie l'erreur dans l'ancienne version.
Phasage reconnu sous QRN : ancien 1 ligne sur 60, nouveau 61. Coût : ≈ 11 ms par ligne (500 ms disponibles).

## RTTY et NAVTEX — nouvelle chaîne (`rtty/fsk.py`, `rtty/ita2_async.py`, `rtty/sitorb.py`)

* L'ancien décodeur ne restituait aucun texte, même sur un signal parfait au banc : il ne gardait que
  les deux dernières trames de chaque bloc audio, et son filtre « lexical » rejetait le reste.
  De plus, la boucle RTTY tronquait l'audio à 1,5 s.
* **NAVTEX ne pouvait pas fonctionner** : le poste est accordé 1,9 kHz sous la fréquence publiée (les
  tonalités arrivent donc autour de 1900 Hz), mais le décodeur les attendait autour de 1700 Hz.
  La table CCIR 476 inversait aussi CR et LF et prenait le signal RQ pour le signal de phasage β.
* Démodulateur FSK : deux filtres adaptés (intégration sur une durée de bit), **ATC** (seuil suivi
  séparément pour chaque tonalité : le fading sélectif éteint souvent une seule des deux), AFC par
  barycentre de puissance des tonalités.
* RTTY : trames vérifiées (start + stop), polarité automatique, pas d'« unshift on space » (norme ITA2 ;
  les groupes chiffrés SYNOP/SHIP du DWD sont restitués).
* NAVTEX : horloge bit synchrone (boucle avance/retard), alignement des mots par contrôle 4B/3Y (avec
  levée de l'ambiguïté du phasage α/β), **combinaison des copies DX et RX**, correction d'un bit sur
  décision souple, caractère d'erreur « * », messages ZCZC B1B2B3B4 … NNNN avec taux d'erreur et
  élimination des doublons (≤ 4 %). Chaque message est journalisé.
* Squelch : validité des trames + contraste marche/arrêt des tonalités (bruit seul ≈ 9 dB, signal
  ≥ 12 dB même à 0 dB de SNR) : **zéro caractère parasite sur du bruit**, sans filtre lexical.

| Condition (CER, 3 tirages) | RTTY ancien | RTTY nouveau | NAVTEX ancien | NAVTEX nouveau |
|---|---|---|---|---|
| Propre | 100 % | 0,8 % | 100 % | 0 % |
| SNR 5 dB | 100 % | 1,8 % | 100 % | 0 % |
| SNR 2 dB | 100 % | 2,6 % | 100 % | 0 % |
| Fading moyen, 15 dB | 100 % | 0,8 % | 100 % | 0 % |
| Fading fort, 12 dB | 100 % | 8,6 % | 100 % | 8,8 % |
| QRN, 12 dB | 100 % | 2,3 % | 100 % | 0,8 % |
| Accord +30 Hz | 100 % | 0,8 % | 100 % | 0 % |
| Horloge +200 ppm | 100 % | 1,0 % | 100 % | 0 % |

(Les ~1 % résiduels en RTTY correspondent surtout au caractère décodé avant la synchronisation.)
Le flutter (étalement Doppler de 10 Hz, propagation aurorale) reste hors de portée à 50 et 100 Bd.

## Scan

* Niveau 3 « structure WEFAX reconnue » : continuité verticale des lignes à 120 lignes/min, START /
  STOP / phasage, sur les 4 dernières secondes (`dsp/wefax_signature.py`). Une raie fixe (cas GYA3 /
  1896 Hz du journal du 14/11) est classée « porteuse fixe » et ne passe plus devant une vraie carte,
  même si elle est plus forte. Vérifié par l'autotest.
* L'ancien reclassement « 2300 Hz », qui ne s'exécutait jamais, est remplacé par ce critère.

## Réglages radio (`radio/profiles.py`)

* Profil unique et documenté pour WEFAX / RTTY / NAVTEX : USB-D, filtre 3 kHz, AGC FAST, **NR OFF,
  notch automatique OFF, notch manuel OFF** (le notch automatique pouvait supprimer la porteuse blanche
  2300 Hz ou une tonalité FSK), NB laissé au choix de l'opérateur.
* Les deux profils de l'ancienne version se contredisaient (l'un forçait NB ON, l'autre le conservait).
* Bande passante audio réelle mesurée sur le bruit après chaque changement de fréquence et journalisée
  (`PASSBANDE …`), avec alerte si la bande utile du mode n'est pas couverte.
* Filtre plus étroit pour RTTY/NAVTEX : volontairement non automatisé (position du filtre étroit en
  USB-D non garantie sur l'IC-705) ; à décider après mesure sur le poste.

## Enregistrement, relecture, outils

* Enregistreur WAV (bouton ⏺ REC, menu Enregistrements, mode automatique par carte), relecture d'un
  enregistrement dans la chaîne, `outils/analyse_wav.py`, `outils/banc_hf.py`.
* Sauvegarde de sécurité rétablie : `reception_en_cours.png` toutes les 60 s pendant une carte
  (écriture atomique), supprimée à l'archivage. L'archivage forcé en fragment après une perte de signal
  n'a **pas** été rétabli, pour ne pas scinder une carte pendant un fading.

## Vérifications

`outils/autotest.py` : 26 vérifications de bout en bout, toutes conformes. Une émission WEFAX
conforme OMM dégradée (SNR 15 dB, QRN, accord +25 Hz, horloge +80 ppm) est rejouée : START, phasage et
STOP sont reconnus, l'horloge est mesurée à +82 ppm, l'AFC corrige 21 Hz et la carte décodée corrèle à
0,97 avec la carte émise. Un message NAVTEX à 4 dB avec fading et un bulletin RTTY DWD à 5 dB avec
fading sont restitués sans erreur, et le scan préfère une vraie carte à une raie fixe plus forte.

Limites : tout cela est mesuré sur signaux simulés. Le réglage final se fera sur vos enregistrements
de terrain (menu Enregistrements).

---

# Refonte modulaire — version 2.6.0 (14/11/2026)

## Ce qui a été fait

L'ancienne version était un empilement de couches : une classe de base (2.0) puis quatre
sous-classes successives (2.1, 2.3, 2.4, 2.5), auxquelles s'ajoutaient trois séries de patchs
appliqués au démarrage (`part10`, `install_reception_banner`, `install_hf_bulletins_and_portable_core`).
Une même méthode pouvait être redéfinie jusqu'à 7 fois ; il fallait lire 6 fichiers pour savoir
ce qui s'exécutait réellement.

* Chaque méthode effectivement exécutée a été extraite de l'ancien programme assemblé, puis
  rangée **une seule fois** dans le module de son domaine. Le texte des méthodes est celui de
  la version précédente (reformaté de façon uniforme) ; seules les liaisons entre couches
  (`super()`, `orig_…`) ont été remplacées par des appels explicites à des méthodes nommées.
* Plus aucun patch dynamique, plus de script d'assemblage : chaque module importe explicitement
  ce qu'il utilise.
* Les quatre constructeurs successifs sont devenus des **phases d'initialisation nommées**
  (`main_window.py`), exécutées dans l'ordre exact de l'ancienne cascade.
* Mécanisme de **validation terrain** par module (empreintes SHA-256, contrôle au démarrage).
* **Autotest** de non-régression livré (`outils/autotest.py`).

## Code mort supprimé (≈ 1 400 lignes)

Ces éléments n'étaient jamais exécutés dans la version précédente :

* 49 anciennes versions de méthodes entièrement remplacées par une couche plus récente
  (ex. 5 versions de `_build_permanent_top_bar`, 3 de `_scan_next`, 2 superviseurs…).
* 5 correctifs de `hf_bulletins_and_portable_core` qui ne s'installaient jamais, car ils visaient
  des méthodes inexistantes : `_draw_selection_overlay`, `_refresh_canvas_image`,
  `_rf_verify_step`, `_scan_finish`, `_scan_finish_station`.
* Méthodes jamais appelées : `_auto_save_received_png_to_archive`, `_carrier_scan_worker`,
  `_checkpoint`, `_create_default_emblem_logo`, `_help_for_label`, `_diag_scan_next`.
* Reclassement « 2300 Hz » du scan (`_re_rank_last_scan_result_with_2300hz_intelligence`) :
  voir le point 2 ci-dessous.

## Corrections

1. **Démarrage sans PortAudio** : si la bibliothèque audio est absente, `sounddevice` lève
   `OSError` (et non `ImportError`) ; l'ancien programme s'arrêtait. Le démarrage se fait
   désormais avec l'audio désactivé.
2. **Journal tournant** : un message émis depuis un thread (connexion CAT, préparation RF)
   était écrit deux fois dans le journal tournant. Il n'est plus écrit qu'une fois.
3. **Chemins** : l'espace portable et le bouton « Compiler le .exe » se basent sur le dossier
   du lanceur (même emplacement qu'avant, sans dépendre du nom `wefax_modules`).

## Vérifications effectuées

Comparaison automatique ancienne / nouvelle version, sous Linux sans écran (Xvfb) :

* Démarrage : titre, géométrie, arbre complet des widgets, menus, fichiers créés et journal
  de démarrage **identiques**.
* Réception d'une carte synthétique complète (START, phasage, 240 lignes, STOP) :
  PNG décodé, traité et signé **identiques au pixel près**, métadonnées identiques
  (hors horodatages), journal identique.
* Scan des 7 fréquences avec IC-705 simulé : mêmes QSY, mêmes classements, même fréquence
  retenue, même séquence de journal.
* Ouverture des fenêtres et actionnement de 40 commandes : aucun écart, aucune exception.

Non vérifiable ici : liaison série réelle avec l'IC-705, carte son USB, rendu sous Windows.
Un premier essai sur le poste est nécessaire avant de valider les modules.

## Points constatés, conservés tels quels — à décider

Le comportement a été conservé à l'identique ; ces points méritent une décision :

1. **Superviseur neutralisé** : le socle hybride remplace `_supervisor` par une version vide.
   Avec lui ont disparu : la sauvegarde de sécurité `reception_en_cours.png` toutes les 60 s,
   l'archivage d'un fragment après 90 s de perte de signal, et la ligne `TELEMETRIE` du journal.
2. **Reclassement 2300 Hz inactif** : l'en-tête de `hf_bulletins_and_portable_core` annonce que
   GYA2 (vraie porteuse 2300 Hz) est préféré à GYA3 (raie fixe 1896 Hz). Ce code ne s'exécutait
   jamais (il attendait des variables `scan_current` / `scan_samples` jamais renseignées et un
   format de résultats différent). La sélection actuelle repose sur `assess_scan_audio`
   (`dsp/scan_diagnostics.py`). La méthode `evaluate_wefax_scan_candidate`
   (`weather/reliability.py`) reste disponible pour une intégration propre dans `app/scanner.py`.
3. **Bandeau supérieur construit deux fois** : la version 2.5 construit le bandeau 2.4 puis en
   détruit une partie pour le réorganiser (`_build_permanent_top_bar`, `_build_right_map_area`).
   Fonctionnel, mais une réécriture directe allégerait le démarrage.
4. L'en-tête du module hybride parle d'un blocage anti-scission dès la ligne 3 ; le code
   bloque à partir de la ligne 15.
