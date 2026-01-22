import re
from pathlib import Path

import geocoder
import pandas as pd

import utils
from config import *


def langs(path: Path | str) -> tuple[list[str], dict[str, str], pd.DataFrame]:
    langxl = pd.read_excel(path, sheet_name=None, dtype=str)
    langlist = langxl["langs"]["iso639-1"].dropna().str.upper().str.strip().tolist()
    langnames = langxl["langs"].fillna("").map(lambda x: x.strip())
    langnames.set_index("uri", drop=False, inplace=True)
    langmap = langxl["errors"].apply(lambda x: x.astype(str).str.upper().str.strip())
    langmap = pd.Series(langmap["shouldbe"].values, index=langmap["is"]).to_dict()
    missing = set(langmap.values()) - set(langlist)
    if missing:
        raise KeyError(f'Language codes {", ".join(missing)} from "errors" sheet not in "langs" sheet')
    langlist.append("NOLANG")
    for l in langlist:
        langmap[l] = l
    return langlist, langmap, langnames


def types(types_path: Path | str):
    typesdf = pd.read_excel(types_path, dtype=str)
    typesdf.set_index("type", inplace=True)
    return typesdf


def places_mapping(
    cities_path: Path | str, new_cities_path: Path | str, publishers: pd.DataFrame
) -> tuple[pd.DataFrame, list[str]]:
    """Import mapping of city names as they appear in source excel, to
    unambiguous geoname IDs.

    For names present in source excel that don't already appear in
    `cities.xlsx`, this function will generate spreadsheet
    `cities_new.xlsx`, containing names and associated publisher for
    context. Go through the `city` column and for every cell containing
    city names, copy that whole cell into `cities.xlsx` and find
    geonames for each city name in that string. Write down geonames in
    the same order, into `geonameid` column.

    Args:
        cities_path (Path | str): Path to `cities.xlsx` containing
            city and `geonameid` columns mapping places, as they appear
            in main excel, to geoname IDs.
        newcities_path (Path | str): Path to `cities_new.xlsx`, file
            generated every time the script detects place names in main
            excel missing from `cities.xlsx`.
        publishers (DataFrame): DataFrame about publishers, containing
            `city` and `publisher` columns.

    Returns:
        out (tuple[DataFrame, list[str]]):
            A tuple `(cities_to_geonames, geonameids)`, where
                - `cities_to_geonames` is a DataFrame created from
                    `cities.xlsx` where city names from main excel are
                    the index and respective geoname IDs are in
                    `geonameid` column,
                - `geonameids` is a list of all singular, unique
                    geonameids appearing in `cities.xlsx`.
    """
    cities_path = Path(cities_path)
    new_cities_path = Path(new_cities_path)
    city_keys = set(publishers["city"].unique())
    city_excel = publishers[["city", "publisher"]].groupby("city").first()
    cities_to_geonames = pd.DataFrame(data=[], columns=["geonameid"], index=pd.Index([], name="city", dtype=str))
    if cities_path.exists():
        cities_to_geonames = pd.read_excel(cities_path, dtype=str, index_col=0)
        city_keys = list(city_keys - set(cities_to_geonames.index.values))
    city_new = city_excel[~city_excel.index.isin(cities_to_geonames.index.values)]
    city_all = pd.concat([cities_to_geonames, city_new])
    if len(city_all) != len(cities_to_geonames):
        city_all.to_excel(new_cities_path)
        print(
            f"[Info] Extracted places with no mapping. Saved to {new_cities_path}. If these names look like artifacts, they likely are - ignore them. If there are city names there, then in {PATH_EXTR_CITY}, in 'yaz-place-list' add mapping to a place from 'data' sheet. If there is no such place in 'data', add it and fill in the columns, then add mapping.",
        )
    geonameids = cities_to_geonames["geonameid"].str.split().explode().drop_duplicates().tolist()
    return cities_to_geonames, geonameids


def places(
    cities_to_geonames: pd.DataFrame,
    geonameids: list[str],
    prefix_place: str,
    geocache_path: Path | str,
    fetch_from_geonames_api: bool = False,
    geonames_api_key: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Prepare data about places for inserting into graph."""
    if fetch_from_geonames_api:
        geoinfo = {
            geonameid: geocoder.geonames(geonameid, key=geonames_api_key, method="details") for geonameid in geonameids
        }
        cityinfo = pd.DataFrame.from_dict(geoinfo, orient="index", columns=["geo"])
        cityinfo["json"] = cityinfo["geo"].map(lambda x: x.json)
        cityinfo["json"].to_json(geocache_path, force_ascii=False, indent=4)

    geocache = pd.read_json(geocache_path, orient="index")
    geocache.index = geocache.index.astype(str)
    geocache.index.name = "geonameid"

    places = pd.DataFrame(data=geocache.index, index=geocache.index, columns=["geonameid"])
    places[["city", "country", "city_pl", "wdid"]] = places.apply(
        _places_row_add_names, axis=1, result_type="expand", geocache=geocache
    )
    places["yid_lkg"] = pd.Series([prefix_place + str(x) for x in range(len(places))], dtype=str).values

    cities_to_geonames["yid_lkg"] = cities_to_geonames["geonameid"].map(
        lambda x: " ".join([places.at[geonameid, "yid_lkg"] for geonameid in x.split()])
    )
    return places, cities_to_geonames, geocache


def _places_row_add_names(row: pd.Series, geocache: pd.DataFrame):
    """Given row where index is geoname, and the geocache DataFrame,
    return list containing city name, country name, and also city name in Polish
    and wikidata ID, if found in geocache (else English name and None as
    wikidata ID).
    """
    result = [None] * 4
    if row.name not in geocache.index:
        return result
    result[0] = geocache["address"].get(row.name)
    result[1] = geocache["country"].get(row.name)
    raw = geocache["raw"].get(row.name)
    altnames = raw.get("alternateNames")
    if not altnames:
        return result
    foundPL = False
    foundWD = False
    for name in altnames:
        if not foundPL and name.get("lang") == "pl":
            result[2] = name.get("name")
            if name.get("isPreferredName") == True:
                foundPL = True
        if not foundWD and name.get("lang") == "wkdt":
            result[3] = name.get("name")
            foundWD = True
    if not result[2]:
        result[2] = result[0]
    return result


def prepare(sheet: pd.DataFrame, colmap: dict[str, str] | None) -> pd.DataFrame:
    sheet.index = sheet.index.astype(str)
    sheet.columns = sheet.columns.astype(str)
    if colmap:
        sheet = sheet.rename(columns=colmap)
    sheet = sheet.map(lambda x: re.sub(r"\s+", " ", x) if isinstance(x, str) else x)
    return sheet


def prepare_publishers(publishers: pd.DataFrame, colmap: dict[str, str] | None) -> pd.DataFrame:
    publishers = prepare(publishers, colmap)
    publishers = publishers.dropna(subset=["city"])[["publisher", "city"]]
    return publishers


def prepare_plp(plp: pd.DataFrame, colmap: dict[str, str] | None) -> pd.DataFrame:
    plp = prepare(plp, colmap)
    plp["sep"] = plp["sep"].fillna("-")
    return plp


def prepare_monographs(sheet: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    sheet = prepare(sheet, None)
    monocols = sheet.columns.tolist()
    monocols[:len(cols)] = cols
    sheet.columns = monocols
    sheet = sheet.fillna("").astype(str)
    # For now remove non-ID information in refs, such as
    # "2336 [wyd.2, 2010]", "PL:2039(1198 [1996]+1411 [1999])"
    # Also remove separator columns
    cdrop = []
    for c in sheet.columns:
        sheet[c] = sheet[c].str.strip()
        if c.isdigit():
            sheet[c] = sheet[c].str.split(r"\(| \[", regex=True).map(lambda x: x[0])
        elif c not in cols:
            cdrop.append(c)
    sheet = sheet.drop(columns=cdrop)
    return sheet


def _plp_row_make_allnames(row, langmap):
    result = {}
    langs = row["mainname_langs"] if isinstance(row["mainname_langs"], list) else ["NOLANG"]
    afterequals = row["names_after_equals"]
    if not isinstance(afterequals, list):
        afterequals = []
    try:
        for lang in langs:
            lang = utils.verify_lang(lang, langmap)
            result[lang] = [[name] for name in row["mainname_altlist"]]
    except KeyError as e:
        e.add_note(str(row))
        raise e
    return [*[name + " (" + ",".join(langs) + ")" for name in row["mainname_altlist"]], *afterequals]


def _plp_row_make_linkednames(row, langmap):
    result = {}
    langs = row["langs"].split(",") if isinstance(row["langs"], str) else ["NOLANG"]
    try:
        for lang in langs:
            lang = utils.verify_lang(lang, langmap)
            result[lang] = [[name] for name in row["altlist"]]
    except KeyError as e:
        e.add_note(str(row))
        raise e
    return result


def plp_names(plp: pd.DataFrame, langmap: dict[str, str]) -> pd.DataFrame:
    """Collect people from PLp sheet and extract their names into
    a language-labeled dictionary where for each language there's a
    list of lists of alternative forms of their name.
    """
    plp = plp.copy()

    # Records with main name, pointing to associated works. Column can
    # contain a list of translations, as initials. Main name can contain
    # alternative forms in brackets, for any word separately or full
    # name as a whole.
    plp_people = plp.loc[plp["person_id"].notna(), ["type", "person_id", "names"]].set_index("person_id")

    # Records with translated name, pointing to main name. Main name as
    # initials.
    plp_alts = plp.loc[plp["alt_of"].notna(), ["alt_of", "names", "langs", "ogname"]]
    plp_alts = plp_alts[plp_alts["alt_of"].isin(plp["person_id"])]

    # Extract all unique names from main rows.
    plp_people[["names_before_equals", "names_after_equals"]] = plp_people["names"].str.split(" = ", expand=True)
    plp_people["names_after_equals"] = plp_people["names_after_equals"].str.split(", ")
    # Split main name from its language labels in parentheses, then
    # parse both.
    plp_people["mainname_with_alts"] = (
        plp_people["names_before_equals"].str.split(r" \([А-Яа-яЁёA-Za-z]{2}[\),]", regex=True).map(lambda x: x[0])
    )
    plp_people["mainname_langs"] = (
        plp_people["names_before_equals"]
        .str.extract(r"\(((?:[А-Яа-яЁёA-Za-z]{2})(?:,[А-Яа-яЁёA-Za-z]{2})*)\)$", expand=False)
        .str.split(",")
    )
    plp_people["mainname_altlist"] = plp_people["mainname_with_alts"].map(utils.expand_brackets_names)
    plp_people["mainname"] = plp_people["mainname_altlist"].map(lambda x: x[0])
    plp_people["all_src"] = plp_people.apply(_plp_row_make_allnames, axis=1, langmap=langmap)
    plp_people["namedict"] = plp_people.apply(lambda row: utils.make_namedict(row["all_src"], langmap), axis=1)

    # Extract all unique names from alternative rows.
    plp_alts["altlist"] = plp_alts["names"].map(utils.expand_brackets_names)
    plp_alts["linkednames"] = plp_alts.apply(_plp_row_make_linkednames, axis=1, langmap=langmap)
    plp_alts["langs"] = plp_alts["linkednames"].map(lambda x: list(x.keys()))
    plp_people["new_namedict"] = plp_people["namedict"].copy(deep=True)

    # Merge extracted names into one dict.
    for _, irow in plp_alts.iterrows():
        id = irow["alt_of"]
        currentnames = plp_people.at[id, "new_namedict"]
        for lang in irow["langs"]:
            ilang = lang
            if lang not in currentnames:
                currentnames[lang] = [irow["altlist"]]
            if "NOLANG" not in currentnames:
                currentnames["NOLANG"] = []
            found = False
            for i, item in enumerate(currentnames[ilang]):
                if any([utils.is_same_name(j, alt) for j in item for alt in irow["altlist"]]):
                    currentnames[ilang][i] = list(dict.fromkeys([*currentnames[ilang][i], *irow["altlist"]]))
                    if ilang == "NOLANG":
                        currentnames[lang] = [currentnames[ilang][i]]
                    found = True
                    break
            if not found:
                currentnames[lang].append(irow["altlist"])

    return plp_people


def _prs_row_make_alts(row):
    result = []
    if isinstance(row["names"], str) and row["names"] != "":
        result.append(row["names"])
    if isinstance(row["cyrillic"], str) and row["cyrillic"] != "":
        result.append(row["cyrillic"])
    return result


def prs_names(prs: pd.DataFrame) -> pd.DataFrame:
    """Collect people from Prs sheet and insert their names into
    a language-labeled dictionary where for each language there's a
    list of lists of alternative forms of their name.
    """
    prs = prs.copy()
    prs_people = (
        prs[prs["person_id"].notna()][["person_id", "type", "cyrillic", "names"]].set_index("person_id").fillna("")
    )
    prs_alts = prs[prs["alt_of"].notna()][["alt_of", "names"]]
    prs_alts["alt"] = prs_alts["names"].map(lambda x: x.split(" zob.")[0].rstrip(","))
    prs_people["alts"] = prs_people.apply(_prs_row_make_alts, axis=1)

    for _, row in prs_alts.iterrows():
        prs_people.at[row["alt_of"], "alts"].append(row["alt"])

    # ['Anninski Lew (Аннинский Л.А.)', 'Anninski L.'] <- It would be
    # good to extract name and brackets alts same as in PLp. Alas, alts
    # and use of parentheses in Prs are less feasible for parsing
    # because there is less of a pattern. Extraction would produce a lot
    # of erroneous data.

    return prs_people


def people_merge(plp_names: pd.DataFrame, prs_names: pd.DataFrame, person_prefix: str) -> pd.DataFrame:
    """Make a unified DataFrame of:

    - People referenced by Lem.
    - Lem, co-authors, authors of works about Lem, translators, editors,
      etc.

    that has `yid_lkg` and merged names dictionary `new_namedict`,
    ready to graph.
    """
    person_merge = pd.merge(plp_names, prs_names, how="outer", on=["person_id", "type"], suffixes=("_plp", "_prs"))
    person_merge[["mainname", "names_prs", "cyrillic"]] = person_merge[["mainname", "names_prs", "cyrillic"]].fillna(
        ""
    )
    duplicates = person_merge[person_merge.index.duplicated()]
    if len(duplicates) > 0:
        e = ValueError("Duplicate Person ID")
        e.add_note(duplicates.to_string())
        raise e
    for i, row in person_merge.iterrows():
        namedict = person_merge.at[i, "new_namedict"]
        if not isinstance(namedict, dict):
            namedict = {"NOLANG": []}
            person_merge.at[i, "new_namedict"] = namedict
        alts = row["alts"] if isinstance(row["alts"], list) else []
        for alt in alts:
            found = False
            for lang, namelist in namedict.items():
                for j, names in enumerate(namelist):
                    if any([utils.is_same_name(alt, x) for x in names]):
                        namedict[lang][j] = list(dict.fromkeys([*namedict[lang][j], *[alt]]))
                        found = True
            if not found:
                namedict["NOLANG"].append([alt])
    person_merge["yid_lkg"] = person_prefix + person_merge.index
    person_merge["search"] = person_merge["new_namedict"].map(
        lambda dct: " | ".join(
            list(dict.fromkeys({el: 0 for _, lst in dct.items() for sublst in lst for el in sublst}))
        )
    )
    return person_merge


def nf_cleanup(df: pd.DataFrame, cols: list[str], startcol: int):
    sheet = df.copy()
    sheet.columns = df.columns.astype(str)
    newcols = sheet.columns.tolist()
    newcols[startcol : startcol + len(cols)] = cols
    sheet.columns = newcols
    sheet.fillna("", inplace=True)
    sheet = prepare(sheet, None)
    sheet = sheet.apply(lambda x: x.str.strip())
    # Some refs have a space before a sub-id, this removes it
    sheet["refs"] = sheet["refs"].str.replace(r"\. +(\d)", r".\1", regex=True)
    sheet = sheet[(
        (
            (sheet["is_main"] == "@") &
            (sheet["yid_main"].str.isdigit() | sheet["yid_main"].str.contains("~"))
        ) |
        (
            sheet["yid_main"].str.contains("~") &
            (sheet["yid_sub"] != "")
        )
    )]
    return sheet


def _nf_row_yid_lkg(row: pd.Series, df: pd.DataFrame):
    if ('~' not in row["yid_main"] and row["yid_main"] != ""):
        return row["yid_main"]
    i = df.index.get_loc(row.name)
    if isinstance(i, str):
        print(i)
    while i > 0:
        i -= 1
        if re.search(r"\d+", df.iloc[i, df.columns.get_loc("yid_main")]):
            return ".".join([df.iloc[i, df.columns.get_loc("yid_main")], row["yid_sub"]])
    print(f"[Warning] Main YID not found for NF row:\n{row}")


def nf_filter_entities(nonfic: pd.DataFrame, prefix_nf, prefix_lang):
    """Handle range notation issues, add explicit YIDs in `yid_lkg`."""
    prefix = f"{prefix_nf}{prefix_lang}"
    # Explode "4.1÷4.14" range ID into rows with proper IDs.
    nonfic[["expid", "expref"]] = None
    nonfic.loc[nonfic["yid_sub"].str.contains("÷"), "expid"] = nonfic[nonfic["yid_sub"].str.contains("÷")].apply(
        lambda row: utils.expand_range(row["yid_sub"]), axis=1
    )
    nonfic.loc[nonfic["yid_sub"].str.contains("÷"), "expref"] = nonfic[nonfic["yid_sub"].str.contains("÷")].apply(
        lambda row: [int(row["refs"].rsplit(".", 1)[1]) + i for i in range(len(utils.expand_range(row["yid_sub"])))],
        axis=1,
    )
    nonfic = nonfic.explode(["expid", "expref"], ignore_index=True)
    nonfic.loc[nonfic["expid"].notna(), "yid_sub"] = nonfic.loc[nonfic["expid"].notna(), "expid"]
    # In exploded rows adjust ID in refs: "↑329.6.1" ->
    # "↑329.6.{{1 + i}}".
    nonfic.loc[nonfic["expid"].notna(), "refs"] = nonfic.loc[nonfic["expid"].notna()].apply(
        lambda row: f'{row["refs"].rsplit(".", 1)[0]}.{row["expref"]}', axis=1
    )
    # Get YIDs and check for duplicates.
    nonfic["yid_lkg"] = nonfic["yid_main"]
    nonfic["yid_lkg"] = nonfic.apply(_nf_row_yid_lkg, df=nonfic, axis=1)
    nonfic = nonfic[~nonfic["yid_lkg"].str.contains("~")]
    nonfic.loc[:, "yid_lkg"] = prefix + nonfic["yid_lkg"]
    duplicates = nonfic[nonfic.duplicated(subset=["yid_lkg"], keep=False)]
    if len(duplicates) > 0:
        print("[Warning] Duplicate YIDs in source data:\n", duplicates[["yid_lkg", "title"]])
    nonfic = nonfic.drop_duplicates(subset=["yid_lkg"])
    nonfic["part_of"] = nonfic["yid_lkg"].map(lambda x: x.split("÷")[0].rsplit(".", 1)[0])
    nonfic.loc[nonfic["yid_lkg"] == nonfic["part_of"], "part_of"] = ""
    # In exploded rows copy title from original in refs.
    nonfic = nonfic.set_index("yid_lkg", drop=False)
    titlestofix = nonfic.loc[nonfic["expid"].notna(), "title"]
    if not titlestofix.empty:
        nonfic.loc[nonfic["expid"].notna(), "title"] = nonfic.loc[nonfic["expid"].notna()].apply(
            lambda row: nonfic["title"].get(row["refs"].replace("↑", prefix)), axis=1
        )
    return nonfic


def _nf_row_pub_info(row: pd.Series, number_patterns: str) -> list[str]:
    if row["part_of"]:
        return [""] * 4
    name = row["publisher"].split(" (")[0].split(": ")[-1]
    year = re.match(r"\d{4}", row["pub_info"])
    year = year.group() if year else ""
    number = utils.cutout_issue_number(row["pub_info"], number_patterns)
    city = re.search(r"\((.+?)\)$", row["publisher"])
    city = city.group(1) if city else ""
    city = city.split(":")[0].split(")")[0]
    if not city:
        city = re.match(r"(.*?):", row["publisher"])
        city = city.group(1) if city else ""
    return [name, year, number, city]


def _nf_row_expanded_title(row: pd.Series, df: pd.DataFrame) -> str:
    title = row["title"]
    partof = row["part_of"]
    while partof and partof in df.index:
        nextrow = df.loc[partof]
        title = " | ".join([nextrow["title"], title])
        partof = nextrow["part_of"]
    return title


def _nf_row_normalize_refs(
    row: pd.Series, prefix_nf: str, prefix_lang: str, lang_prefixes: list[str], prefix_other: str
) -> list[str]:
    refs = row["refs"].strip("↑").split(" (")[0] if row["refs"].startswith("↑") else ""
    plus = refs.split("+") if refs != "" else []
    normalrefs = []
    normalparts = []
    prev_prefix = None
    for i, sref in enumerate(plus):
        for cref in sref.split("; "):
            for ref in cref.split(", "):
                # Normalize prefix.
                if ref[0] == ".":  # Case of "↑2358.2-+.22-".
                    ref = plus[i - 1].rsplit(".")[0] + ref
                    ref = prefix_nf + (prev_prefix or prefix_lang) + ref
                elif ref[0].isdigit():
                    if not prev_prefix:
                        prev_prefix = prefix_lang
                    ref = prefix_nf + prev_prefix + ref
                else:
                    prefix = re.match(r"[A-Za-z]+", ref)
                    if not prefix:
                        prefix = prev_prefix
                        number = re.match(r"\D*(.*)", ref).group(1)
                    else:
                        prefix = prefix.group()
                        number = ref[len(prefix) :].strip(":")
                        prev_prefix = prefix
                    if not prefix:
                        continue
                    else:
                        if prefix not in lang_prefixes:
                            ref = prefix_other + prefix + number
                            continue
                        else:
                            ref = prefix_nf + prefix + number
                # If there's a "÷" range, expand to explicit IDs. If
                # reference is within same language sheet, add as
                # components. Otherwise, add as references.
                parts = ref.split("÷")
                if len(parts) > 1:
                    idfirst = parts[0].rsplit(".", 1)
                    idlast = parts[-1].rsplit(".", 1)
                    if not idfirst[-1].isnumeric() or not idlast[-1].isnumeric():
                        continue
                    comps = [str(x) for x in range(int(idfirst[-1]), int(idlast[-1]) + 1)]
                    for c in comps:
                        if parts[0].startswith(prefix_nf + prefix_lang):
                            normalparts.append(f"{idfirst[0]}.{c}")
                        else:
                            normalrefs.append(f"{idfirst[0]}.{c}")
                else:
                    if not sref.endswith("?") and not ref.startswith(prefix_other):
                        normalrefs.append(ref)
    return [" ".join(normalparts), " ".join(normalrefs)]


def nf_process_sheet(
    sheet: pd.DataFrame,
    prefix_nf: str,
    prefix_other: str,
    lang: str,
    langlist: list[str],
    lem_names: list[str],
    nf_number_patterns: tuple[re.Pattern, re.Pattern],
    nf_cols: list[str],
    nf_newcols: list[str],
    main: pd.DataFrame,
) -> pd.DataFrame:
    """Do following:
    - Normalize referenced IDs into `refs_normal`, add IDs as children
      in `has_part` where ref is a range and within same language sheet.
    - Add `by_lem`.
    - Add `expanded_title` for context-independent component titles.
    - Add `pub_name`, `pub_number`, `city` with publishing info.
    - Join frame to main.
    """
    # Normalize referenced IDs, or if referencing a "÷" range, add
    # explicit IDs as parts
    sheet[["has_part", "refs_normal"]] = sheet.apply(
        _nf_row_normalize_refs,
        axis=1,
        result_type="expand",
        prefix_nf=prefix_nf,
        prefix_lang=lang,
        lang_prefixes=langlist,
        prefix_other=prefix_other,
    )
    # Get "full" title for chapters, e.g. "Summa technologiae | IV.
    # Intelelektronika | Powrót na ziemię"
    sheet["expanded_title"] = sheet.apply(_nf_row_expanded_title, axis=1, df=sheet)
    # Look for Lem's name in "author" column
    sheet["by_lem"] = pd.DataFrame({lnm: sheet["author"].str.contains(lnm, regex=False) for lnm in lem_names}).any(
        axis=1
    )
    # Extract publishing details into separate fields, including issue
    # numbers
    sheet[["pub_name", "pub_year", "pub_number", "city"]] = sheet.apply(
        _nf_row_pub_info, axis=1, result_type="expand", number_patterns=nf_number_patterns[lang]
    )
    # Join frame to main works
    current_main = sheet.loc[~sheet["part_of"].astype(bool), nf_cols + nf_newcols]
    return pd.concat([main, current_main], axis=0)


def nf_publishers(
    publishers: pd.DataFrame, nf_main: pd.DataFrame, cities_to_geonames: pd.DataFrame, prefix_publisher: str
) -> pd.DataFrame:
    """Collect additional publishers from Non Fiction and return joined
    frame.
    """
    nf_pub = nf_main[["pub_name", "city"]].groupby("pub_name").first()
    nf_pub = nf_pub[~nf_pub.index.isin(publishers["publisher"])]
    nf_cities = nf_pub["city"].drop_duplicates()
    nf_new_cities = nf_cities[~nf_cities.isin(cities_to_geonames.index)]
    if len(nf_new_cities) > 0:
        msg = (
            f"[Warning] {str(len(nf_new_cities))} publishers from Non Fiction sheets have city names that don't appear "
            f"in '{PATH_EXTR_CITY}'. To have these recognized as cities in graph, transfer 'city' names from "
            f"'{PATH_EXTR_CITY_NEW}' into '{PATH_EXTR_CITY}' and assign them proper IDs. Don't transfer names that "
            "don't look like cities."
        )
        print(msg)
        nf_new_cities.to_excel(PATH_EXTR_CITY_NEW)
    nf_pub["uri_place"] = nf_pub["city"].map(lambda x: cities_to_geonames["uri"].get(x))
    nf_pub["publisher"] = nf_pub.index

    allpublishers = pd.concat([publishers, nf_pub], ignore_index=True)
    allpublishers["yid_lkg"] = prefix_publisher + allpublishers.index.astype(str)
    allpublishers["uri"] = "F11_" + allpublishers["yid_lkg"]
    allpublishers.set_index("publisher", drop=False, inplace=True)

    return allpublishers


def nf_issues(nf_main: pd.DataFrame, prefix_journal: str) -> pd.DataFrame:
    """Collect journal issues from Non Fiction."""
    results = nf_main[nf_main["pub_number"] != ""][["pub_name", "pub_year", "pub_number"]]
    results = results.drop_duplicates(ignore_index=True)
    results["yid_lkg"] = prefix_journal + results.index.astype(str)
    results.set_index(["pub_name", "pub_year", "pub_number"], drop=False, inplace=True)
    return results


def authorships(
    plp: pd.DataFrame,
    nf_main: pd.DataFrame,
    lang_list: list[str],
    prefix_person: str,
    prefix_nf: str,
    prefix_other: str,
) -> pd.DataFrame:
    """Relate people to their works based on references listed in sheet
    `PLp`. Extract refs into list, transform IDs into explicit `lkg_yid`
    by adding prefixes, finally connect to F28 Expression Creation as
    author or translator.

    As Lem does not have a specific list of references in `PLp`, he will
    instead be connected to any work in a NF dataframe where `author`
    column contains some form of his name.
    """
    authors_plp = plp[plp["alt_of"].isna()].copy()

    author_startcol = authors_plp.columns.get_loc("langs")
    last_author = 0
    last_prefix = "PL"
    authors_plp["refs_normal"] = [[] for _ in authors_plp.index]
    for i, row in authors_plp.iterrows():
        if row["person_id"]:
            last_author = i
            last_prefix = "PL"
            refs_list = row["refs_normal"]
        else:
            refs_list = authors_plp.at[last_author, "refs_normal"]
        for cell in row.iloc[author_startcol:]:
            if not isinstance(cell, str) or len(cell) == 0:
                continue
            prefix_match = re.match(r"[A-Za-z]+", cell)
            if prefix_match:
                # for now only include nf references
                if prefix_match.group() not in lang_list:
                    continue
                last_prefix = prefix_match.group()
                cell = cell[len(last_prefix) :].strip(":")
            if not isinstance(cell, str) or len(cell) == 0:
                # TODO: condition skips first prefix in cases like
                # Jeżewski Krzysztof   –  PL:     B44  /  FR:B1. These
                # cases refer to external poem bibliography excel: "Lem
                # Non-Fiction Wiersze Bibliografia.xls". We should
                # include that later on.
                continue
            # Repeat in case of double prefix like Kapuściński Ryszard |
            # – | PL:D10 |,| D11 |,| D18. This skips first prefix.
            prefix_match = re.match(r"[A-Za-z]+", cell)
            if prefix_match:
                if prefix_match.group() not in lang_list:
                    continue
                last_prefix = prefix_match.group()
                cell = cell[len(last_prefix) :].strip(":")
            if cell[0].isdigit():
                newrefs = utils.normalize_ref(
                    cell,
                    prefix_default=last_prefix,
                    prefix_nf=prefix_nf,
                    lang_prefixes=lang_list,
                    prefix_other=prefix_other,
                ).split()
                if all([r.startswith(prefix_nf) for r in newrefs]):
                    refs_list += newrefs

    authorships = authors_plp.dropna(subset=["person_id"])[["person_id", "refs_normal"]].set_index("person_id")
    lemrefs = nf_main.loc[nf_main["by_lem"], "yid_lkg"].tolist()
    authorships.loc["0", "refs_normal"] = lemrefs
    authorships["yid_lkg"] = prefix_person + authorships.index

    return authorships


def monographs(sheet: pd.DataFrame, prefix_mg: str, prefix_nf: str, lang_prefixes: list[str], prefix_other: str, ignores: dict[str, list[str]]):
    work_expressions = []
    last_lang = "PL"
    work_yid = "MONXXX"
    refcols = [c for c in sheet.columns.tolist() if c.isdigit()]
    for i, row in sheet.iterrows():
        is_list = False
        # New F1 Work
        if row["is_main"] == "@" and row["yid_main"] != "":
            last_lang = row["1"].split(":")[0]
            # Create singular F1 Work for multi-volume F2 Expressions
            work_yid = prefix_mg + row["yid_main"]
            refs = utils.normalize_ref(row["1"], last_lang, prefix_nf, lang_prefixes, prefix_other).split()
            work_expressions.append({
                "yid": work_yid,
                "title": row["title"],
                "lang": last_lang,
                "originals": refs,
                "derivatives": []
            })
            is_list = True
        # New language
        elif row["equals"] == "–" and row["1"] != "":
            last_lang = row["1"].split(":")[0]
            is_list = True
        # Continue last language
        elif row["equals"] == "" and row["1"] != "":
            is_list = True
        if is_list:
            refs = []
            for c in refcols:
                if row[c] == "":
                    continue
                refs += [utils.normalize_ref(row[c], last_lang, prefix_nf, lang_prefixes, prefix_other).split()]
            # Except for first cell of first line, add all as derivatives
            start_num = 0
            if not work_expressions[-1]["derivatives"] and row["is_main"] == "@" and row["yid_main"] != "":
                start_num = 1
            work_expressions[-1]["derivatives"] += refs[start_num:]
    preignores = {prefix_mg + k: v for k, v in ignores.items()}
    for mon in work_expressions:
        ignorelist = preignores.get(mon["yid"])
        if not ignorelist:
            continue
        ignorelangs = [i for i in ignorelist if i.isalpha()]
        ignorerefs = [i for i in ignorelist if not i.isalpha()]
        for ilang in ignorelangs:
            mon["derivatives"] = [exp for exp in mon["derivatives"] if not any([i.startswith(prefix_nf+ilang) for i in exp])]
        denyindices = []
        for iref in ignorerefs:
            ispl = iref.split(":")
            ilang = ispl[0]
            inum = int(ispl[1])
            i = 0
            ilastlang = None
            for index, exp in enumerate(mon["derivatives"]):
                ithislang = exp[0].removeprefix(prefix_nf)[:2]
                if ithislang != ilastlang:
                    ilastlang = ithislang
                    i = 0
                i += 1
                if ithislang == ilang and i == inum:
                    denyindices.append(index)
        mon["derivatives"] = [exp for i, exp in enumerate(mon["derivatives"]) if i not in denyindices]
    return work_expressions
