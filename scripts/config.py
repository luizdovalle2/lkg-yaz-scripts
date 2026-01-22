import os
import re
from collections import defaultdict
from enum import Enum
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

# Only used in new code.
SHOW_WARNINGS = True
class WARNINGS(Enum):
    NO_LABEL_FOR_TYPE = 1
WARN_PAST = {i: None for i in WARNINGS}

# Set to True to fetch geoname details from API and save to file.
# Subsequent runs with this set to False will use cached results. To
# fetch data from geonames you have to put your geonames username into
# .env file as so: GEONAMES_KEY=YOUR_USERNAME_HERE
FETCH_GEONAME_INFO=False

# Optionally use the lingua-py library to guess language for
# appellations that don't have it. Note this sometimes fails so there
# will be some cases left without a language assigned.
AUTODETECT_LANG=False
# ISO 639-1 codes for languages to autodetect. Make sure lingua-py
# supports any other that you want to add.
AUTODETECT_LANG_LIST = "BE DE EN ES EL FR IT JA PL PT RU TR UK ZH"

# Paths and filenames
DIR_DATA = Path("data")
DIR_ONTO = DIR_DATA / "onto"
DIR_RECO = DIR_DATA / "reconciled"
DIR_OUT = Path("output")
PATH_DATA_YAZN = DIR_DATA / "Lem Non Fiction BPK-25s_LKG_v3.4.xlsx"
PATH_EXTR_LANG = DIR_DATA / "langs.xlsx"
PATH_EXTR_TYPE = DIR_DATA / "types.xlsx"
PATH_EXTR_CITY = DIR_DATA / "cities.xlsx"
PATH_EXTR_CITY_NEW = DIR_DATA / "cities_new.xlsx"
PATH_EXTR_GEOC = DIR_DATA / "geocache.json"
PATH_ONTO_LKG = DIR_ONTO / "LKG_ontology_0_1.rdf"
PATH_ONTO_CRM = DIR_ONTO / "CIDOC_CRM_v7.1.3.rdf"
PATH_ONTO_LRM = DIR_ONTO / "LRMoo_v1.0.rdf"
PATH_GRAPH_YAZN = DIR_OUT / "lkg_yaz2.ttl"

# Output LKG YID prefixes
PREFIX_PERSON = "P"
PREFIX_NONFICTION = "NF"
PREFIX_OTHER = "OTH"
PREFIX_JOURNAL = "J"
PREFIX_PUBLISHER = "C"
PREFIX_PLACE = "G"
PREFIX_MONOGRAPH = "MON"

# Maps of excel column names for predictable indexing. Update keys if
# column headers change in main excel.
PUBLISHERS_SHEETNAME = "WWW"
PUBLISHERS_COLMAP = {
    "Razem:  1247  książek w  437  wydawnictwach": "publisher",
    "miasto": "city"
}
PLP_SHEETNAME = "PLp"
PLP_ROWS = slice(2, None)
PLP_COLMAP = {
    " ↗": "id",
    "Persona": "names",
    " (": "sep",
    "RU": "langs",
    "→": "arrow",
    " / ": "ogname"
}
PRS_SHEETNAME = "Prs"
PRS_ROWS = slice(None, 5432)
PRS_COLMAP = {
    " ↗": "id",
    "Персона": "cyrillic",
    "Personalie Stanisława Lema": "names",
    "x": "continue",
    "r": "sep"
}
# All workable Non Fiction sheet names. Don't include "BE_all", "JA (2)"
# etc. because their IDs overlap with their language's base sheet.
NF_SHEETLIST = [
    "PL", "RU", "DE", "EN", "ES", "UK", "FR", "LT", "BE", "BG", "CS", "PT", "IT", "ZH", "ET", "EL", "KA", "KY", "JA",
    "LV", "MK", "MN", "RO", "SR", "SK", "SL", "HR", "SV", "TR", "HU", "FI", "NL", "HE"
]
# For Non Fiction sheets, rely on universal column order instead of
# maps, because these columns have same meaning, quantity and order but
# different headings between language sheets. This way we don't need
# multiple maps for the same kind of thing.
NF_COLS = [
    "is_main", "yid_main", "yid_sub", ".", "author", ",", "title", "sep", "publisher", ",,", "pub_info", "more",
    "refs", ";", "tls", "..", "type"
]
# Account for different starting column of above column sequence.
NF_STARTCOL = defaultdict(lambda: 2, {"RU": 3})
# Mark data end row for sheets that need it.
NF_ENDROW = {"SK": 21, "PL": 6079, "RU": 3326, "LV": 41, "ZH": 32}

# Construct pattern to cut out year and page numbers from publishing
# info. Result should be issue number, however exotic its form. There
# will be some false positives but strict patterns often skip valuable
# information.
NF_PAGEMARKS = ["s", "c", "S", "p", "pp", "页", "lk", "Ik", "σ", "გ", "б", "l", "г", "old"]
REGXP_PAGE_AIO = r"|".join([
    r"(?:, |^)"
    + re.escape(mark)
    + r"\.(?: )?(?:\d|[A-Za-z])|(?:, |^)?(?:\d|[A-Za-z_])+ "
    + re.escape(mark)
    + r"\."
    for mark in NF_PAGEMARKS
])
NF_ISSUE_PATTERNS_DEFAULT = (r"^(?P<year>\d{4})(?:, )?", REGXP_PAGE_AIO)
NF_ISSUE_PATTERNS = defaultdict(lambda: NF_ISSUE_PATTERNS_DEFAULT)

# Scientific monographs index details
MON_SHEETNAME = "IMN"
MON_COLS = [
    "is_main",
    "yid_main",
    "d1",
    "title",
    "c1",
    "year",
    "d2",
    "equals"
]
# For each monograph in sheet a list of positions to disqualify as a formal edition.
# Examples:
# - ["EN"] to ignore all English positions;
# - given a monograph has the following listed as all editions:
#     "PL:355 [1975]",
#     "DE:215 [1981], 284+304 [1986+1987], 305 [1987]",
#     "CS:33 [1999], CS:54 [2005]",
#   the blacklist ["CS", "DE:2"] will disqualify both Czech texts and the second
#   German text (in blacklist in DE:2, the number represents order (counting
#   from 1), not YID). In other words, the only formal editions will be PL:355,
#   DE:215, DE:305.
# TODO: Need expert revision
MON_IGNORE = {
    "2": ["BG"],
    "4": ["BG", "EN"],
    "5": ["EN", "IT", "JA"],
    "6": ["DE", "JA"],
    "7": ["RU"],
    "8": ["CS", "DE", "SR", "UK"]
}

GEONAMES_KEY = os.getenv("GEONAMES_KEY")


#
# --------------------------
# WIKI AND BVI CONFIGURATION
# --------------------------
#

DIR_BVI = DIR_DATA / "lbibl"
DIR_WIKI = DIR_DATA / "lemwiki"

REGEXP_BVI_FILE = r"L_B_(?P<fileid>[A-Za-z]*)\.TXT"
PATH_DATA_BVI_ATOMS = DIR_BVI / "L_NAZA.TXT"
PATH_DATA_WIKI_EDITIONS = DIR_WIKI / "editions.xml"
PATH_EXTR_WIKI_EDITIONS_TRANSFORM = DIR_WIKI / "editions.xsl"
PATH_EXTR_WIKI_ENTITIES = DIR_DATA / "wiki-entities.xlsx"
PATH_EXTR_FICTION = DIR_DATA / "F1_fiction_all.xlsx"

# F1 fiction prefix
PREFIX_FICTION = "FIC"

# Prefixes signifying source dataset
PREFIX_INDEX = "I"
PREFIX_YAZN = "Y"
PREFIX_WIKI = "W"
PREFIX_BVI = "B"

WIKI_MAP_PROPS = {
    "dimesions": "dimensions"
}

COLMAP_FICTION = {
    "Lp": "id",
    "Nazwa kolekcji lub tekstu poza kolekcją": "name_main",
    "Elementy składowe": "name_comp1",
    "Składowe elementów składowych": "name_comp2",
    "Uwagi": "notes",
    "Ewentualne URI NF": "sameas_lkg",
    "Pierwsze wydanie (link)": "wiki_page_url",
    "Tytuł jaki jest na stronie": "wiki_page_title",
    "Kolejne wydania": "subsequent_editions",
    "Wydane jako część wydania": "wiki_page_url_partial",
    "Autorzy": "authors",
    "Język (fallback)": "lang",
}
