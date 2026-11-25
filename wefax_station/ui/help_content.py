"""Contenu de l'aide intégrée (rubriques F1)."""

import unicodedata

HELP_TOPICS_25 = {
    "demarrage": (
        "Démarrage et parcours conseillé",
        "1. Brancher l'IC-705 et vérifier que l'entrée audio USB sélectionnée correspond bien au poste, pas au microphone du PC.\n2. Fermer les autres applications susceptibles d'utiliser le même port CAT.\n3. Démarrer en auto : la connexion CAT et l'audio doivent être établis avant le scan.\n4. Vérifier la station choisie, le spectre et la progression des lignes. Un score spectral élevé ne suffit pas à prouver la présence d'une carte.\n5. Après la fin, consulter la dernière carte et vérifier le fichier archivé.\nLe programme peut recevoir sans Internet après installation. Le bouton Carte Web, lui, exige une connexion.\nConsulter [[audio|Entrée audio]], [[cat|Connexion CAT]], [[scan|Scan et changement de fréquence]] et [[archives|Cartes enregistrées]].",
    ),
    "interface": (
        "Interface, fenêtres et raccourcis",
        "L'écran principal regroupe sur un seul bandeau compact à 3 colonnes : la télémétrie RF, le centre de contrôle du récepteur HF (état, horaires UTC et commandes Cartes/Réception/Affichage) et le spectre BF, afin de laisser une place maximale à la carte météo.\nRéglages ouvre Radio / Image / Bulletin. Diagnostics conserve les informations techniques et le journal.\nF1 ouvre la rubrique du contrôle qui a le focus ; à défaut, celle sous le pointeur.\nBouton ⟳ Auto : apparaît en orange dans la barre supérieure dès que les automatismes sont suspendus (mode MANUEL, RELECTURE ou hold manuel). Un clic restitue immédiatement le contrôle automatique (passage en mode HYBRIDE). Le bouton disparaît quand l'automatique est actif.\nVoir [[affichage|Zoom et modes d'image]], [[stations|Bouton Stations (choix manuel)]] et [[diagnostic|Résolution des difficultés]].",
    ),
    "audio": (
        "Audio USB : choix et diagnostic",
        "L'entrée audio transporte le signal à décoder. La connexion CAT ne transporte pas nécessairement cet audio.\nChoisir le périphérique du poste dans Réglages / Radio. Vérifier sur le spectre que le signal change lorsque le poste est accordé sur un autre signal réel.\nUne entrée nommée Microphone (USB Audio CODEC) peut être celle du poste : le mot Microphone n'implique pas à lui seul une mauvaise entrée.\nLe menu Enregistrements capture l'audio brut en WAV (bouton ⏺ REC, ou automatiquement de START à la fin de carte) et permet de rejouer un enregistrement dans le décodeur. L'outil outils/analyse_wav.py analyse un enregistrement sans interface.\nL'erreur d'horloge de la carte son est mesurée sur le phasage et mémorisée par périphérique.\nVoir [[spectre|Lire le spectre]] et [[journal|Journal CSV]].",
    ),
    "cat": (
        "Commande CAT / CI-V",
        "La liaison CAT commande notamment la fréquence et certains réglages du récepteur. Pour l'IC-705, l'adresse par défaut est A4.\nVérifier le protocole, le port série et le débit. Éviter qu'un autre logiciel monopolise le même port.\nVoir [[scan|Scan]], [[rf|S-mètre et automatismes RF]] et [[diagnostic|Diagnostic]].",
    ),
    "scan": (
        "Scan, sélection et rescan",
        "Le scan teste les fréquences de la famille (DWD, Northwood, Athènes), attend l'établissement du signal puis compare plusieurs mesures. Une simple porteuse sans modulation WEFAX ne l'emporte pas sur le DWD quand une carte DWD est au programme.\nEntre deux cartes, la veille de propagation (30 min le jour, 45 min la nuit) et la veille spectrale (spectre du poste toutes les 2 min) tiennent à jour la meilleure fréquence de chaque station. Au retour d'un bulletin RTTY, une station vue forte sur le spectre il y a moins de 5 min l'emporte sur une mesure plus ancienne.\nVoir [[priorites|Priorités et famille de référence]], [[snr|Indicateur spectral]] et [[apt|Début et fin de carte]].",
    ),
    "rf": (
        "S-mètre, préamplificateur et atténuateur",
        "Le premier bargraphe représente la lecture RF renvoyée par le poste lorsque la liaison CAT est vérifiée. Sinon il affiche n/d.\nP.AMP automatique : en cas de fading, le cran supérieur est ESSAYÉ puis gardé seulement s'il améliore le rapport signal/bruit ; surcharge (OVF) : descente immédiate. Pendant le tracé d'une carte, chaque commutation marque l'image : au plus un essai toutes les 3 min, gardé seulement pour un gain d'au moins 3 dB, et aucune descente avant la fin de la carte. Les scans se font en P.AMP 1.\nVoir [[snr|SNR spectral estimé]], [[spectre|Spectre audio]] et [[journal|Journal]].",
    ),
    "snr": (
        "SNR spectral estimé : portée et limites",
        "Le deuxième bargraphe utilise l'indicateur calculé dans la bande audio. Il s'agit d'un score spectral relatif, pas d'un SNR RF étalonné.\nVoir [[scan|Sélection d'une fréquence]], [[traitement|Traitement d'image]] et [[diagnostic|Carte grise ou bruitée]].",
    ),
    "spectre": (
        "Courbe du signal : spectre audio",
        "Cette courbe montre la répartition de l'énergie selon la fréquence audio (1500 Hz Noir, 1900 Hz Centre, 2300 Hz Blanc).\nVoir [[audio|Entrée audio]], [[apt|Signaux de service]] et [[snr|SNR spectral]].",
    ),
    "programmes": (
        "Horaires UTC et prochaine carte",
        "Les programmes intégrés viennent des documents officiels : DWD d'après la NOAA (information du 24/07/2024, plan DWD 10/2020), Northwood d'après la NOAA (information du 05/01/2022, une carte toutes les 12 min), Athènes 08:45-10:45 UTC (réception au Cannet à confirmer). Toujours confirmer le type, la date et la validité sur le cartouche effectivement reçu ; le DWD diffuse lui-même son programme à 14:25 et 14:45 UTC.\nLa ligne « Ensuite » mêle les prochaines cartes et les prochains bulletins, dans l'ordre des heures.\nCompte à rebours dans la barre d'état : entre deux cartes, au lieu d'un message générique, la barre affiche directement le nom abrégé de la prochaine carte et le temps restant, par exemple « ⏱ Analyse de surface Atlantique Nord / Europe [ASXX] · dans 7 min ». Quand le délai est inférieur à 1 min, « imminente » s'affiche. Cet affichage se rafraîchit avec l'état du décodeur.\nProgramme observé : chaque START reçu est rattaché à l'heure du programme ; un créneau où le poste écoutait la station avec un bon signal sans recevoir de START est noté « muet » (ligne [PROGRAMME OBSERVÉ] au journal). Muet au moins 3 jours et jamais reçu, il est signalé « à vérifier » dans la fenêtre des sources officielles ; rien n'est retiré du programme sans vous.\nVoir [[sources|Mise à jour par les sources officielles]], [[horsligne|Fonctionnement sans Internet]] et [[priorites|Priorités]].",
    ),
    "apt": (
        "START, STOP, attente et reprise en cours",
        "Les tonalités de service permettent de détecter le début (300.0 Hz) et la fin (450.0 Hz) d'une carte.\nDès qu'un STOP est confirmé, la carte terminée est automatiquement enregistrée et le décodeur passe en attente du prochain START sans empiler deux cartes l'une sous l'autre.\nVoir [[archives|Dernière carte et direct]] et [[diagnostic|Décodeur qui attend]].",
    ),
    "affichage": (
        "Image décodée, traitée, comparaison et zoom",
        "Décodée montre l'image issue du décodeur avant le retraitement documentaire final.\nTraitée montre le rendu documentaire nettoyé (suppression des stries horizontales HF, blanchiment du papier et rehaussement des isobares). Comparer juxtapose les deux côtés.\nVoir [[traitement|Traitement]], [[geometrie|Marge et slant]] et [[archives|Historique]].",
    ),
    "geometrie": (
        "Marge, slant et orientation",
        "La marge est un déplacement circulaire horizontal sur les 1809 pixels de la ligne IOC 576 : ce qui sort d'un côté revient de l'autre sans aucune troncature de largeur.\nDès le début de carte, l'impulsion de phasage cale automatiquement l'origine de ligne, puis l'estimation affine le slant.\nVoir [[traitement|Conservation des détails]], [[archives|Copies corrigées]] et [[meteo|Orientation géographique]].",
    ),
    "traitement": (
        "Lissage et conservation des détails",
        "Le retraitement documentaire supprime les stries horizontales HF, égalise le fond papier et renforce le contraste des isobares et des chiffres.\nVoir [[affichage|Comparaison]], [[snr|Signal estimé]] et [[journal|Décisions de traitement]].",
    ),
    "archives": (
        "Archives, dernière carte et sauvegardes",
        "Dernière carte et Direct sont deux modes de consultation. Historique ouvre les images déjà enregistrées sans remplacer la réception active : voir [[consultation|Consulter une carte pendant une réception]].\nUne carte prise en cours de route (sans START ni phasage, haut de carte manquant : moins de 92 % d'une carte normale) n'est pas complète : elle est rangée dans le dossier cartes_partielles du jour, et « Dernière carte » continue d'afficher la dernière carte complète. Quand le poste change de famille (Northwood pendant le trou du programme DWD), il arrive 90 s avant l'heure de la carte suivante pour la recevoir entière.\nChaque fin de carte sauvegarde l'image décodée, l'image traitée, la carte de confiance (blanc = pixel mesuré de façon fiable, noir = pixel reconstitué pendant un fading ou un parasite), la carte signée et ses métadonnées JSON (proportion de pixels fiables, correction d'accord, erreur d'horloge de la carte son).\nVoir [[journal|Trouver le CSV]], [[signature|Logo et opérateur]] et [[apt|Fin de carte]].",
    ),
    "journal": (
        "Journal affiché, CSV et diagnostic",
        "Le journal de Diagnostics présente les événements récents. Le CSV en conserve une trace par session.\nVoir [[diagnostic|Diagnostic par symptôme]] et [[archives|Dossier utilisé]].",
    ),
    "signature": (
        "Logo et identification de l’opérateur",
        "Charger un logo ouvre un fichier image et affiche son aperçu. L'indicatif opérateur est distinct de l'identité du développeur.\nVoir [[archives|Exporter une carte]] et [[meteo|Portée du bulletin]].",
    ),
    "meteo": (
        "Analyse météo : mesures, échéances et limites",
        "Calcul d'un gradient et d'un vent géostrophique à partir de mesures confirmées.\nLe bulletin éditable conserve les observations et annotations ; relire avant diffusion ADRASEC.\nVoir [[geometrie|Nord et orientation]], [[programmes|Validité et horaires]] et [[archives|Sources du bulletin]].",
    ),
    "compilation": (
        "Compilation Windows en exécutable",
        "Compiler .exe appelle PyInstaller avec l'interpréteur Python qui exécute l'application.\nVoir [[diagnostic|Diagnostic]] et [[archives|Dossiers et fichiers]].",
    ),
    "diagnostic": (
        "Diagnostic par symptôme",
        "Aucune courbe : vérifier [[audio|l'entrée audio]].\nCAT sans réponse : vérifier [[cat|le port, le débit et l'adresse]].\nMarge automatique refusée : utiliser [[geometrie|la correction manuelle non destructive]].\nCâble USB débranché/rebranché : la connexion CAT est rétablie automatiquement dès que la signature du port change (détection toutes les 5 s). Le port fantôme est fermé proprement avant la reconnexion. Si la reconnexion échoue, vérifier qu'aucun autre logiciel n'a pris le port en charge pendant le débranchement.",
    ),
    "sources": (
        "Mise à jour des programmes par les sources officielles",
        "Menu Bulletins › Programmes : sources officielles. Quand Internet est joignable, le logiciel télécharge EN ENTIER, en arrière-plan, les documents officiels : programme radiofac-similé du DWD (dwd.de) et compilation mondiale de la NOAA (weather.gov). Ils sont conservés dans configuration/sources avec la date, la taille et l'empreinte SHA-256, puis leur texte est lu : heures de chaque station et date « INFORMATION DATED ».\nRésultat pour chaque station : CONFORME, DIFFÉRENCES (heures nouvelles ou absentes) ou texte peu exploitable (ouvrir le document pour le lire). Rien n'est modifié sans vous : Accepter enregistre le programme corrigé (configuration/programmes_acceptes.json, utilisé ensuite même hors ligne), Refuser le laisse tel quel. Une heure nouvelle reçoit un libellé générique : l'intitulé exact se lit sur le cartouche de la carte reçue.\nLecture : le tableau de chaque station est lu ligne à ligne (heure, vitesse 120/576, heure de référence, intitulé pour le DWD ; intitulé puis heure pour Northwood). Si le tableau n'est pas reconnu, aucune modification n'est proposée. Les adresses sont modifiables dans configuration/sources_officielles.json (https uniquement) ; si un site renvoie une page web au lieu du PDF, le lien PDF de la page est suivi une fois. Vérification automatique au démarrage puis au plus toutes les 6 h.\nVoir [[horsligne|Fonctionnement sans Internet]] et [[programmes|Programmes utilisés]].",
    ),
    "horsligne": (
        "Fonctionnement sans Internet (blackout, plan ORSEC)",
        "La réception des cartes et des bulletins n'utilise jamais Internet : programmes intégrés (ou acceptés), fréquences, traduction des bulletins et lexique sont dans le logiciel. Sans réseau, la vérification des sources échoue en arrière-plan et laisse une seule ligne « 📴 [SOURCES] Internet non joignable … la réception continue » ; aucune fenêtre ne bloque, aucune fonction n'attend le réseau.\nLe coupe-circuit réseau interdit tout accès Internet. Seuls Carte Web, la mise à jour des sources et les fonctions Winlink par Internet en ont besoin.\nVoir [[sources|Sources officielles]] et [[stations_texte|Stations texte en sommeil]].",
    ),
    "stations_texte": (
        "Stations NAVTEX / RTTY : écoute optionnelle et mise en sommeil",
        "Réglages › Plan de réception › Stations texte. Chaque station (La Maddalena R et I, Cabo la Nao X, La Garde W et S, programmes RTTY 1 et 2 du DWD) peut être activée ou non. La Garde est désactivée par défaut : l'OHI l'a annoncée « temporairement suspendue » (2023) puis « No operational » (2024) ; à réactiver si l'émission reprend.\nUne station écoutée jusqu'au bout de son créneau sans au moins 40 caractères décodés compte un échec (un créneau écourté par une carte ou par vous ne compte pas). Après 3 échecs de suite (NAVTEX) ou 5 (RTTY DWD), elle est mise en sommeil : propagation, antenne inadaptée (518/490 kHz demandent une antenne adaptée aux ondes moyennes) ou émetteur arrêté. Nouvel essai une fois par jour (NAVTEX) ou toutes les 6 h (RTTY) ; une réception la réactive. Le bouton Réactiver remet le compteur à zéro. Le temps libéré va aux cartes.\nVoir [[priorites|Priorités]] et [[horsligne|Fonctionnement sans Internet]].",
    ),
    "priorites": (
        "Priorités cartes / bulletins et famille de référence",
        "Une carte en cours n'est jamais interrompue. Une analyse de surface (situation présente, isobares) est prioritaire sur tout bulletin : prévision RTTY, avis RTTY ou créneau NAVTEX (décision F4NMK du 19/11/2026) ; à moins de 3 min de son heure, aucun bulletin n'est commencé. Un avis n'est interrompu par aucune autre carte. Une prévision de surface à 48 h au plus, une rediffusion d'analyse ou une carte d'avis de Northwood ne l'interrompent que si le bulletin a déjà été reçu dans les 12 dernières heures. Les analyses de Northwood sans heure de référence publiée sont traitées comme des rediffusions.\nLe DWD est la famille de référence : 2 min avant l'heure d'une carte DWD, le poste revient sur la meilleure fréquence du DWD ; la nuit (trou du programme DWD de 22:12 à 04:30), Northwood prend le relais.\nAthènes (08:45-10:45 UTC) n'est gardée que si sa modulation WEFAX est reconnue : sinon retour au DWD et nouvel essai 30 min plus tard, jamais dans les 3 min qui précèdent une carte DWD.\nVoir [[programmes|Programmes]] et [[stations_texte|Stations texte]].",
    ),
    "consultation": (
        "Consulter une carte pendant une réception",
        "« Dernière carte » ou une image de l'Historique remplacent l'affichage en direct, pas la réception : la carte en cours continue d'être décodée et enregistrée. Un bandeau orange posé sur l'image l'indique (« 👁 Consultation : … ») avec le bouton Revenir au direct.\nRetour automatique au direct : dès qu'une nouvelle carte commence (après 5 lignes), ou après 90 s sans action sur l'image consultée si une carte est en cours de réception. Toucher l'image (clic, molette) relance le délai.\nVoir [[archives|Archives]] et [[affichage|Modes d'image]].",
    ),
    "winlink": (
        "Winlink / VARA HF : réglages à faire vous-même",
        "Station WEFAX PRO n'émet jamais : pendant une session Winlink, elle libère le port CI-V et l'audio, et c'est VARA HF qui émet quand vous cliquez Start. Les réglages ci-dessous se font dans VARA, Winlink Express et le poste ; l'assistant Winlink › Installation les vérifie sans rien modifier.\n• IC-705 : DATA MOD = USB (SET › Connectors › MOD Input), mode USB-D pour le trafic de données.\n• VARA HF › Settings › Soundcard : entrée et sortie « USB Audio CODEC » du poste.\n• Winlink Express › session Vara HF Winlink › Settings › Radio Setup : modèle IC-705 s'il est proposé, adresse CI-V A4, port série du poste (COM14 chez F4NMK), commande d'émission par CAT plutôt que par VOX.\n• Niveau d'émission : avec le bouton Tune de VARA, régler pour que l'ALC du poste reste au seuil (indication nulle ou très faible). Un Drive VARA très bas (par exemple -25 dB) pour éviter l'ALC signale en général un USB MOD Level trop élevé sur le poste : baisser plutôt USB MOD Level et remonter le Drive. À confirmer sur votre station, ALC et puissance de sortie sous les yeux.\nVoir [[cat|Commande CAT]] et [[horsligne|Fonctionnement sans Internet]].",
    ),
    "prevision": (
        "Situation actuelle et prévision à 3-6 h",
        "Le bouton Météo & bulletin affiche en permanence l'aperçu du secteur dans 3 à 6 h : couleur du niveau d'attention (vert, jaune, orange, rouge) et indice de fiabilité. Il est recalculé toutes les 10 min et une minute après chaque bulletin archivé ; le détail apparaît au survol.\nLe même bloc ouvre le bulletin (fenêtre Météo & bulletin) et le rapport en un clic. Il sépare les FAITS (observations SYNOP / SHIP reçues près du secteur avec leur âge, votre observation, la prévision officielle en vigueur, la dernière carte d'analyse), la PRÉVISION REÇUE pour la période (bulletin texte, GRIB, avis de coup de vent) et l'ESTIMATION (évolution du vent, sens de la tendance barométrique).\nTendance sur 3 h : stationnaire < 0,1 hPa ; lente 0,1 à 1,5 ; 1,6 à 3,5 ; rapide 3,6 à 6 ; très rapide au-delà. Une baisse rapide annonce en général un renforcement du vent dans les heures qui suivent.\nIndice de fiabilité : chaque élément ajoute ou retire des points, listés sous l'indice (fraîcheur de la prévision, distance du point, GRIB, observations, accord entre sources, lisibilité des textes). Une seule source plafonne l'indice ; sans donnée, 0 % [D] et rien n'est inventé. A ≥ 80 %, B ≥ 62 %, C ≥ 42 %, D en dessous. L'indice dit ce que l'on sait, pas la météo : les avis officiels font foi.\nVotre observation se saisit dans Réglages › Opérateur & observations.\nVoir [[meteo|Analyse météo]] et [[stations_texte|Stations texte]].",
    ),
    "horloge": (
        "Horloge UTC",
        "L'afficheur du poste porte une horloge UTC en chiffres 7 segments bleu pâle, à côté du S-mètre. Tous les programmes des émetteurs (cartes, bulletins RTTY, NAVTEX) sont en UTC : l'heure de Paris a une heure d'avance en hiver, deux en été.\nSi la place manque (petit écran), l'horloge passe en HH:MM. Elle suit l'horloge de l'ordinateur : vérifier que Windows est à l'heure (synchronisation automatique).",
    ),
    "donnees": (
        "Où sont rangées les données",
        "Depuis la 2.10.0, les données (configuration, profils, archives de réception) sont dans un dossier commun à toutes les versions, à côté d'elles : par exemple D:\\Downloads\\StationWEFAXPro quand les versions sont dans D:\\Downloads. Au premier démarrage d'une nouvelle version, la configuration, les profils et les réceptions d'hier et d'aujourd'hui de la version précédente y sont copiés (rien n'est effacé) et l'index des réceptions est reconstruit ; une ligne du journal le dit.\nUn fichier portable_root_path.txt placé à côté du programme impose un autre dossier.\nSupprimer un ancien dossier de version ne supprime plus les archives. Archives : 7 jours et 1 500 Mo par défaut.\nGuide illustré (français / English) : menu Aide.\nDepuis la 2.11.0, chaque jour compte cinq dossiers : cartes (la carte finale et sa fiche ; sous-dossiers partielles et details pour les images techniques), bulletins (texte original et traduction côte à côte), mes_bulletins (vos bulletins), journaux et audio. Le brouillon du bulletin est dans le dossier de l'opérateur (brouillons). Les jours enregistrés par une version antérieure gardent leurs anciens dossiers, toujours lus ; outils/reorganiser_archives.py les range dans la nouvelle forme si vous le souhaitez (simulation par défaut).",
    ),
    "stations": (
        "Bouton Stations (choix manuel)",
        "Le bouton Stations de l'écran principal ouvre la liste de toutes les stations (WEFAX, RTTY, NAVTEX) avec leur dernière qualité mesurée. Double-clic ou « Accorder sur la sélection » : le poste passe sur la station choisie sans nouveau scan.\nUn choix WEFAX est GARDÉ jusqu'à la fin de la carte suivante (ou 45 min sans carte) : l'automatisme ne change plus de fréquence pendant ce temps et le libellé du bouton devient orange (« Stations — choix DDK3 »). Le bouton « Rendre la main à l'automatique » dans la fenêtre Stations reprend tout de suite le fonctionnement normal.\nBouton ⟳ Auto dans la barre supérieure : distinct du bouton Stations, il s'affiche en orange dès que le contrôle automatique est suspendu, quelle qu'en soit la cause (choix de station, bascule en mode MANUEL ou RELECTURE, hold manuel). Un seul clic relance immédiatement les automatismes. Il disparaît dès que l'automatique reprend la main.\nUtile quand le scan automatique se trompe (propagation changeante, station brouillée).",
    ),
}


def help_plain25(value):
    return "".join(
        c for c in unicodedata.normalize("NFD", str(value)) if unicodedata.category(c) != "Mn"
    ).casefold()
