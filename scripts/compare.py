"""
Compare old graph and new graph. For debugging.
"""

from rdflib import Graph
from rdflib.compare import to_isomorphic, graph_diff
from namespaces import *
from graphutils import make_base_graph

a = Graph()
a.parse("output/compare/lkg_yaz2-old.ttl")

b = Graph()
b.parse("output/lkg_yaz2.ttl")

aiso = to_isomorphic(a)
biso = to_isomorphic(b)

diff = graph_diff(aiso, biso)

bg = make_base_graph()
graphs = [bg + dg for dg in diff]

graphs[0].serialize("output/compare/in_both.ttl", format="turtle")
graphs[1].serialize("output/compare/in_a.ttl", format="turtle")
graphs[2].serialize("output/compare/in_b.ttl", format="turtle")
