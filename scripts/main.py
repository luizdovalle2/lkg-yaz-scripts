import pandas as pd

import extract
import graphutils as guts
from config import *

print("[Info] Loading Yaznevich database.")

xlbook = pd.read_excel(PATH_DATA_YAZN, sheet_name=None, dtype=str)

print("[Info] Processing preextracted data.")

lang_list, lang_map, languages = extract.langs(PATH_EXTR_LANG)
types = extract.types(PATH_EXTR_TYPE)

print("[Info] Extracting publisher and place info.")

publishers = xlbook[PUBLISHERS_SHEETNAME]
publishers = extract.prepare_publishers(publishers, PUBLISHERS_COLMAP)
cities_to_geonames, geonameids = extract.places_mapping(PATH_EXTR_CITY, PATH_EXTR_CITY_NEW, publishers)
places = pd.read_excel(PATH_EXTR_CITY, sheet_name="data", dtype=str)
places = places.set_index("uri", drop=False)
publishers["uri_place"] = publishers["city"].map(cities_to_geonames["uri"])

print("[Info] Extracting person info.")

plp = xlbook[PLP_SHEETNAME].iloc[PLP_ROWS]
plp = extract.prepare_plp(plp, PLP_COLMAP)
plp_names = extract.plp_names(plp, lang_map)
prs = xlbook[PRS_SHEETNAME].iloc[PRS_ROWS]
prs = extract.prepare(prs, PRS_COLMAP)
prs_names = extract.prs_names(prs)
people = extract.people_merge(plp_names, prs_names, PREFIX_PERSON)
lem_names = people.at["0", "search"].split(" | ")

print("[Info] Extracting Non Fiction info.")

nf = {
    sheetname: extract.nf_cleanup(xlbook[sheetname].iloc[: NF_ENDROW.get(sheetname, len(xlbook[sheetname]))], NF_COLS, NF_STARTCOL[sheetname])
    for sheetname in NF_SHEETLIST
}
nf_langs = {sheetname: xlbook[sheetname].columns[0].strip(":") for sheetname in NF_SHEETLIST}
nf_main = pd.DataFrame({}, [], NF_COLS, dtype=str)
nf_newcols = [
    "yid_lkg",
    "part_of",
    "has_part",
    "refs_normal",
    "expanded_title",
    "by_lem",
    "pub_name",
    "pub_year",
    "pub_number",
    "city",
]
for sheetname, nonfic in nf.items():
    nf[sheetname] = extract.nf_filter_entities(nonfic, PREFIX_NONFICTION, nf_langs[sheetname])
    nf_main = extract.nf_process_sheet(
        nf[sheetname],
        PREFIX_NONFICTION,
        PREFIX_OTHER,
        nf_langs[sheetname],
        lang_list,
        lem_names,
        NF_ISSUE_PATTERNS,
        NF_COLS,
        nf_newcols,
        nf_main,
    )

print("[Info] Extracting additional info from Non Fiction.")

publishers = extract.nf_publishers(publishers, nf_main, cities_to_geonames, PREFIX_PUBLISHER)
issues = extract.nf_issues(nf_main, PREFIX_JOURNAL)
authorships = extract.authorships(plp, nf_main, lang_list, PREFIX_PERSON, PREFIX_NONFICTION, PREFIX_OTHER)

print("[Info] Extracting scientific monograph index info.")

monographs_sheet = xlbook[MON_SHEETNAME]
monographs_sheet = extract.prepare_monographs(monographs_sheet, MON_COLS)
monographs = extract.monographs(monographs_sheet, PREFIX_MONOGRAPH, PREFIX_NONFICTION, lang_list, PREFIX_OTHER, MON_IGNORE)

lang_detector = guts.build_detector(AUTODETECT_LANG_LIST.split()) if AUTODETECT_LANG else None

print("[Info] Building base graph...")

guts.build_graph(
    PATH_ONTO_LKG,
    PATH_GRAPH_YAZN,
    languages,
    lang_detector,
    types,
    places,
    people,
    publishers,
    issues,
    nf,
    PREFIX_NONFICTION,
    authorships,
    monographs,
)

print(f"[Info] Success: base graph saved as {PATH_GRAPH_YAZN}.")

import enrich
