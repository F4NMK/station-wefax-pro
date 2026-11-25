"""Traduction hors ligne des bulletins météo marine du DWD (anglais, un peu d'allemand) vers le français.

2.8.5 — remplace le glossaire mot à mot, qui ne traduisait que quelques mots isolés (« ISOLATED SEVERE
ORAGES WITH HEAVY PLUIE »). Les bulletins marine emploient un vocabulaire restreint : la traduction se fait
par EXPRESSIONS (la plus longue d'abord), avec quelques tournures (« FROM WESTERLY TO SOUTH-WESTERLY
DIRECTIONS », « GUSTS OF UP TO 10 BFT »).

Règles de sûreté :
* les nombres, heures, positions et groupes chiffrés ne sont jamais modifiés ;
* un mot que le traducteur ne connaît pas RESTE EN MAJUSCULES, dans sa langue d'origine : rien n'est
  deviné, et le lecteur voit d'un coup d'œil ce qui n'a pas été traduit ;
* les tableaux de prévisions ponctuelles sont réécrits ligne à ligne à partir des champs lus (jour, heure,
  direction, force, rafales, mer), jamais interprétés.
"""

import re

from wefax_station.weather.rtty_parse import _LINE, _POINT, DAYS, WX, _dir_fr

# ------------------------------------------------------------------------------ mers et zones
# anglais -> (nom français, forme avec « de », forme avec « en / dans »)
SEAS = {
    "WESTERN AND CENTRAL MEDITERRANEAN": (
        "Méditerranée occidentale et centrale",
        "de la Méditerranée occidentale et centrale",
        "en Méditerranée occidentale et centrale",
    ),
    "WESTERN MEDITERRANEAN SEA": (
        "Méditerranée occidentale",
        "de la Méditerranée occidentale",
        "en Méditerranée occidentale",
    ),
    "WESTERN MEDITERRANEAN": (
        "Méditerranée occidentale",
        "de la Méditerranée occidentale",
        "en Méditerranée occidentale",
    ),
    "CENTRAL MEDITERRANEAN": (
        "Méditerranée centrale",
        "de la Méditerranée centrale",
        "en Méditerranée centrale",
    ),
    "EASTERN MEDITERRANEAN SEA": (
        "Méditerranée orientale",
        "de la Méditerranée orientale",
        "en Méditerranée orientale",
    ),
    "EASTERN MEDITERRANEAN": (
        "Méditerranée orientale",
        "de la Méditerranée orientale",
        "en Méditerranée orientale",
    ),
    "WESTERN EUROPEAN SEA": ("mers d'Europe de l'Ouest", "des mers d'Europe de l'Ouest", "dans les mers d'Europe de l'Ouest"),
    "WESTERN EUROPEAN SEAS": ("mers d'Europe de l'Ouest", "des mers d'Europe de l'Ouest", "dans les mers d'Europe de l'Ouest"),
    "MEDITERRANEAN SEA": ("Méditerranée", "de la Méditerranée", "en Méditerranée"),
    "MEDITERRANEAN": ("Méditerranée", "de la Méditerranée", "en Méditerranée"),
    "LIGURIAN AND TYRRHENIAN SEAS": (
        "mers Ligure et Tyrrhénienne",
        "des mers Ligure et Tyrrhénienne",
        "en mers Ligure et Tyrrhénienne",
    ),
    "LIGURIAN SEA": ("mer Ligure", "de la mer Ligure", "en mer Ligure"),
    "LIGURIAN": ("mer Ligure", "de la mer Ligure", "en mer Ligure"),
    "TYRRHENIAN SEA": ("mer Tyrrhénienne", "de la mer Tyrrhénienne", "en mer Tyrrhénienne"),
    "TYRRHENIAN": ("mer Tyrrhénienne", "de la mer Tyrrhénienne", "en mer Tyrrhénienne"),
    "ADRIATIC SEA": ("Adriatique", "de l'Adriatique", "en Adriatique"),
    "ADRIATIC": ("Adriatique", "de l'Adriatique", "en Adriatique"),
    "IONIAN SEA": ("mer Ionienne", "de la mer Ionienne", "en mer Ionienne"),
    "AEGEAN SEA": ("mer Égée", "de la mer Égée", "en mer Égée"),
    "AEGEAN": ("mer Égée", "de la mer Égée", "en mer Égée"),
    "GULF OF LIONS": ("golfe du Lion", "du golfe du Lion", "dans le golfe du Lion"),
    "GULF OF LION": ("golfe du Lion", "du golfe du Lion", "dans le golfe du Lion"),
    "GULF OF GENOA": ("golfe de Gênes", "du golfe de Gênes", "dans le golfe de Gênes"),
    "BALEARIC SEA": ("mer des Baléares", "de la mer des Baléares", "en mer des Baléares"),
    "BALEARIC ISLANDS": ("Baléares", "des Baléares", "aux Baléares"),
    "BALEARICS": ("Baléares", "des Baléares", "aux Baléares"),
    "ALBORAN SEA": ("mer d'Alboran", "de la mer d'Alboran", "en mer d'Alboran"),
    "STRAIT OF GIBRALTAR": ("détroit de Gibraltar", "du détroit de Gibraltar", "dans le détroit de Gibraltar"),
    "STRAIT OF BONIFACIO": ("bouches de Bonifacio", "des bouches de Bonifacio", "dans les bouches de Bonifacio"),
    "CORSICA": ("Corse", "de la Corse", "en Corse"),
    "SARDINIA": ("Sardaigne", "de la Sardaigne", "en Sardaigne"),
    "SICILY": ("Sicile", "de la Sicile", "en Sicile"),
    "CRETE": ("Crète", "de la Crète", "en Crète"),
    "CYPRUS": ("Chypre", "de Chypre", "à Chypre"),
    "BLACK SEA": ("mer Noire", "de la mer Noire", "en mer Noire"),
    "NORTH SEA": ("mer du Nord", "de la mer du Nord", "en mer du Nord"),
    "BALTIC SEA": ("mer Baltique", "de la mer Baltique", "en mer Baltique"),
    "BALTIC": ("mer Baltique", "de la mer Baltique", "en mer Baltique"),
    "GERMAN BIGHT": ("baie Allemande", "de la baie Allemande", "en baie Allemande"),
    "ENGLISH CHANNEL": ("Manche", "de la Manche", "en Manche"),
    "BAY OF BISCAY": ("golfe de Gascogne", "du golfe de Gascogne", "dans le golfe de Gascogne"),
    "BISCAY": ("golfe de Gascogne", "du golfe de Gascogne", "dans le golfe de Gascogne"),
    "NORTH ATLANTIC": ("Atlantique Nord", "de l'Atlantique Nord", "en Atlantique Nord"),
    "ATLANTIC": ("Atlantique", "de l'Atlantique", "en Atlantique"),
    "IRISH SEA": ("mer d'Irlande", "de la mer d'Irlande", "en mer d'Irlande"),
    "NORWEGIAN SEA": ("mer de Norvège", "de la mer de Norvège", "en mer de Norvège"),
}
_PARTS = {
    "NORTHERN": "nord",
    "SOUTHERN": "sud",
    "EASTERN": "est",
    "WESTERN": "ouest",
    "CENTRAL": "centre",
    "NORTH-EASTERN": "nord-est",
    "NORTH-WESTERN": "nord-ouest",
    "SOUTH-EASTERN": "sud-est",
    "SOUTH-WESTERN": "sud-ouest",
    "NORTHEASTERN": "nord-est",
    "NORTHWESTERN": "nord-ouest",
    "SOUTHEASTERN": "sud-est",
    "SOUTHWESTERN": "sud-ouest",
}
_DIR_ADJ = {
    "NORTH-EASTERLY": "nord-est",
    "NORTH-WESTERLY": "nord-ouest",
    "SOUTH-EASTERLY": "sud-est",
    "SOUTH-WESTERLY": "sud-ouest",
    "NORTHEASTERLY": "nord-est",
    "NORTHWESTERLY": "nord-ouest",
    "SOUTHEASTERLY": "sud-est",
    "SOUTHWESTERLY": "sud-ouest",
    "NORTHERLY": "nord",
    "SOUTHERLY": "sud",
    "EASTERLY": "est",
    "WESTERLY": "ouest",
}
_DIR_NOUN = {
    "NORTHEAST": "nord-est",
    "NORTHWEST": "nord-ouest",
    "SOUTHEAST": "sud-est",
    "SOUTHWEST": "sud-ouest",
    "NORTH-EAST": "nord-est",
    "NORTH-WEST": "nord-ouest",
    "SOUTH-EAST": "sud-est",
    "SOUTH-WEST": "sud-ouest",
    "NORTH": "nord",
    "SOUTH": "sud",
    "EAST": "est",
    "WEST": "ouest",
}
_FORCE_WORDS = {
    "NEAR-GALE-FORCE": "de force 7 (grand frais)",
    "NEAR GALE FORCE": "de force 7 (grand frais)",
    "SEVERE-GALE-FORCE": "de force 9 (fort coup de vent)",
    "SEVERE GALE FORCE": "de force 9 (fort coup de vent)",
    "GALE-FORCE": "de force 8 (coup de vent)",
    "GALE FORCE": "de force 8 (coup de vent)",
    "VIOLENT-STORM-FORCE": "de force 11 (violente tempête)",
    "STORM-FORCE": "de force 10 (tempête)",
    "STORM FORCE": "de force 10 (tempête)",
    "HURRICANE-FORCE": "de force 12 (ouragan)",
    "HURRICANE FORCE": "de force 12 (ouragan)",
}
_DAYS_EN = {
    "MONDAY": "lundi",
    "TUESDAY": "mardi",
    "WEDNESDAY": "mercredi",
    "THURSDAY": "jeudi",
    "FRIDAY": "vendredi",
    "SATURDAY": "samedi",
    "SUNDAY": "dimanche",
}

# expressions figées, anglais (et allemand courant) -> français ; appliquées de la plus longue à la plus courte
PHRASES = {
    # en-têtes
    "ISSUED BY MARINE WEATHER SERVICE HAMBURG": "émis par le service météorologique maritime de Hambourg",
    "MARINE WEATHER SERVICE HAMBURG": "service météorologique maritime de Hambourg",
    "GENERAL SYNOPTIC SITUATION": "situation générale",
    "GENERAL SYNOPSIS": "situation générale",
    "SHIPPING FORECAST": "prévision maritime",
    "DWD FORECAST OF": "prévision du DWD du",
    "WIND FORCE: BEAUFORT, WAVE HEIGHT: METRE": "force du vent en Beaufort, hauteur des vagues en mètres",
    "WIND FORCE": "force du vent",
    "WAVE HEIGHT": "hauteur des vagues",
    "FORECAST FOR": "prévision pour",
    "FORECASTS": "prévisions",
    "FORECAST": "prévision",
    "OUTLOOK": "tendance ultérieure",
    "ISSUED AT": "émis à",
    "ISSUED BY": "émis par",
    # avis
    "NO GALE WARNING": "aucun avis de coup de vent",
    "NO WARNINGS": "aucun avis en vigueur",
    "NO WARNING": "aucun avis en vigueur",
    "STRONG WIND WARNING": "AVIS DE GRAND FRAIS",
    "NEAR GALE WARNING": "AVIS DE GRAND FRAIS",
    "GALE WARNING": "AVIS DE COUP DE VENT",
    "STORM WARNING": "AVIS DE TEMPÊTE",
    "PLEASE PAY ATTENTION TO LOCAL WARNINGS": "tenez compte des avis locaux",
    "LOCAL WARNINGS": "avis locaux",
    "WARNINGS": "avis",
    "WARNING": "avis",
    # verbes et tournures (formes invariables en genre)
    "CANNOT BE RULED OUT": "ne sont pas à exclure",
    "CAN NOT BE RULED OUT": "ne sont pas à exclure",
    "ARE EXPECTED": "sont à prévoir",
    "IS EXPECTED": "est à prévoir",
    "ARE ANTICIPATED": "sont à prévoir",
    "IS ANTICIPATED": "est à prévoir",
    "ARE FORECAST": "sont à prévoir",
    "ARE POSSIBLE": "sont possibles",
    "IS POSSIBLE": "est possible",
    "ARE LIKELY": "sont probables",
    "IS LIKELY": "est probable",
    "WILL INCREASE": "va se renforcer",
    "WILL DECREASE": "va faiblir",
    "WILL PERSIST": "va persister",
    "IN PATCHES": "par endroits",
    "AT TIMES": "par moments",
    "AT FIRST": "d'abord",
    "OVER THE NEXT FEW DAYS": "au cours des prochains jours",
    "DURING THE NIGHT": "pendant la nuit",
    "IN THE MORNING": "le matin",
    "IN THE AFTERNOON": "l'après-midi",
    "IN THE EVENING": "le soir",
    "NEAR THE COAST": "près des côtes",
    "COASTAL WATERS": "eaux côtières",
    "OPEN SEA": "large",
    "PARTICULARLY": "en particulier",
    "ESPECIALLY": "en particulier",
    "OCCASIONALLY": "par moments",
    "TEMPORARILY": "temporairement",
    "GRADUALLY": "progressivement",
    "LOCALLY": "localement",
    "MAINLY": "surtout",
    "EITHER": "non plus",
    "LATER": "plus tard",
    "TODAY": "aujourd'hui",
    "TONIGHT": "cette nuit",
    "TOMORROW": "demain",
    # vent
    "LOCALIZED STORM": "une tempête localisée",
    "LOCALISED STORM": "une tempête localisée",
    "STRONG WINDS": "des vents forts",
    "LIGHT WINDS": "des vents faibles",
    "MODERATE WINDS": "des vents modérés",
    "FRESH WINDS": "des vents frais",
    "NEAR GALE": "grand frais",
    "SEVERE GALE": "fort coup de vent",
    "VIOLENT STORM": "violente tempête",
    "HURRICANE": "ouragan",
    "GALE": "coup de vent",
    "STORM": "tempête",
    "GUSTS": "rafales",
    "GUST": "rafale",
    "SQUALLS": "grains",
    "WINDS": "vents",
    "WIND": "vent",
    "INCREASING": "se renforçant",
    "DECREASING": "faiblissant",
    "ABATING": "mollissant",
    "EASING": "mollissant",
    "BACKING": "tournant vers la gauche (backing)",
    "VEERING": "tournant vers la droite (veering)",
    "SHIFTING": "tournant",
    "BECOMING": "devenant",
    "VARIABLE": "variable",
    # temps sensible
    "ISOLATED SEVERE THUNDERSTORMS": "des orages violents isolés",
    "SEVERE THUNDERSTORMS": "des orages violents",
    "ISOLATED THUNDERSTORMS": "des orages isolés",
    "THUNDERSTORMS": "orages",
    "THUNDERSTORM": "orage",
    "HEAVY RAIN": "fortes pluies",
    "HEAVY SHOWERS": "fortes averses",
    "ISOLATED SHOWERS": "averses isolées",
    "SHOWERS": "averses",
    "FOG PATCHES": "bancs de brouillard",
    "DRIZZLE": "bruine",
    "RAIN": "pluie",
    "HAIL": "grêle",
    "SNOW": "neige",
    "FOG": "brouillard",
    "MIST": "brume",
    "POOR VISIBILITY": "mauvaise visibilité",
    "MODERATE VISIBILITY": "visibilité moyenne",
    "GOOD VISIBILITY": "bonne visibilité",
    "VISIBILITY": "visibilité",
    # mer
    "SEA STATE": "état de la mer",
    "VERY ROUGH": "mer très forte",
    "ROUGH": "mer forte",
    "SLIGHT": "mer peu agitée",
    "SMOOTH": "mer belle",
    "SWELL": "houle",
    # situation synoptique
    "LOW PRESSURE SYSTEM": "dépression",
    "LOW PRESSURE AREA": "zone dépressionnaire",
    "LOW PRESSURE": "basses pressions",
    "HIGH PRESSURE SYSTEM": "anticyclone",
    "HIGH PRESSURE": "hautes pressions",
    "COLD FRONT": "front froid",
    "WARM FRONT": "front chaud",
    "OCCLUDED FRONT": "front occlus",
    "OCCLUSION": "occlusion",
    "TROUGH": "talweg",
    "RIDGE": "dorsale",
    "DEEPENING": "se creusant",
    "WEAKENING": "s'affaiblissant",
    "FILLING": "se comblant",
    "INTENSIFYING": "se renforçant",
    "STATIONARY": "stationnaire",
    "MOVING": "se déplaçant vers",
    "EXTENDING": "s'étendant",
    "SLOWLY": "lentement",
    "RAPIDLY": "rapidement",
    "QUICKLY": "rapidement",
    "HPA": "hPa",
    "NIL": "néant",
    # allemand courant (programme 2)
    "SEEWETTERBERICHT": "bulletin météo marine",
    "WETTERLAGE": "situation météorologique",
    "VORHERSAGE": "prévision",
    "AUSSICHTEN": "tendance ultérieure",
    "STURMWARNUNG": "AVIS DE TEMPÊTE",
    "STARKWINDWARNUNG": "AVIS DE GRAND FRAIS",
    "ZUNEHMEND": "se renforçant",
    "ABNEHMEND": "faiblissant",
    "RECHTDREHEND": "tournant vers la droite",
    "RUECKDREHEND": "tournant vers la gauche",
    "SCHAUERBOEEN": "rafales sous averses",
    "GEWITTERBOEEN": "rafales d'orage",
    "SCHAUER": "averses",
    "GEWITTER": "orages",
    "NEBEL": "brouillard",
    "SICHT": "visibilité",
    "SEEGANG": "état de la mer",
    "STURM": "tempête",
    "BOEEN": "rafales",
    "TIEF": "dépression",
    "HOCH": "anticyclone",
    "NORDSEE": "mer du Nord",
    "OSTSEE": "mer Baltique",
    "MITTELMEER": "Méditerranée",
    "DEUTSCHE BUCHT": "baie Allemande",
}
# petits mots, traduits en dernier (et seulement s'ils restent)
_SMALL = {
    "THROUGHOUT": "sur l'ensemble",
    "BETWEEN": "entre",
    "DURING": "pendant",
    "UNTIL": "jusqu'à",
    "AROUND": "autour de",
    "ABOUT": "environ",
    "FROM": "de",
    "WITH": "avec",
    "NEAR": "près de",
    "OVER": "sur",
    "ALSO": "aussi",
    "THEN": "puis",
    "AND": "et",
    "FOR": "pour",
    "THE": "",
    "OF": "de",
    "OR": "ou",
    "IN": "dans",
    "ON": "sur",
    "AT": "à",
    "TO": "à",
    "IS": "est",
    "ARE": "sont",
    "A": "un",
    "AN": "un",
    "UND": "et",
    "BIS": "à",
    "IN DER": "dans la",
    "UTC": "UTC",
}


# 2.11.0 — pays et lieux cités dans les situations générales du DWD (forme avec article ; les
# contractions « de le » -> « du », « à les » -> « aux » sont faites en finition).
PLACES = {
    "NORTHERN IRELAND": "l'Irlande du Nord",
    "IRELAND": "l'Irlande",
    "SCOTLAND": "l'Écosse",
    "ENGLAND": "l'Angleterre",
    "GREAT BRITAIN": "la Grande-Bretagne",
    "BRITISH ISLES": "les îles Britanniques",
    "ICELAND": "l'Islande",
    "GREENLAND": "le Groenland",
    "FAROE ISLANDS": "les îles Féroé",
    "FAROES": "les îles Féroé",
    "SOUTHERN NORWAY": "le sud de la Norvège",
    "NORTHERN NORWAY": "le nord de la Norvège",
    "NORWAY": "la Norvège",
    "SWEDEN": "la Suède",
    "FINLAND": "la Finlande",
    "DENMARK": "le Danemark",
    "SCANDINAVIA": "la Scandinavie",
    "SOUTHERN SCANDINAVIA": "le sud de la Scandinavie",
    "BALTIC STATES": "les pays Baltes",
    "ST PETERSBURG": "Saint-Pétersbourg",
    "ST. PETERSBURG": "Saint-Pétersbourg",
    "SAINT PETERSBURG": "Saint-Pétersbourg",
    "MOSCOW": "Moscou",
    "RUSSIA": "la Russie",
    "WESTERN RUSSIA": "l'ouest de la Russie",
    "UKRAINE": "l'Ukraine",
    "BELARUS": "la Biélorussie",
    "POLAND": "la Pologne",
    "GERMANY": "l'Allemagne",
    "NORTHERN GERMANY": "le nord de l'Allemagne",
    "SOUTHERN GERMANY": "le sud de l'Allemagne",
    "NETHERLANDS": "les Pays-Bas",
    "BENELUX": "le Benelux",
    "BELGIUM": "la Belgique",
    "FRANCE": "la France",
    "SOUTHERN FRANCE": "le sud de la France",
    "NORTHERN FRANCE": "le nord de la France",
    "SPAIN": "l'Espagne",
    "PORTUGAL": "le Portugal",
    "IBERIAN PENINSULA": "la péninsule Ibérique",
    "IBERIA": "la péninsule Ibérique",
    "ITALY": "l'Italie",
    "NORTHERN ITALY": "le nord de l'Italie",
    "SOUTHERN ITALY": "le sud de l'Italie",
    "PO VALLEY": "la plaine du Pô",
    "ALPS": "les Alpes",
    "PYRENEES": "les Pyrénées",
    "BALKANS": "les Balkans",
    "GREECE": "la Grèce",
    "TURKEY": "la Turquie",
    "MALTA": "Malte",
    "MOROCCO": "le Maroc",
    "ALGERIA": "l'Algérie",
    "TUNISIA": "la Tunisie",
    "LIBYA": "la Libye",
    "EGYPT": "l'Égypte",
    "NORTH AFRICA": "l'Afrique du Nord",
    "AZORES": "les Açores",
    "CANARY ISLANDS": "les Canaries",
    "MADEIRA": "Madère",
    "FRAM STRAIT": "le détroit de Fram",
    "FRAM STRAIGHT": "le détroit de Fram",
    "DENMARK STRAIT": "le détroit du Danemark",
    "SVALBARD": "le Svalbard",
    "SPITSBERGEN": "le Spitzberg",
    "BARENTS SEA": "la mer de Barents",
    "NORTH CAPE": "le cap Nord",
    "SKAGERRAK": "le Skagerrak",
    "KATTEGAT": "le Kattegat",
    "BOTHNIAN BAY": "la baie de Botnie",
    "GULF OF FINLAND": "le golfe de Finlande",
    "GULF OF RIGA": "le golfe de Riga",
}
_RE_PLACE = None  # compilé plus bas (après _alt)

# 2.11.0 — verbes et tournures des situations générales (« MOVES A BIT TO THE NORTH WHILE WEAKENING »),
# des avis et des avertissements de navigation NAVTEX ; appliqués avant le tableau PHRASES.
SYNOPTIC = {
    "STRONG WIND, GALE AND STORM WARNINGS FOR SEA AREAS": "avis de grand frais, de coup de vent et de tempête pour les zones maritimes",
    "STRONG WIND, GALE AND STORM WARNINGS": "avis de grand frais, de coup de vent et de tempête",
    "STRONG WIND AND GALE WARNINGS": "avis de grand frais et de coup de vent",
    "NO WARNINGS IN FORCE": "aucun avis en vigueur",
    "NO WARNING IN FORCE": "aucun avis en vigueur",
    "WARNINGS IN FORCE AT": "avis en vigueur au",
    "WARNINGS IN FORCE": "avis en vigueur",
    "IN FORCE": "en vigueur",
    "NAVIGATIONAL WARNING NO.": "avertissement de navigation n°",
    "NAVIGATIONAL WARNING NO": "avertissement de navigation n°",
    "NAVIGATIONAL WARNINGS": "avertissements de navigation",
    "NAVIGATIONAL WARNING": "avertissement de navigation",
    "CANCEL NAVIGATIONAL WARNING NO.": "annuler l'avertissement de navigation n°",
    "CANCELLED": "annulé",
    "CANCELED": "annulé",
    "CURRENTLY NOT AVAILABLE": "momentanément indisponible",
    "NOT AVAILABLE": "indisponible",
    "MEDIUM RANGE": "moyenne échéance",
    "SEA AREAS": "zones maritimes",
    "SEA AREA": "zone maritime",
    "A TROUGH FROM A LOW": "un talweg issu d'une dépression",
    "A BIT": "un peu",
    "ARE PARTICULARLY EXPECTED": "sont à prévoir en particulier",
    "IS PARTICULARLY EXPECTED": "est à prévoir en particulier",
    "IN PARTS OF": "sur une partie de",
    "IN PARTS": "sur une partie",
    "IN SOME PARTS OF": "sur une partie de",
    "WAVE HEIGHTS WILL REACH": "les vagues atteindront",
    "WAVE HEIGHTS OF": "des vagues de",
    "WAVE HEIGHTS": "hauteur des vagues",
    "THE WIND AND WAVES": "le vent et les vagues",
    "WIND AND WAVES": "le vent et les vagues",
    "WILL GRADUALLY DECREASE": "faibliront progressivement",
    "WILL GRADUALLY INCREASE": "se renforceront progressivement",
    "WILL BUILD UP": "se lèvera",
    "WILL REACH": "atteindront",
    "WILL SPREAD": "s'étendra",
    "WILL CONTINUE": "se poursuivra",
    "WILL WEAKEN": "faiblira",
    "WILL DIMINISH": "faiblira",
    "WILL SUBSIDE": "s'apaisera",
    "WILL ABATE": "mollira",
    "WILL TURN": "tournera",
    "WILL BE": "sera",
    "ONCE AGAIN": "de nouveau",
    "AGAIN": "de nouveau",
    "ACROSS THE ENTIRE": "sur l'ensemble de",
    "THE ENTIRE": "tout",
    "ENTIRE": "tout",
    "STARTING IN": "à partir du",
    "STARTING FROM": "à partir de",
    "STARTING": "à partir de",
    "REACHING": "atteignant",
    "WINDS OF UP TO": "des vents jusqu'à",
    "UP TO": "jusqu'à",
    "OFF THE COAST OF": "au large de",
    "OFF": "au large de",
    "BUT": "mais",
    "HOWEVER": "cependant",
    "WAVES": "vagues",
    "MISTRAL": "le mistral",
    "TRAMONTANE": "la tramontane",
    "TRAMONTANA": "la tramontane",
    "SIROCCO": "le sirocco",
    "SCIROCCO": "le sirocco",
    "LIBECCIO": "le libeccio",
    "BORA": "la bora",
    "LEVANTER": "le levante",
    "LEVANTE": "le levante",
    "MELTEMI": "le meltem",
    "ETESIANS": "les vents étésiens",
    "SLIGHTLY": "légèrement",
    "LITTLE CHANGE": "peu de changement",
    "LITTLE CHANGED": "peu changé",
    "UNDER THE INFLUENCE OF": "sous l'influence de",
    "QUASI-STATIONARY": "quasi stationnaire",
    "SLOW-MOVING": "lent",
    "FRONTAL SYSTEM": "système frontal",
    "FRONTAL ZONE": "zone frontale",
    "SECONDARY LOW": "dépression secondaire",
    "SHALLOW": "peu creusée",
    "COMPLEX": "complexe",
    "EXTENSIVE": "vaste",
    "INITIALLY": "dans un premier temps",
    "MEANWHILE": "pendant ce temps",
    "AFTERWARDS": "ensuite",
    "THEREAFTER": "ensuite",
    "WHILE": "en",
    "EXTENDS TO": "s'étend jusqu'à",
    "EXTENDS FROM": "s'étend depuis",
    "EXTENDS": "s'étend",
    "EXTEND": "s'étendre",
    "MOVES TO": "se décale vers",
    "MOVE TO": "se décaler vers",
    "MOVES": "se déplace",
    "MOVE": "se déplacer",
    "DRIFTS": "dérive",
    "CROSSES": "traverse",
    "REACHES": "atteint",
    "REMAINS": "reste",
    "PERSISTS": "persiste",
    "DEEPENS": "se creuse",
    "FILLS": "se comble",
    "WEAKENS": "s'affaiblit",
    "INTENSIFIES": "se renforce",
    "BUILDS": "se renforce",
    "FORMS": "se forme",
    "FORMING": "se formant",
    "DISSIPATES": "se dissipe",
    "DISSIPATING": "se dissipant",
    "DEVELOPS": "se développe",
    "DEVELOPING": "se développant",
    "AFFECTS": "concerne",
    "INFLUENCES": "influence",
    "APPROACHES": "s'approche de",
    "APPROACHING": "s'approchant de",
    "TOWARDS": "vers",
    "TOWARD": "vers",
    "ACROSS": "à travers",
    "ALONG": "le long de",
    "BEHIND": "derrière",
    "AHEAD OF": "en avant de",
    "CENTRE": "centre",
    "CENTER": "centre",
    "AREA": "zone",
    "AREAS": "zones",
    "NOTES": "remarques",
    "NOTE": "remarque",
    "LESS THAN": "de moins de",
    "DAYS OLD": "jours",
    "ARE PROMULGATED BY": "sont diffusés par",
    "PROMULGATED BY": "diffusés par",
    "TRANSMITTER": "émetteur",
    "THE COMPLETE TEXTS OF ALL": "les textes complets de tous les",
    "INCLUDING THOSE WHICH ARE NO LONGER BEING BROADCAST": "y compris ceux qui ne sont plus diffusés",
    "ARE AVAILABLE FROM": "sont disponibles sur",
    "WEBSITE AT": "site internet",
    "WEBSITE": "site internet",
    # allemand (NAVTEX Pinneberg, programme 2)
    "SEEWETTERBERICHT FUER DEN NOERDLICHEN NORDATLANTIK": "bulletin météo marine pour le nord de l'Atlantique Nord",
    "SEEWETTERBERICHT FUER DEN SUEDLICHEN NORDATLANTIK": "bulletin météo marine pour le sud de l'Atlantique Nord",
    "SEEWETTERBERICHT FUER DAS WESTLICHE MITTELMEER": "bulletin météo marine pour la Méditerranée occidentale",
    "SEEWETTERBERICHT FUER DAS OESTLICHE MITTELMEER": "bulletin météo marine pour la Méditerranée orientale",
    "SEEWETTERBERICHT FUER NORD- UND OSTSEE": "bulletin météo marine pour la mer du Nord et la Baltique",
    "HERAUSGEGEBEN VOM SEEWETTERDIENST HAMBURG": "émis par le service météorologique maritime de Hambourg",
    "SEEWETTERDIENST HAMBURG": "service météorologique maritime de Hambourg",
    "WINDSTAERKE BEAUFORT, WELLENHOEHE METER": "force du vent en Beaufort, hauteur des vagues en mètres",
    "VORHERSAGEN VON": "prévisions du",
    "VORHERSAGE VON": "prévision du",
    "NORDATLANTIK": "Atlantique Nord",
    "GEBIET": "zone",
    "STARKWIND STURMWARNUNGEN FUER NORD UND OSTSEE": "avis de grand frais et de tempête pour la mer du Nord et la Baltique",
    "STARKWIND- UND STURMWARNUNGEN": "avis de grand frais et de tempête",
    "KEINE WARNUNGEN IN KRAFT": "aucun avis en vigueur",
    "NAUTISCHE WARNNACHRICHT NR.": "avertissement de navigation n°",
    "NAUTISCHE WARNNACHRICHT": "avertissement de navigation",
    "WARNUNGEN GUELTIG AB": "avis en vigueur au",
    "AUFGEHOBEN": "annulé",
    "WARNUNGEN": "avis",
    "ANMERKUNG": "remarque",
    "FUER": "pour",
}
_GERUNDS_AFTER_EN = ("s'affaiblissant", "se renforçant", "se comblant", "se creusant", "se formant", "se dissipant")
_VERBS_AFTER_PRESSURE = (
    "MOVES|MOVE|MOVING|IS|REMAINS|WITH|AND|WHILE|EXTENDS|EXTENDING|DEEPENS|DEEPENING|FILLS|FILLING|WEAKENS|"
    "WEAKENING|INTENSIFIES|INTENSIFYING|DRIFTS|CROSSES|OVER|NEAR|IN|OF|TO|FROM|ABOVE|HPA|AT|ON|BECOMES|"
    "STATIONARY|QUASI-STATIONARY|SLOWLY|QUICKLY|RAPIDLY|BUILDS|PERSISTS|FORMS|DISSIPATES|STAYS|ALSO|THEN|"
    "LATER|OFF|AREA|CENTRE|CENTER|NORTH|SOUTH|EAST|WEST|NORTHWEST|NORTHEAST|SOUTHWEST|SOUTHEAST|NORTH-WEST|"
    "NORTH-EAST|SOUTH-WEST|SOUTH-EAST|WHICH|THAT|IT|AS|BY|BETWEEN|REACHES|APPROACHES|TOWARDS|ACROSS|ALONG|HAS|"
    "WILL|SHIFTS|DRIFTING|CENTRED|CENTERED|LIES|LYING"
)
_FEM = (
    "dépression|dorsale|zone|tempête|averse|rafale|occlusion|houle|pluie|vague|baisse|hausse|"
    "goutte froide|perturbation|ligne de grains|mer"
)


def _de(word):
    return ("d'" if word[:1] in "aeiouéèêh" else "de ") + word


def _alt(keys):
    return "|".join(re.escape(k) for k in sorted(keys, key=len, reverse=True))


_RE_SEA = _alt(SEAS)
_RE_PART = _alt(_PARTS)
_RE_ADJ = _alt(_DIR_ADJ)
_RE_NOUN = _alt(_DIR_NOUN)
_RE_FORCE = _alt(_FORCE_WORDS)
_RE_DAY = _alt(_DAYS_EN)
_RE_PLACE = _alt(PLACES)
_DIR_WARDS = {"NORTH": "le nord", "SOUTH": "le sud", "EAST": "l'est", "WEST": "l'ouest", "NORTHEAST": "le nord-est", "NORTHWEST": "le nord-ouest", "SOUTHEAST": "le sud-est", "SOUTHWEST": "le sud-ouest", "NORTH-EAST": "le nord-est", "NORTH-WEST": "le nord-ouest", "SOUTH-EAST": "le sud-est", "SOUTH-WEST": "le sud-ouest"}
_RE_WARDS = _alt(_DIR_WARDS)


def _phrase_sub(text, table):
    for src in sorted(table, key=len, reverse=True):
        text = re.sub(rf"(?<![\w-]){re.escape(src)}(?![\w-])", table[src], text)
    return text


# tournures à traiter avant les noms de mers et de jours
_FIRST = {
    "WEATHER AND SEA BULLETIN": "bulletin météo et état de la mer",
    "VALID UNTIL": "valable jusqu'à",
    "VALID FROM": "valable à partir de",
}


def _with_article(name):
    """« Baléares » -> « les Baléares », « golfe du Lion » -> « le golfe du Lion », « Adriatique » -> « l'Adriatique »."""
    if name in ("Chypre", "Malte", "Madère"):
        return name
    if name[:1] in "AEIOUÉ":
        return "l'" + name
    if name.startswith(("mers", "Baléares", "bouches")):
        return "les " + name
    if name.startswith(("golfe", "détroit", "large")):
        return "le " + name
    return "la " + name


def translate_prose(sentence):
    """Traduit une phrase (ou un paragraphe) en MAJUSCULES. Les mots inconnus restent en majuscules."""
    t = " " + re.sub(r"\s+", " ", (sentence or "").upper().replace("?BR?", " ")).strip() + " "
    t = _phrase_sub(t, _FIRST)
    # 2.11.0 — en-tête souvent abîmé en RTTY (« WIND FORCE: OEAUFORT, WAVE HEIGHT: METRE »)
    t = re.sub(r"WIND FORCE:? ?\S{0,2}EAU\S*,? WAVE HEIGHT:? ?\S{0,2}ET\S*", "force du vent en Beaufort, hauteur des vagues en mètres", t)
    # « LOW 1014 UKRAINE » = dépression 1014 SUR l'Ukraine (le DWD omet la préposition)
    t = re.sub(rf"(?<![\w-])(LOW|HIGH) (\d{{3,4}}) (?!(?:{_VERBS_AFTER_PRESSURE})\b)(?=[A-Z])", r"\1 \2 OVER ", t)
    t = re.sub(r"(?<![\w-])LOW (\d{3,4})\b", r"dépression \1", t)
    t = re.sub(r"(?<![\w-])HIGH (\d{3,4})\b", r"anticyclone \1", t)
    # rafales et forces
    t = re.sub(r"GUSTS OF UP TO (\d{1,2}) ?(?:BFT|BEAUFORT)", r"des rafales jusqu'à force \1 Beaufort", t)
    t = re.sub(r"GUSTS UP TO (\d{1,2}) ?(?:BFT|BEAUFORT)", r"des rafales jusqu'à force \1 Beaufort", t)
    t = re.sub(r"UP TO (\d{1,2}) ?(?:BFT|BEAUFORT)", r"jusqu'à force \1 Beaufort", t)
    t = re.sub(r"(\d{1,2})(?: ?(?:TO|-) ?(\d{1,2}))? ?(?:BFT|BEAUFORT)\b", lambda m: "force " + m.group(1) + (f" à {m.group(2)}" if m.group(2) else "") + " Beaufort", t)
    # « NEAR-GALE-FORCE WESTERLY TO NORTH-WESTERLY WINDS » -> des vents d'ouest à nord-ouest de force 7
    t = re.sub(
        rf"({_RE_FORCE}) ({_RE_ADJ}) TO ({_RE_ADJ}) WINDS?",
        lambda m: f"des vents de secteur {_DIR_ADJ[m.group(2)]} à {_DIR_ADJ[m.group(3)]} {_FORCE_WORDS[m.group(1)]}",
        t,
    )
    t = re.sub(rf"({_RE_FORCE}) ({_RE_ADJ}) WINDS?", lambda m: f"des vents de secteur {_DIR_ADJ[m.group(2)]} {_FORCE_WORDS[m.group(1)]}", t)
    t = re.sub(rf"(?<![\w-])BY ({_RE_DAY})\b", lambda m: "d'ici " + _DAYS_EN[m.group(1)], t)
    t = re.sub(r"(\d) M\b", r"\1 m", t)
    t = re.sub(rf"({_RE_FORCE}) WINDS", lambda m: "des vents " + _FORCE_WORDS[m.group(1)], t)
    t = re.sub(rf"({_RE_FORCE}) GUSTS", lambda m: "des rafales " + _FORCE_WORDS[m.group(1)], t)
    t = re.sub(rf"({_RE_FORCE})", lambda m: _FORCE_WORDS[m.group(1)], t)
    # directions
    t = re.sub(
        rf"FROM ({_RE_ADJ}) TO ({_RE_ADJ}) DIRECTIONS?",
        lambda m: f"de secteur {_DIR_ADJ[m.group(1)]} à {_DIR_ADJ[m.group(2)]}",
        t,
    )
    t = re.sub(rf"FROM ({_RE_ADJ}) DIRECTIONS?", lambda m: f"de secteur {_DIR_ADJ[m.group(1)]}", t)
    t = re.sub(rf"({_RE_ADJ}) TO ({_RE_ADJ}) WINDS?", lambda m: f"vent de secteur {_DIR_ADJ[m.group(1)]} à {_DIR_ADJ[m.group(2)]}", t)
    t = re.sub(rf"({_RE_ADJ}) WINDS?", lambda m: "vent " + _de(_DIR_ADJ[m.group(1)]), t)
    t = re.sub(rf"\b({_RE_ADJ})\b", lambda m: "de secteur " + _DIR_ADJ[m.group(1)], t)
    # mers : « THE SOUTHERN AEGEAN », « IN THE LIGURIAN SEA », « THROUGHOUT THE WESTERN MEDITERRANEAN »
    t = re.sub(
        rf"(?:IN |OVER )?(?:THE )?({_RE_PART}) (?:PART OF (?:THE )?)?({_RE_SEA})(?![A-Z])",
        lambda m: (
            ("sur le " if m.group(0).lstrip().startswith(("IN ", "OVER ")) else "le ")
            + _PARTS[m.group(1)]
            + " "
            + SEAS[m.group(2)][1]
        )
        if (m.group(1) + " " + m.group(2)) not in SEAS
        else m.group(0),
        t,
    )
    t = re.sub(rf"THROUGHOUT (?:THE )?({_RE_SEA})(?![A-Z])", lambda m: "sur l'ensemble " + SEAS[m.group(1)][1], t)
    t = re.sub(rf"(?:IN|OVER) (?:THE )?({_RE_SEA})(?![A-Z])", lambda m: SEAS[m.group(1)][2], t)
    t = re.sub(rf"(?:OF|FROM) (?:THE )?({_RE_SEA})(?![A-Z])", lambda m: SEAS[m.group(1)][1], t)
    t = re.sub(rf"FOR (?:THE )?({_RE_SEA})(?![A-Z])", lambda m: "pour " + _with_article(SEAS[m.group(1)][0]), t)
    t = re.sub(rf"(?:THE )?({_RE_SEA})(?![A-Z])", lambda m: ("l'" if SEAS[m.group(1)][0][0] in "AEIOUÉ" else ("les " if SEAS[m.group(1)][0].startswith(("mers", "Baléares", "bouches")) else ("le " if SEAS[m.group(1)][0].startswith(("golfe", "détroit")) else "la "))) + SEAS[m.group(1)][0] if SEAS[m.group(1)][0] not in ("Chypre",) else SEAS[m.group(1)][0], t)
    # jours
    t = re.sub(rf"(?:ON|FOR) ({_RE_DAY})\b", lambda m: _DAYS_EN[m.group(1)], t)
    t = re.sub(rf"(?:UNTIL|jusqu'à) ({_RE_DAY})\b", lambda m: "jusqu'à " + _DAYS_EN[m.group(1)], t)
    t = re.sub(rf"\b({_RE_DAY})\b", lambda m: _DAYS_EN[m.group(1)], t)
    t = re.sub(r"\b(MO|TU|WE|TH|FR|SA|SU)/(\d{1,2})/(\d{1,2})", lambda m: f"{DAYS.get(m.group(1), m.group(1))} {m.group(2)}/{m.group(3)}", t)
    # 2.11.0 — situation générale : directions de déplacement, lieux, verbes
    t = re.sub(rf"(?:TO THE |TOWARDS? THE )({_RE_NOUN})(?![\w-])", lambda m: "vers " + _DIR_WARDS.get(m.group(1), m.group(1)), t)
    t = re.sub(rf"(?<![\w-])({_RE_WARDS})WARDS? TO\b", lambda m: "vers " + _DIR_WARDS[m.group(1)] + " jusqu'à", t)
    t = re.sub(rf"(?<![\w-])({_RE_WARDS})WARDS?\b", lambda m: "vers " + _DIR_WARDS[m.group(1)], t)
    t = re.sub(rf"(?<![\w-])({_RE_NOUN}) OF (?:THE )?", lambda m: "au " + _DIR_NOUN[m.group(1)] + " de ", t)
    t = re.sub(rf"(?:OVER|IN) (?:THE )?({_RE_PLACE})(?![\w-])", lambda m: "sur " + PLACES[m.group(1)], t)
    t = re.sub(rf"(?<![\w-])(?:THE )?({_RE_PLACE})(?![\w-])", lambda m: PLACES[m.group(1)], t)
    t = _phrase_sub(t, SYNOPTIC)
    # expressions figées, puis directions restantes, puis petits mots
    t = _phrase_sub(t, PHRASES)
    t = re.sub(rf"(?<![\w-])({_RE_NOUN})(?![\w-])", lambda m: _DIR_NOUN[m.group(1)], t)
    t = _phrase_sub(t, _SMALL)
    # finitions
    t = re.sub(r"\bde (?=[aeiouéèêh])", "d'", t)
    t = re.sub(r"\b(le|vers) (est|ouest)\b", r"\1 l'\2", t)
    t = re.sub(r"\ble l'", "l'", t)
    t = re.sub(r"\bvers (nord|sud)", r"vers le \1", t)
    t = re.sub(r"\bde le\b", "du", t)
    t = re.sub(r"\bde les\b", "des", t)
    t = re.sub(r"\bà le\b", "au", t)
    t = re.sub(r"\bà les\b", "aux", t)
    t = re.sub(r"\bdans en\b", "en", t)
    t = re.sub(r"\bet des\b", "et des", t)
    t = re.sub(r"\bavec des fortes\b", "avec de fortes", t)
    t = re.sub(r"\bjusqu'à le\b", "jusqu'au", t)
    t = re.sub(r"\bjusqu'à les\b", "jusqu'aux", t)
    t = re.sub(r"\bde l'([a-zéèê])", r"de l'\1", t)
    t = re.sub(r"\bde (?=[aeiouéèêh])", "d'", t)
    # accords : « un dépression » -> « une dépression », « un vaste dépression » -> « une vaste dépression »
    t = re.sub(rf"\b([Uu])n ((?:vaste |petite |forte |large |nouvelle |seconde )?(?:{_FEM})\b)", r"\1ne \2", t)
    t = re.sub(r"\btalweg d'une dépression", "talweg issu d'une dépression", t)
    t = re.sub(r"\b([Uu])n (le|la) (mistral|sirocco|libeccio|levante|meltem|tramontane|bora)\b",
               lambda m: m.group(1) + ("n " if m.group(2) == "le" else "ne ") + m.group(3), t)
    t = re.sub(r"\b(?:the|THE) (le|la) (mistral|tramontane)", r"\1 \2", t)
    t = re.sub(r"\bsur une partie (la|le|les|l')", r"sur une partie de \1", t)
    t = re.sub(r"\bsur une partie de le\b", "sur une partie du", t)
    t = re.sub(r"\bà partir de dans le\b", "à partir du", t)
    t = re.sub(r"\bà partir de dans (la|l'|les)", r"à partir de \1", t)
    t = re.sub(r"\b(atteignant|avec) vents de jusqu'à", r"\1 des vents jusqu'à", t)
    t = re.sub(r"\bvents de jusqu'à", "vents jusqu'à", t)
    t = re.sub(r"\bet rafales de force", "et des rafales de force", t)
    t = re.sub(r"\ben (?!(?:" + "|".join(re.escape(g) for g in _GERUNDS_AFTER_EN) + r"))(?=[a-zé]+ant\b)", "en ", t)
    t = re.sub(r"\s+([,.;])", r"\1", t)
    t = re.sub(r"\s{2,}", " ", t).strip()
    # majuscule en début de phrase
    t = re.sub(r"(^|[.!?]\s+)([a-zàâçéèêëîïôûùüÿœ])", lambda m: m.group(1) + m.group(2).upper(), t)
    return t


def untranslated_words(french):
    """Mots restés en majuscules (non traduits), hors sigles et abréviations admises."""
    keep = {"UTC", "DWD", "AVIS", "BSH", "WWW", "PDF", "NAVTEX", "DE", "COUP", "VENT", "GRAND", "FRAIS", "TEMPÊTE", "ZCZC", "NNNN", "EDZW", "SST"}
    return sorted({w for w in re.findall(r"\b[A-ZÄÖÜ]{3,}\b", french) if w not in keep})


# ------------------------------------------------------------------------------ bulletin complet
_WMO = re.compile(r"^\s*[A-Z]{4}\d{2}\s+[A-Z]{4}\s+\d{6}")
_STAMP = re.compile(r"^\s*\d{1,2}\.\d{1,2}\.\d{2,4},?\s+\d{1,2}(?::\d{2})?(?:\s*UTC)?:?\s*$")


def _table_line(m):
    day, date, hour, d, bft, gust, sea, wx = m.groups()
    # 2.11.0 — heure illisible (« SA 21. 56Z ») : signalée, jamais devinée
    hour = hour if int(hour) <= 23 else "??"
    out = f"  {DAYS.get(day, day):<5}{int(date):>2}  {hour} h UTC : {_dir_fr(d):<6} force {bft:<4}"
    out += f" rafales {gust:<5}" if gust else " " * 14
    out += f" mer {sea.replace('.', ',')} m"
    phen = [WX[w] for w in wx.split() if w in WX]
    if phen:
        out += "  " + ", ".join(phen)
    return out.rstrip()


def _point_header(line, m):
    name, lat, ns, lon, ew, wt = m.groups()
    name = name.strip()
    from wefax_station.weather.plain_language import sea_name

    fr = sea_name(float(lat) * (1 if ns == "N" else -1), float(lon) * (1 if ew == "E" else -1))
    label = f"{name} ({fr})" if fr and fr != "zone maritime" else name
    return f"{label} — {lat}°{ns} {lon}°{ew}" + (f" — eau {wt} °C" if wt else "")


def _garbled(up):
    """Ligne de tableau ou d'en-tête abîmée (« SU )2. 12Z: 1,3- 4 15 M // », « ENGQ AANNEL »)."""
    if _POINT.match(up) or _STAMP.match(up) or _WMO.match(up) or re.search(r"UTC|FORECAST|VORHERSAGE|WARNING|WARNNACHRICHT", up):
        return False
    if "//" in up or re.search(r"\b\d{1,2}[A-Z]{0,2}[:.]\s*[A-Z]{0,3}[-\d]", up) and re.search(r"\bM\b|\d\.\d", up):
        return True
    alnum = sum(c.isalnum() for c in up)
    odd = sum(c in "()#&'+?/,;!*" for c in up)
    digits = sum(c.isdigit() for c in up)
    return len(up) >= 6 and (odd >= 3 or (alnum and digits / max(1, alnum) > 0.45 and not _STAMP.match(up) and not _WMO.match(up)))


def translate_bulletin(text):
    """Bulletin complet en français : prose traduite par paragraphes, tableaux réécrits ligne à ligne."""
    lines = (text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    out, para = [], []

    def flush():
        if para:
            out.append(translate_prose(" ".join(para)))
            para.clear()

    for raw in lines:
        ln = raw.strip()
        up = ln.upper()
        if not ln:
            continue
        m_step = _LINE.match(up)
        m_point = _POINT.match(up)
        if m_step and m_step.group(1) in DAYS:
            flush()
            out.append(_table_line(m_step))
        elif _garbled(up):
            # 2.11.0 — ligne de tableau abîmée par la réception : signalée telle quelle, jamais
            # mêlée à la prose (elle rendait les paragraphes traduits illisibles)
            flush()
            out.append(f"  [illisible] {ln}")
        elif m_point:
            flush()
            out.append("")
            out.append(_point_header(up, m_point))
        elif up.startswith(("ZCZC", "NNNN")) or up == "=" or _WMO.match(up) or _STAMP.match(up):
            flush()
            if up.startswith("ZCZC"):
                out.append("")
            out.append(ln if up != "=" else "")
        elif up in ("NIL", "IL", "NI", "NL"):
            flush()
            out.append("néant")
        else:
            para.append(ln)
            if up.endswith((":", ".")):
                flush()
    flush()
    # « néant » répétés (rubriques vides d'un même bulletin) regroupés
    cleaned = []
    for ln in out:
        if ln == "néant" and cleaned and cleaned[-1].startswith("néant"):
            continue
        if ln == "" and cleaned and cleaned[-1] == "":
            continue
        cleaned.append(ln)
    return "\n".join(cleaned).strip()


def synopsis_paragraphs(text, limit=2):
    """Paragraphes « situation générale » des bulletins reçus, traduits, l'émission la plus récente d'abord.

    Retourne une liste de textes précédés de leur date d'émission quand elle est lisible.
    """
    src = (text or "").replace("\r\n", "\n").replace("\r", "\n")
    found = []
    for m in re.finditer(r"GENERAL SYNOP(?:TIC SITUATION|SIS)[^\n]*\n", src.upper()):
        body = []
        for ln in src[m.end() :].split("\n"):
            s = ln.strip()
            u = s.upper()
            if not s:
                continue
            if (
                u in ("NIL", "=")
                or u.startswith(("NNNN", "ZCZC", "DWD FORECAST"))
                or _POINT.match(u)
                or _STAMP.match(u)
            ):
                break
            body.append(s)
            if len(body) > 14:
                break
        if not body:
            continue
        fr = translate_prose(" ".join(body))
        head = src[max(0, m.start() - 260) : m.start()].upper()
        stamp = re.findall(r"(\d{1,2})\.(\d{1,2})\.(\d{2,4}),?\s+(\d{1,2})\s*UTC", head)
        key, label = (0, 0, 0, 0), ""
        if stamp:
            d, mo, y, h = (int(v) for v in stamp[-1])
            key, label = (y % 100, mo, d, h), f"Émis le {d:02d}/{mo:02d} à {h:02d} h UTC — "
        if fr and all(fr != f[2] for f in found):
            found.append((key, label, fr))
    found.sort(key=lambda f: f[0], reverse=True)
    return [label + fr for _k, label, fr in found[:limit]]
