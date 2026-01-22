import re
import string
from enum import Enum
from pathlib import Path

import pandas as pd
import numpy as np
from lingua import LanguageDetector, LanguageDetectorBuilder, IsoCode639_1
from rdflib import Graph, Literal, URIRef
from rdflib.paths import OneOrMore, ZeroOrMore, ZeroOrOne

from namespaces import *
from config import SHOW_WARNINGS, WARNINGS, WARN_PAST

APPMAP_PREDICATE = {
    CIDOC.E41_Appellation: CIDOC.P1_is_identified_by,
    CIDOC.E42_Identifier: CIDOC.P1_is_identified_by,
    CIDOC.E35_Title: CIDOC.P102_has_title,
}
APPMAP_INVERSE_PREDICATE = {
    CIDOC.E41_Appellation: CIDOC.P1i_identifies,
    CIDOC.E42_Identifier: CIDOC.P1i_identifies,
    CIDOC.E35_Title: CIDOC.P102i_is_title_of,
}
REFCHARS = {
    "-": "SKIP", # This character means only a citation. For now don't link.
    ">": LKG.S763_is_reduced_form_of,
    "<": LKG.S764_is_extended_form_of,
    "!": LKG.S762_is_altered_form_of,
}
UILABEL = SKOS.prefLabel
ORDERLABEL = SKOS.hiddenLabel
SEARCHLABEL = SKOS.altLabel

autoinc_id_counts: dict[str, int] = {}


def import_lkg(path: Path | str) -> Graph:
    """Load generated graph for further operations.
    Read and continue existing autoincrement IDs and values.
    """
    g = make_base_graph()
    g.parse(path)
    simple_ids = [*APPMAP_PREDICATE.keys(), CIDOC.E52_Time_Span]
    order_ids = [LRMOO.F1_Work, LRMOO.F2_Expression, LRMOO.F3_Manifestation]
    prefixed_ids = [CIDOC.E21_Person, CIDOC.E53_Place, LRMOO.F11_Corporate_Body]
    for i in simple_ids + prefixed_ids:
        prefix = get_class_prefix(get_id_from_uri(i))
        numbers = np.char.rsplit(list(g.subjects(RDF.type, i)), sep="_", maxsplit=1)
        numbers = [n[-1] for n in numbers]
        numbers = np.char.lstrip(numbers, chars=string.ascii_letters).astype(int)
        autoinc_id_counts[prefix] = numbers.max() + 1
    for i in order_ids:
        prefix = get_class_prefix(get_id_from_uri(i))
        numbers = np.array([g.value(entity, ORDERLABEL, None).value for entity in g.subjects(RDF.type, i)], dtype=int)
        autoinc_id_counts[prefix] = numbers.max() + 1
    # for i in autoinc_id_counts.items():
    #     print(i)
    return g


def get_id_from_uri(uri: str | URIRef) -> str:
    """Get local resource ID from a full URI.

    Args:
        uri (str | URIRef): Full URI of resource.

    Returns:
        str: Local resource ID.

    Examples:
        >>> get_id_from_uri("http://www.cidoc-crm.org/cidoc-crm/E35_Title")
        'E35_Title'
    """
    split = uri.rsplit("/", 1)
    res = split[-1]
    if len(split) == 1:
        split = uri.rsplit("#", 1)
        res = split[-1]
        if len(split) == 1:
            res = uri
    return res


def get_class_prefix(id: str) -> str:
    """Get class prefix from local resource ID.

    Args:
        id (str): Local resource ID.

    Returns:
        str: Class prefix.

    Examples:
        >>> get_prefix_from_id("E35_Title")
        'E35'
    """
    return id.split("_")[0]


def make_autoinc_id(prefix: str) -> str:
    """Create local resource ID from prefix with auto-increment.

    Use for mass-produced entities where ID is not important. For meaningful
    entities prefer YID to auto-increment.

    Args:
        prefix (str):
            ID prefix

    Returns:
        str:
            ID consisting of prefix and auto-incremented number, separated by
            underscore.

    Examples:
        >>> make_autoinc_id("E42")
        'E42_0'
        >>> make_autoinc_id("E42")
        'E42_1'
        >>> make_autoinc_id("E35")
        'E35_0'
    """
    if prefix not in autoinc_id_counts:
        autoinc_id_counts[prefix] = 0
    uri = f"{prefix}_{autoinc_id_counts[prefix]}"
    autoinc_id_counts[prefix] += 1
    return uri


def add_types(graph: Graph, types: pd.DataFrame):
    for t, row in types.iterrows():
        uri = "E55_" + t
        graph.add((LKG[uri], RDF.type, CIDOC.E55_Type))
        graph.add((LKG[uri], RDFS.label, Literal("E55 " + row["label"])))
        graph.add((LKG[uri], UILABEL, Literal(row["label"], lang="en")))


def add_langs(graph: Graph, langnames: pd.DataFrame):
    for _, row in langnames.iterrows():
        if row.name == "NOLANG":
            continue
        uri = row.name
        graph.add((LKG[uri], RDF.type, CIDOC.E56_Language))
        graph.add((LKG[uri], RDFS.label, Literal("E56 " + row["name"])))
        graph.add((LKG[uri], UILABEL, Literal(row["name"], lang="en")))
        part1 = row["iso639-1"]
        part3 = row["iso639-3"]
        if part1:
            add_appellation(graph, uri, part1, appel_class=CIDOC.E42_Identifier, has_types=["E55_ISO_639_1"])
        if part3:
            add_appellation(graph, uri, part3, appel_class=CIDOC.E42_Identifier, has_types=["E55_ISO_639_3"])
        if row["idwd"]:
            graph.add((LKG[uri], OWL.sameAs, WD[row["idwd"]]))


def add_timespan(graph: Graph, subject: str, subject_label: str, date: str, yid: str = None):
    uri = make_autoinc_id("E52")
    date = int(date)  # For now assume only year
    graph.add((LKG[uri], RDF.type, CIDOC.E52_Time_Span))
    graph.add((LKG[uri], RDFS.label, Literal(f'E52 {subject_label}{f" (YID: {yid})" if yid else ""}')))
    graph.add((LKG[uri], CIDOC.P82a_begin_of_the_begin, Literal(date, datatype=XSD.gYear)))
    graph.add((LKG[uri], CIDOC.P82b_end_of_the_end, Literal(date, datatype=XSD.gYear)))
    graph.add((LKG[subject], CIDOC.P4_has_time_span, LKG[uri]))
    return uri


def add_appellation(
    graph: Graph,
    subject: str,
    appel_value: str,
    appel_type: str | None = None,
    appel_label: str | None = None,
    appel_class: URIRef = CIDOC.E41_Appellation,
    has_types: list[URIRef | str] = [],
    has_language: URIRef | str | None = None,
    lang_detector: LanguageDetector | None = None,
    refgraph: Graph | None = None,
):
    """
    Add CIDOC appellation and connect it to subject. 
    
    Args:
        graph (rdflib.Graph): Graph to add to.
        subject (str): Local ID of subject entity.
        appel_value (str): Value of appellation's Literal.
        appel_type (str | None): Data type of appellation's Literal.
        appel_label (str | None): Custom rdfs:label value for appellation.
        appel_class (rdflib.URIRef): CIDOC appellation class. Supported classes: E41_Appellation, E42_Identifier, E35_Title.
        has_types (list[rdflib.URIRef | str]): URIRefs or Local IDs of CIDOC types to add with P2_has_type.
        has_language (rdflib.URIRef | str | None): URIRef or Local ID of language.
        lang_detector (lingua.LanguageDetector | None): Detector for machine language recognition.
        refgraph (rdflib.Graph | None): Reference graph to pull type labels from. If it can't find label in refgraph, will look in graph. Only used when has_types is set.

    Returns:
        str:
            Local ID of appellation.
    """
    uri = make_autoinc_id(get_class_prefix(get_id_from_uri(appel_class)))
    label = f'{uri.split("_")[0]} {appel_label if appel_label else appel_value}'
    refgraph = refgraph or graph
    objs_type = [t if isinstance(t, URIRef) else LKG[t] for t in has_types]
    typelabels = []
    for i in objs_type:
        for g in [refgraph, graph]:
            tlab = refgraph.value(i, UILABEL, None)
            if tlab:
                break
        if not tlab:
            if SHOW_WARNINGS and not WARN_PAST[WARNINGS.NO_LABEL_FOR_TYPE]:
                warn_msg = f"[Warning] {WARNINGS.NO_LABEL_FOR_TYPE.value}: Can't find property {UILABEL} for type: {i}."
                WARN_PAST[WARNINGS.NO_LABEL_FOR_TYPE] = warn_msg
                print(warn_msg)
            tlab = get_id_from_uri(i).replace("_", " ")
        typelabels.append(tlab)
    label += " [" + ", ".join(typelabels) + "]" if has_types else ""
    if lang_detector and not has_language and appel_class == CIDOC.E41_Appellation:
        label += " # LANGUAGE AUTO-DETECTED"
        lang = lang_detector.detect_language_of(appel_value)
        has_language = "E56_" + lang.iso_code_639_3.name.lower() if lang else None
    graph.add((LKG[uri], RDF.type, appel_class))
    graph.add((LKG[uri], RDFS.label, Literal(label)))
    graph.add((LKG[uri], APPMAP_INVERSE_PREDICATE[appel_class], LKG[subject]))
    val = Literal(appel_value, datatype=appel_type) if appel_type is not None else Literal(appel_value)
    graph.add((LKG[uri], CIDOC.P190_has_symbolic_content, val))
    graph.add((LKG[subject], APPMAP_PREDICATE[appel_class], LKG[uri]))
    for i in objs_type:
        graph.add((LKG[uri], CIDOC.P2_has_type, i))
    if has_language:
        o_lang = has_language if isinstance(has_language, URIRef) else LKG[has_language]
        graph.add((LKG[uri], CIDOC.P72_has_language, o_lang))
    return uri


def add_places(graph: Graph, cities: pd.DataFrame):
    """Expected columns: uri, geonameid, wdid, city, city_pl, country"""
    for _, row in cities.iterrows():
        uri = row.name
        geonameid = row["geonameid"]
        wdid = row["wdid"]
        base_label_info_data = []
        if isinstance(geonameid, str) or isinstance(wdid, str):
            if isinstance(geonameid, str):
                base_label_info_data.append("GEO: " + geonameid)
            if isinstance(wdid, str):
                base_label_info_data.append("WD: " + wdid)
        base_label_info = f" ({', '.join(base_label_info_data)})" if base_label_info_data else ""
        base_label = f'{row["wd_city"]}, {row["wd_country"]}{base_label_info}'
        e53_label = "E53 " + base_label
        graph.add((LKG[uri], RDF.type, CIDOC.E53_Place))
        graph.add((LKG[uri], RDFS.label, Literal(e53_label)))
        graph.add((LKG[uri], UILABEL, Literal(row["wd_city"], lang="en")))
        if isinstance(geonameid, str) and geonameid != "":
            graph.add((LKG[uri], OWL.sameAs, GN[geonameid]))
        if isinstance(wdid, str) and wdid != "":
            graph.add((LKG[uri], OWL.sameAs, WD[wdid]))
        add_appellation(graph, uri, row["wd_city"], appel_label=base_label, has_language="E56_eng")
        add_appellation(graph, uri, row["wd_city_pl"], appel_label=base_label, has_language="E56_pol")


def add_people(graph: Graph, people: pd.DataFrame, languages: pd.DataFrame, lang_detector: LanguageDetector | None = None):
    people["uri"] = "E21_" + people["yid_lkg"]
    for _, row in people.iterrows():
        uri = row["uri"]
        mainname = row["mainname"] or row["names_prs"] or row["cyrillic"]
        base_label = f'{mainname} (YID: {row["yid_lkg"]})'
        graph.add((LKG[uri], RDF.type, CIDOC.E21_Person))
        graph.add((LKG[uri], RDFS.label, Literal("E21 " + base_label)))
        graph.add((LKG[uri], UILABEL, Literal(mainname)))
        graph.add((LKG[uri], ORDERLABEL, Literal(re.sub(r"[A-Za-z]+", "", row["yid_lkg"]), datatype=XSD.float)))
        # graph.add((LKG[uri], SEARCHLABEL, Literal(row["search"])))
        add_appellation(
            graph,
            uri,
            row["yid_lkg"],
            appel_label=base_label,
            appel_class=CIDOC.E42_Identifier,
            has_types=["E55_YID"],
            lang_detector=lang_detector,
        )
        language_map = languages.dropna(subset=["iso639-1"]).set_index("iso639-1")
        for l, variantslist in row["new_namedict"].items():
            lang = None if l == "NOLANG" else l
            lang_uri = language_map["uri"].get(lang) if lang else None
            for variants in variantslist:
                appellations = []
                for variant in variants:
                    graph.add((LKG[uri], SEARCHLABEL, Literal(variant)))
                    appellations.append(add_appellation(
                        graph,
                        uri,
                        variant,
                        appel_label=f'{variant} (YID: {row["yid_lkg"]})',
                        has_language=lang_uri,
                        lang_detector=lang_detector,
                    ))
                for i, ai in enumerate(appellations):
                    for j, aj in enumerate(appellations):
                        if i != j:
                            graph.add((LKG[ai], CIDOC.P139_has_alternative_form, LKG[aj]))
                            graph.add((LKG[aj], CIDOC.P139_has_alternative_form, LKG[ai]))


def add_publishers(graph: Graph, publishers, lang_detector: LanguageDetector | None = None):
    for _, row in publishers.iterrows():
        uri = row["uri"]
        base_label = f'{row["publisher"]} (YID: {row["yid_lkg"]})'
        graph.add((LKG[uri], RDF.type, LRMOO.F11_Corporate_Body))
        graph.add((LKG[uri], RDFS.label, Literal("F11 " + base_label)))
        graph.add((LKG[uri], UILABEL, Literal(row["publisher"])))
        graph.add((LKG[uri], ORDERLABEL, Literal(re.sub(r"[A-Za-z]+", "", row["yid_lkg"]), datatype=XSD.float)))
        graph.add((LKG[uri], SEARCHLABEL, Literal(row["publisher"])))
        add_appellation(
            graph, uri, row["yid_lkg"], appel_label=base_label, appel_class=CIDOC.E42_Identifier, has_types=["E55_YID"]
        )
        add_appellation(graph, uri, row["publisher"], appel_label=base_label, lang_detector=lang_detector)
        places = row["uri_place"].split() if isinstance(row["uri_place"], str) else []
        for p in places:
            graph.add((LKG[uri], CIDOC.P74_has_current_or_former_residence, LKG[p]))
            # For now no inverse because it makes it harder to query out
            # a subgraph about one entity
            # graph.add((LKG[placeid], CIDOC.P74i_is_current_or_former_residence_of, LKG[uri]))


def add_issues(
    graph: Graph, issues: pd.DataFrame, publishers: pd.DataFrame, lang_detector: LanguageDetector | None = None
):
    for _, row in issues.iterrows():
        f3_uri = f'F3_{row["yid_lkg"]}'
        base_name = f'{row["pub_name"]}, {row["pub_year"]}, {row["pub_number"]}'
        base_label = f'{row["pub_name"]}, {row["pub_year"]}, {row["pub_number"]} (YID: {row["yid_lkg"]})'
        graph.add((LKG[f3_uri], RDF.type, LRMOO.F3_Manifestation))
        graph.add((LKG[f3_uri], RDFS.label, Literal(f"F3 {base_label}")))
        graph.add((LKG[f3_uri], UILABEL, Literal(base_name)))
        add_appellation(graph, f3_uri, base_name, lang_detector=lang_detector)
        add_appellation(
            graph,
            f3_uri,
            row["pub_name"],
            appel_label=base_name,
            appel_class=CIDOC.E42_Identifier,
            has_types=["E55_Journal_Name"],
        )
        add_appellation(
            graph,
            f3_uri,
            row["pub_number"],
            appel_label=base_name,
            appel_class=CIDOC.E42_Identifier,
            has_types=["E55_Journal_Number"],
        )
        add_appellation(
            graph,
            f3_uri,
            row["pub_year"],
            appel_type=XSD.gYear,
            appel_label=base_name,
            appel_class=CIDOC.E42_Identifier,
            has_types=["E55_Journal_Date"],
        )
        f30_uri = "F30_" + row["yid_lkg"]
        graph.add((LKG[f30_uri], RDF.type, LRMOO.F30_Manifestation_Creation))
        graph.add((LKG[f30_uri], RDFS.label, Literal(f"F30 {base_label}")))
        graph.add((LKG[f30_uri], LRMOO.R24_created, LKG[f3_uri]))
        graph.add((LKG[f3_uri], LRMOO.R24i_was_created_through, LKG[f30_uri]))
        graph.add((LKG[f30_uri], LKG.S145_published_by, LKG[publishers["uri"].get(row["pub_name"])]))
        if row["pub_year"]:
            add_timespan(graph, f30_uri, base_label, row["pub_year"], row["yid_lkg"])


def add_nonfic(
    graph: Graph, df: pd.DataFrame, lang: str, issues: pd.DataFrame, publishers: pd.DataFrame, nfprefix: str, languages: pd.DataFrame
):
    language_map = languages.dropna(subset=["iso639-1"]).set_index("iso639-1")
    for _, row in df.iterrows():
        lang_uri = language_map["uri"].get(lang)
        base_label = f'{row["title"]} (YID: {row["yid_lkg"]})'

        # Add F2 Expression
        f2_uri = "F2_" + row["yid_lkg"]
        f2_label = "F2 " + base_label
        graph.add((LKG[f2_uri], RDF.type, LRMOO.F2_Expression))
        graph.add((LKG[f2_uri], RDFS.label, Literal(f2_label)))
        graph.add((LKG[f2_uri], CIDOC.P72_has_language, LKG[lang_uri]))
        graph.add((LKG[f2_uri], UILABEL, Literal(row["title"])))
        add_appellation(
            graph, f2_uri, row["title"], appel_label=base_label, appel_class=CIDOC.E35_Title, has_language=lang_uri
        )
        yid_uri = add_appellation(
            graph,
            f2_uri,
            row["yid_lkg"],
            appel_label=base_label,
            appel_class=CIDOC.E42_Identifier,
            has_types=["E55_YID"],
        )

        # Add F28 Expression Creation
        f28_uri = "F28_" + row["yid_lkg"]
        f28_label = "F28 " + base_label
        graph.add((LKG[f28_uri], RDF.type, LRMOO.F28_Expression_Creation))
        graph.add((LKG[f28_uri], RDFS.label, Literal(f28_label)))
        graph.add((LKG[f28_uri], LRMOO.R17_created, LKG[f2_uri]))
        graph.add((LKG[f2_uri], LRMOO.R17i_was_created_by, LKG[f28_uri]))
        if row["by_lem"]:
            person_uri = "E21_P0"
            graph.add((LKG[f28_uri], LKG.S142_written_by, LKG[person_uri]))

        # Enable querying with smart YID order
        graph.add((LKG[f2_uri], ORDERLABEL, Literal(make_autoinc_id("F2").split("_")[-1], datatype=XSD.float)))
        # Enable querying chapters by full title
        graph.add((LKG[f2_uri], SEARCHLABEL, Literal(row["expanded_title"].replace("| ", ""))))


        # Link to source if derivative
        for ref in row["refs_normal"].split():
            preciserels = []
            skip = False
            while not ref[-1].isdigit():
                pr = REFCHARS.get(ref[-1])
                if pr:
                    if pr == "SKIP":
                        skip = True
                        # Temporary flag to not create F1 Work
                        graph.add((LKG[f2_uri], LKG["SKIP"], Literal(True)))
                        break
                    preciserels.append(pr)
                ref = ref[:-1]
                if not ref:
                    print('uhoho')
            if skip:
                continue
            if ref.startswith(nfprefix):
                nextprefix = re.match(r"[A-Za-z]+", ref[len(nfprefix) :]).group()
                if nextprefix != lang:
                    preciserels.append(LKG.S761_is_translation_of)
            src_uri = "F2_" + ref
            for pr in preciserels:
                graph.add((LKG[f2_uri], pr, LKG[src_uri]))
            if not preciserels:
                graph.add((LKG[f2_uri], LRMOO.R76_is_derivative_of, LKG[src_uri]))

        # Link to parts
        for component in row["has_part"].split():
            component_f2_uri = "F2_" + component
            graph.add((LKG[f2_uri], LRMOO.R5_has_component, LKG[component_f2_uri]))
            graph.add((LKG[component_f2_uri], LRMOO.R5i_is_component_of, LKG[f2_uri]))

        # Link to parent if child
        if row["part_of"]:
            part_of_f2_uri = "F2_" + row["part_of"]
            graph.add((LKG[part_of_f2_uri], LRMOO.R5_has_component, LKG[f2_uri]))
            graph.add((LKG[f2_uri], LRMOO.R5i_is_component_of, LKG[part_of_f2_uri]))
            continue

        # Add everything F3 Manifestation
        f3_uri = None
        # If it's published in a journal, journal issue is the F3
        if row["pub_number"] != "":
            f3_uri = "F3_" + issues.at[tuple(row[["pub_name", "pub_year", "pub_number"]].values), "yid_lkg"]
            # NOTE: it would be helpful to add label that contains title
            # of F2 apart from publishing details. But currently some
            # F3s embody 2 F2s making it ambiguous which title to adopt.
        else:
            # Add F3 Manifestation
            f3_uri = "F3_" + row["yid_lkg"]
            f3_label = "F3 " + base_label
            labelparts = [row["title"], row["pub_name"]]
            if isinstance(row["pub_year"], str) and row["pub_year"] != "":
                labelparts.append(row["pub_year"])
            f3_uilabel = ", ".join(labelparts)
            graph.add((LKG[f3_uri], RDF.type, LRMOO.F3_Manifestation))
            graph.add((LKG[f3_uri], RDFS.label, Literal(f3_label)))
            graph.add((LKG[f3_uri], UILABEL, Literal(f3_uilabel)))

            # Add F30 Manifestation Creation
            f30_uri = "F30_" + row["yid_lkg"]
            f30_label = "F30 " + base_label
            graph.add((LKG[f30_uri], RDF.type, LRMOO.F30_Manifestation_Creation))
            graph.add((LKG[f30_uri], RDFS.label, Literal(f30_label)))
            graph.add((LKG[f30_uri], LRMOO.R24_created, LKG[f3_uri]))
            graph.add((LKG[f30_uri], LKG.S145_published_by, LKG[publishers["uri"].get(row["pub_name"])]))
            graph.add((LKG[f3_uri], LRMOO.R24i_was_created_through, LKG[f30_uri]))
            if row["pub_year"]:
                add_timespan(graph, f30_uri, row["title"], row["pub_year"], row["yid_lkg"])

        # Link F2 and F3
        graph.add((LKG[f3_uri], CIDOC.P1_is_identified_by, LKG[yid_uri]))
        graph.add((LKG[yid_uri], CIDOC.P1i_identifies, LKG[f3_uri]))
        graph.add((LKG[f3_uri], LRMOO.R4_embodies, LKG[f2_uri]))
        graph.add((LKG[f2_uri], LRMOO.R4i_is_embodied_in, LKG[f3_uri]))

        order = graph.objects(subject=LKG[f3_uri], predicate=ORDERLABEL)
        if not list(order):
            graph.add((LKG[f3_uri], ORDERLABEL, Literal(make_autoinc_id("F3").split("_")[-1], datatype=XSD.float)))


def add_authorships(graph: Graph, df: pd.DataFrame):
    """Connect authors to their F28 Expression Creation events.

    Also recursively propagate relation up and down in F2 hierarchy,
    meaning author of 195.4 is also author of 195 and 195.4.1

    Run after adding all possible F2 Expressions: person will be added
    as translator if expression is a translation. However Lem will
    always be as author because it's unclear without context if he did
    translate or not.

    Args:
        graph (Graph): The graph to add to.
        df (str): DataFrame expected to have "yid_lkg" and "refs_normal"
            columns. "refs_normal" for each row must contain a list of
            valid LKG YIDs for linking to expressions.
    """
    df["uri"] = "E21_" + df["yid_lkg"]
    for _, row in df.iterrows():
        uri = row["uri"]
        refs = row["refs_normal"]
        for ref in refs:
            f2_uri = "F2_" + ref
            f28_uri = "F28_" + ref
            deriv_props = [
                LKG.S762_is_altered_form_of,
                LKG.S763_is_reduced_form_of,
                LKG.S764_is_extended_form_of,
                LRMOO.R76_is_derivative_of,
            ]
            if LKG.S761_is_translation_of in graph.predicates(subject=LKG[f2_uri]) and row["uri"] != "E21_P0":
                if not (LKG[f28_uri], LKG.S143_translated_by, LKG[uri]) in graph:
                    graph.add((LKG[f28_uri], LKG.S143_translated_by, LKG[uri]))
                prop = LKG.S143_translated_by
            # elif any([prop in graph.predicates(subject=LKG[f2_uri]) for prop in deriv_props]):
            #     graph.add((LKG[f28_uri], LKG.S142_written_by, LKG[uri]))
            else:
                # Add relation even if F2 doesn't exist
                if not (LKG[f28_uri], LKG.S142_written_by, LKG[uri]) in graph:
                    graph.add((LKG[f28_uri], LKG.S142_written_by, LKG[uri]))
                prop = LKG.S142_written_by
            # elif LKG[f2_uri] not in graph.subjects():
            #     if self.warnings:
            #         print(f'[Warning] Can\'t add authorship {uri} to {f28_uri}: F2 not present in graph.')

            # Propagate authorship up and down
            propagate_through_prop(
                graph, LKG[f2_uri], LRMOO.R5i_is_component_of, prop, LKG[uri], LRMOO.R17i_was_created_by
            )
            propagate_through_prop(
                graph, LKG[f2_uri], LRMOO.R5_has_component, prop, LKG[uri], LRMOO.R17i_was_created_by
            )


def infer_works(graph: Graph) -> Graph:
    derivpath = (
        LRMOO.R76_is_derivative_of
        | LKG.S761_is_translation_of
        | LKG.S762_is_altered_form_of
        | LKG.S763_is_reduced_form_of
        | LKG.S764_is_extended_form_of
    ) * OneOrMore
    authorprops = [
        LKG.S141_composed_by,
        LKG.S142_written_by,
        LKG.S143_translated_by,
        LKG.S144_edited_by,
        LKG.S146_performed_by,
        LKG.S147_directed_by
    ]
    copyprops = [
        CIDOC.P102_has_title,
        CIDOC.P1_is_identified_by,
        CIDOC.P72_has_language,
        SEARCHLABEL,
        UILABEL
    ]
    g = make_base_graph()
    for exp in graph.subjects(RDF.type, LRMOO.F2_Expression):
        sources = list(graph.objects(exp, derivpath, unique=True))
        if not sources and graph.value(exp, LRMOO.R3i_realises, None) is None:
            # Don't make F1 Work for F2 containing a "-" reference
            skip = list(graph.triples((exp, LKG["SKIP"], None)))
            if skip:
                continue
            propslist = list(graph.predicate_objects(exp))
            propsdict = dict(propslist)
            f2_id = get_id_from_uri(exp)
            f2_label = propsdict[RDFS.label]
            f1_id = f2_id.replace("F2_", "F1_", 1)
            f1_label = f2_label.replace("F2", "F1", 1)
            f27_id = f2_id.replace("F2_", "F27_", 1)
            f27_label = f2_label.replace("F2", "F27", 1)
            f28_id = f2_id.replace("F2_", "F28_", 1)
            g.add((LKG[f1_id], RDF.type, LRMOO.F1_Work))
            g.add((LKG[f1_id], RDFS.label, Literal(f1_label)))
            for p in copyprops:
                g.add((LKG[f1_id], p, propsdict[p]))
            g.add((LKG[f1_id], ORDERLABEL, Literal(make_autoinc_id("F1").split("_")[-1], datatype=XSD.float)))
            g.add((LKG[f1_id], LRMOO.R3_is_realised_in, LKG[f2_id]))
            g.add((LKG[f2_id], LRMOO.R3i_realises, LKG[f1_id]))
            g.add((LKG[f28_id], LRMOO.R19_created_a_realisation_of, LKG[f1_id]))
            g.add((LKG[f1_id], LRMOO.R19i_was_realised_through, LKG[f28_id]))
            g.add((LKG[f27_id], RDF.type, LRMOO.F27_Work_Creation))
            g.add((LKG[f27_id], RDFS.label, Literal(f27_label)))
            g.add((LKG[f27_id], LRMOO.R16_created, LKG[f1_id]))
            g.add((LKG[f1_id], LRMOO.R16i_was_created_by, LKG[f27_id]))
            for p, v in graph.predicate_objects(LKG[f28_id]):
                if p in authorprops:
                    g.add((LKG[f27_id], p, v))
            derivatives = list(graph.subjects(derivpath, exp, unique=True))
            for d in derivatives:
                g.add((LKG[f1_id], LRMOO.R3_is_realised_in, d))
                g.add((d, LRMOO.R3i_realises, LKG[f1_id]))
                d_f28 = graph.value(d, LRMOO.R17i_was_created_by)
                g.add((d_f28, LRMOO.R19_created_a_realisation_of, LKG[f1_id]))
                g.add((LKG[f1_id], LRMOO.R19i_was_realised_through, d_f28))
    return g
    # parentpath = (LRMOO.R3_is_realised_in/LRMOO.R5i_is_component_of/LRMOO.R3i_realises)
    # for work in graph.subjects(RDF.type, LRMOO.F1_Work):
    #     for p in graph.objects(work, parentpath, unique=True):
    #         graph.add((work, LRMOO.R67i_forms_part_of, p))
    #         graph.add((p, LRMOO.R67_has_part, work))
            # TODO: find better way to mirror F2 hierarchy. This method
            # adds components of derivatives as children of original
            # Work, which is wrong. Also consider: should derivatives
            # of Expression realise the same Work or a derivative Work? 


def propagate_through_prop(
    graph: Graph,
    src_node: URIRef,
    hierarchy_prop: URIRef,
    predicate: URIRef,
    object: URIRef,
    neighbor_prop: URIRef = None,
):
    linked = list(graph.objects(subject=src_node, predicate=hierarchy_prop))
    while linked:
        node = linked.pop()
        obj = node
        if neighbor_prop:
            obj = graph.value(node, neighbor_prop)
        if (obj, predicate, object) in graph:
            continue
        graph.add((obj, predicate, object))
        propagate_through_prop(graph, node, hierarchy_prop, predicate, object, neighbor_prop)


def get_title(graph: Graph, node: URIRef) -> str | None:
    title_ent = graph.value(node, CIDOC.P102_has_title)
    title = graph.value(title_ent, CIDOC.P190_has_symbolic_content)
    return title.value if title else None


def make_base_graph() -> Graph:
    graph = Graph()
    graph.bind("rdf", RDF)
    graph.bind("rdfs", RDFS)
    graph.bind("crm", CIDOC)
    graph.bind("lrm", LRMOO)
    graph.bind("gn", GN)
    graph.bind("wd", WD)
    graph.bind("lkg", LKG)
    return graph


def gather_up_derivatives(graph: Graph) -> Graph:
    """Produce triples to add from propagating derivative relations up the
    component tree."""
    resultGraph = make_base_graph()
    for s in graph.subjects(LRMOO.R5_has_component):
        if not graph.value(s, LRMOO.R5i_is_component_of):
            _gather_up_derivatives(graph, s, resultGraph)
    return resultGraph


def _gather_up_derivatives(graph: Graph, sender_node: URIRef, resultGraph: Graph) -> list:
    derivrels = [
        LRMOO.R76_is_derivative_of,
        LKG.S761_is_translation_of,
        LKG.S762_is_altered_form_of,
        LKG.S763_is_reduced_form_of,
        LKG.S764_is_extended_form_of
    ]
    children = list(graph.objects(sender_node, LRMOO.R5_has_component))
    for child in children:
        child_relations = _gather_up_derivatives(graph, child, resultGraph)
        for crel in child_relations:
            # If referenced F2 has parent, use parent, else use the F2.
            obj = graph.value(crel[2], LRMOO.R5i_is_component_of, None)
            if obj is None:
                obj = crel[2]
            resultGraph.add((sender_node, crel[1], obj))
    relations = [list(graph.triples((sender_node, drel, None))) for drel in derivrels]
    relations = [rel for rellist in relations for rel in rellist]
    return relations


def gather_down_derivatives(graph: Graph):
    resultGraph = make_base_graph()
    derivrels = [
        LRMOO.R76_is_derivative_of,
        LKG.S761_is_translation_of,
        LKG.S762_is_altered_form_of,
        LKG.S763_is_reduced_form_of,
        LKG.S764_is_extended_form_of
    ]
    for drel in derivrels:
        for s, o in graph.subject_objects(drel, unique=True):
            children = graph.objects(s, LRMOO.R5_has_component*OneOrMore, unique=True)
            for c in children:
                resultGraph.add((c, drel, o))
                resultGraph.add((c, LKG.S763_is_reduced_form_of, o))
    return resultGraph


def infer_derivatives(graph: Graph):
    """If Expression A has n components, and Expression B also has n
    components, and every component of A is derivative of a component of
    B, make A derivative of B. Include subproperties. If all properties
    are the same type, make new property the same type, else use R76.
    Works recursively."""
    for s in graph.subjects(LRMOO.R5_has_component):
        if not graph.value(s, LRMOO.R5i_is_component_of):
            _infer_derivative(graph, s)


def _infer_derivative(graph: Graph, sender_node: URIRef) -> bool:
    derivoptions = (
        LRMOO.R76_is_derivative_of
        | LKG.S761_is_translation_of
        | LKG.S762_is_altered_form_of
        | LKG.S763_is_reduced_form_of
        | LKG.S764_is_extended_form_of
    )
    outputprops = set()
    outputobjs = set()
    children = list(graph.objects(sender_node, LRMOO.R5_has_component))
    if children:
        derivinfo = [_infer_derivative(graph, child) for child in children]
        if all([di is not None for di in derivinfo]) and len(set([di[1] for di in derivinfo])) == 1:
            outputprops = set.intersection(*[di[0] for di in derivinfo])
            ref = graph.value(derivinfo[0][1], LRMOO.R5i_is_component_of)
            if ref:
                for p in sorted(outputprops):
                    graph.add((sender_node, p, ref))
                return (outputprops, ref)
            else:
                return None
        else:
            return None
    else:
        outputobjs = set(graph.objects(sender_node, derivoptions, unique=True))
        if len(outputobjs) == 1:
            refnode = outputobjs.pop()
            outputprops = set(graph.predicates(sender_node, refnode, unique=True))
            return (outputprops, refnode)
        else:
            return None


def build_monographs(graph: Graph, data: list[dict[str, str|list[str]]], languages: pd.DataFrame) -> Graph:
    g = make_base_graph()
    language_map = languages.dropna(subset=["iso639-1"]).set_index("iso639-1")
    for index, item in enumerate(data):
        f1_id = "F1_" + item["yid"]
        title = item["title"]
        lang = language_map["uri"].get(item["lang"])
        f1_base_label = title + f' (YID: {item["yid"]})'
        f1_label = "F1 " + f1_base_label
        f27_id = f1_id.replace("F1_", "F27_", 1)
        f27_label = f1_label.replace("F1", "F27", 1)
        g.add((LKG[f1_id], RDF.type, LRMOO.F1_Work))
        g.add((LKG[f1_id], RDFS.label, Literal(f1_label)))
        g.add((LKG[f1_id], CIDOC.P72_has_language, LKG[lang]))
        g.add((LKG[f1_id], UILABEL, Literal(title)))
        g.add((LKG[f1_id], SEARCHLABEL, Literal(title)))
        g.add((LKG[f1_id], ORDERLABEL, Literal(make_autoinc_id("F1").split("_")[-1], datatype=XSD.float)))
        g.add((LKG[f27_id], RDF.type, LRMOO.F27_Work_Creation))
        g.add((LKG[f27_id], RDFS.label, Literal(f27_label)))
        g.add((LKG[f27_id], LKG.S142_written_by, LKG["E21_P0"]))
        g.add((LKG[f27_id], LRMOO.R16_created, LKG[f1_id]))
        g.add((LKG[f1_id], LRMOO.R16i_was_created_by, LKG[f27_id]))
        add_appellation(g, f1_id, title, appel_label=f1_base_label, appel_class=CIDOC.E35_Title, has_language=lang)
        
        for edition in [item["originals"]] + item["derivatives"]:
            vol_ids = ["F2_" + i for i in edition]
            volcreation_ids = ["F28_" + i for i in edition]
            f2_id = None
            f28_id = None
            # For a singular book edition, just need IDs.
            if len(edition) == 1:
                f2_id = vol_ids[0]
                f28_id = volcreation_ids[0]
            # For multi-volume editions, insert umbrella F2 between F1 and F2s.
            else:
                edition_yid = "u_" + "_".join(edition)
                f2_id = "F2_" + edition_yid
                f28_id = "F28_" + edition_yid
                f2_titles = []
                f2_lang = graph.value(LKG[vol_ids[0]], CIDOC.P72_has_language, None)
                f2_order = float(graph.value(LKG[vol_ids[0]], ORDERLABEL, None)) - 0.5
                for vol_id, volcreation_id in zip(vol_ids, volcreation_ids):
                    f2_titles.append(graph.value(LKG[vol_id], CIDOC.P102_has_title/CIDOC.P190_has_symbolic_content, None))
                    for authorship, person in graph.predicate_objects(LKG[volcreation_id]):
                        if (authorship, RDFS.subPropertyOf, CIDOC.P14_carried_out_by) in graph:
                            g.add((LKG[f28_id], authorship, person))
                    g.add((LKG[f2_id], LRMOO.R5_has_component, LKG[vol_id]))
                    g.add((LKG[vol_id], LRMOO.R5i_is_component_of, LKG[f2_id]))
                f2_title = ", ".join(f2_titles)
                f2_base_label = f'{f2_title} (YID: {edition_yid})'
                labels = [f'{pre} {f2_base_label}' for pre in ["F2", "F28"]]
                g.add((LKG[f2_id], RDF.type, LRMOO.F2_Expression))
                g.add((LKG[f2_id], RDFS.label, Literal(labels[0])))
                g.add((LKG[f2_id], CIDOC.P72_has_language, f2_lang))
                g.add((LKG[f2_id], UILABEL, Literal(f2_title)))
                g.add((LKG[f2_id], SEARCHLABEL, Literal(f2_title)))
                g.add((LKG[f2_id], ORDERLABEL, Literal(f2_order, datatype=XSD.float)))
                g.add((LKG[f28_id], RDF.type, LRMOO.F28_Expression_Creation))
                g.add((LKG[f28_id], RDFS.label, Literal(labels[1])))
                g.add((LKG[f2_id], LRMOO.R17i_was_created_by, LKG[f28_id]))
                g.add((LKG[f28_id], LRMOO.R17_created, LKG[f2_id]))
                add_appellation(g, f2_id, f2_title, appel_label=f2_base_label, appel_class=CIDOC.E35_Title, has_language=f2_lang)
                add_appellation(g, f2_id, edition_yid, appel_label=f2_base_label, appel_class=CIDOC.E42_Identifier, has_types=["E55_YID"], refgraph=graph)
            # Finally, connect F1 with main F2.
            g.add((LKG[f1_id], LRMOO.R3_is_realised_in, LKG[f2_id]))
            g.add((LKG[f2_id], LRMOO.R3i_realises, LKG[f1_id]))
            g.add((LKG[f28_id], LRMOO.R19_created_a_realisation_of, LKG[f1_id]))
            g.add((LKG[f1_id], LRMOO.R19i_was_realised_through, LKG[f28_id]))
    return g


def build_detector(langs: list[str]) -> LanguageDetector:
    lang_detector = LanguageDetectorBuilder.from_iso_codes_639_1(
        *[IsoCode639_1.from_str(lang) for lang in langs]
    ).build()
    return lang_detector


def remove_tempflags(graph: Graph):
    for s in graph.triples((None, LKG["SKIP"], None)):
        graph.remove(s)


def build_graph(
    lkg_onto_path: Path | str,
    graph_path: Path | str,
    languages: pd.DataFrame,
    lang_detector: LanguageDetector | None,
    types: pd.DataFrame,
    places: pd.DataFrame,
    people: pd.DataFrame,
    publishers: pd.DataFrame,
    issues: pd.DataFrame,
    nf: dict[str, pd.DataFrame],
    prefix_nf: str,
    authorships: pd.DataFrame,
    monographs: list[dict[str, str|list[str]]]
) -> Graph:
    graph = make_base_graph()
    graph.parse(lkg_onto_path)

    add_types(graph, types)
    add_langs(graph, languages)
    add_places(graph, places)
    add_people(graph, people, languages, lang_detector)
    add_publishers(graph, publishers, lang_detector)

    add_issues(graph, issues, publishers, lang_detector)
    for lang, nonfic in nf.items():
        add_nonfic(graph, nonfic, lang, issues, publishers, prefix_nf, languages)
    add_authorships(graph, authorships)

    infer_derivatives(graph)

    # gu = gather_up_derivatives(graph)
    # gu.serialize("output/compare/derivatives_up.ttl")
    # gd = gather_down_derivatives(graph)
    # gd.serialize("output/compare/derivatives_down.ttl")
    # graph += gu + gd

    gm = build_monographs(graph, monographs, languages)
    gm.serialize("output/compare/monographs.ttl")
    graph += gm

    gw = infer_works(graph)
    gw.serialize("output/compare/works_inferred.ttl")
    graph += gw

    remove_tempflags(graph)

    graph.serialize(graph_path)
    return graph
