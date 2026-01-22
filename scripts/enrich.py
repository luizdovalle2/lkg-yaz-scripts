"""
Enrich graph with reconciled wikidata entities.
"""

import pandas as pd
from rdflib import URIRef

from config import *
from namespaces import *
from graphutils import make_base_graph


print("[Info] Associating wikidata entities.")

graph = make_base_graph()

for childpath in DIR_RECO.iterdir():
    if childpath.suffix != '.tsv':
        continue
    df = pd.read_table(childpath).fillna("")
    for _, row in df.iterrows():
        if row["uri"] and row["idwd"]:
            graph.add((URIRef(row["uri"]), OWL.sameAs, WD[row["idwd"]]))
    print(f'[Info] Linked {len(df[df[["uri", "idwd"]].notna()])} from {childpath}.')


graph.serialize("output/compare/enrichment.ttl")

bg = make_base_graph()
bg.parse(PATH_GRAPH_YAZN)
bg += graph
print("[Info] Saving enriched graph...")
bg.serialize(PATH_GRAPH_YAZN)

print(f"[Info] Success: enriched graph saved as {PATH_GRAPH_YAZN}.")
