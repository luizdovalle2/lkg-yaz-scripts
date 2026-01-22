from rdflib.namespace import DefinedNamespace, Namespace
from rdflib.term import URIRef


class LKG(DefinedNamespace):
    """
    Generated from: ./data/onto/LKG_ontology_0_1.rdf
    Date: 2025-11-18 11:24:44.449972+00:00
    """

    _warn = False

    _NS = Namespace("http://lkg.org.pl/ns/lkg-core/")

    S141_composed_by: URIRef
    S142_written_by: URIRef
    S143_translated_by: URIRef
    S144_edited_by: URIRef
    S145_published_by: URIRef
    S146_performed_by: URIRef
    S147_directed_by: URIRef
    S761_is_translation_of: URIRef
    """This property associates an instance of F2 Expression with another instance of F2 Expression which was written in another language and constitutes the basis for translation, that is, the former instance of F2. This property is not transitive. It is asymmetric and irreflexive."""
    S762_is_altered_form_of: URIRef
    """This property associates an instance of F2 Expression with another instance of F2 Expression. The content of the former is significantly altered form of the content of the latter, that is, modified beyond the scope of regular translating or editing alterations. This property is not transitive. It is asymmetric and irreflexive."""
    S763_is_reduced_form_of: URIRef
    """This property associates an instance of F2 Expression with another instance of F2 Expression. The content of the former is significantly reduced version of the content of the latter. This property is not transitive. It is asymmetric and irreflexive. It does not exclude the occurance of the S762_is_altered_form_of property."""
    S764_is_extended_form_of: URIRef
    """This property associates an instance of F2 Expression with another instance of F2 Expression. The content of the former is an extended version of the content of the later. This property is not transitive. It is asymmetric and irreflexive. It does not exclude the occurance of the S762_is_altered_form_of property."""
