import re
import itertools
from html.parser import HTMLParser

from config import *


def verify_lang(lang: str, langmap: dict[str, str | None]) -> str:
    """Verify that lang is a key in langmap and return its value. Else
    instruct user on required action.
    
    Raises:
        KeyError: If lang not in langmap.
    """
    if lang not in langmap.keys():
        raise KeyError(f"Language code {lang} not in langmap. Add code to {PATH_EXTR_LANG}")
    lang = langmap[lang]
    return lang

def make_namedict(person_names: list[str], langmap: dict[str, str | None]) -> dict[str, list[list[str]]]:
    """Transform list of different forms of a person's name into a
    structure appropriate for E41 Appellations:

        {
            "<Language code XY>": [
                ["<Name 1>", "<Name 1, alt. form (e.g. spelling)>"],
                ["<Name 2>"]
            ],
            "<Language code YZ>": [...],
            ...
        }

    During graph creation, names in every most nested list will be
    interconnected with `P139_has_alternative_form`. Names without
    language labels in parentheses go under "NOLANG" key. They will
    not have a language assigned in graph unless autodetection is on.

    Args:
        person_names (list[str]): List of person's names, optionally
            labeled with ISO 639-1 language codes in parentheses,
            delimited with ",".
        langmap (dict[str, str | None]): A mapping of language codes
            as they appear in main excel to standardized codes.

    Example:

    >>> make_namedict(
    ...     ["John (EN,DE)", "Hans (DE)"],
    ...     {"EN": "EN", "DE": "DE"}
    ... )
    {'NOLANG': [], 'EN': [['John']], 'DE': [['John'], ['Hans']]}
    """
    result = {}
    result["NOLANG"] = []
    if not person_names:
        return result
    for y in person_names:
        split = re.split(r" \(", y)
        alias = split[0]
        # result[alias] = []
        langs = []
        if len(split) > 1:
            langs = re.split(r",", split[1].rstrip(")"))
        for l in langs:
            l = verify_lang(l, langmap)
            if l in result.keys():
                result[l].append([alias])
            else:
                result[l] = [[alias]]
        if not langs:
            result["NOLANG"].append([alias])
    return result

def expand_range(src: str) -> list[str]:
    """Expand YID range notation into list of explicit YIDs.

    Args:
        src (str): Range to expand.

    Examples:

        >>> expand_range("355.9.1÷9.4")
        ['355.9.1', '355.9.2', '355.9.3', '355.9.4']
    """
    if "÷" not in src:
        return [src]
    bounds = src.split("÷", 1)
    mainid, firstpart = bounds[0].rsplit(".", 1)
    lastpart = bounds[1].rsplit(".", 1)[1]
    ids = [f'{mainid}.{subid}' for subid in range(int(firstpart), int(lastpart)+1)]
    return ids

def normalize_ref(sourceref: str, prefix_default: str, prefix_nf: str, lang_prefixes: list[str], prefix_other: str) -> str:
    """Add explicit prefixes to ID based on parameters. Ranges marked
    with '÷', lists marked with ', ' and lists of chapters marked with
    ';' will be expanded into explicit IDs separated by space. Code
    symbols at the end such as "-", ">", "<", "!" (semantics in main
    excel) are preserved, unless there is a range.
    
    Args:
        sref (str): ID to transform.
        prefix_default (str): Sheet prefix to be used when ref has no
            prefix.
        prefix_nf (str): YID LKG prefix for nonfiction category.
        prefix_other (str): YID LKG prefix for other categories.
        lang_prefixes (list[str]): Language prefixes of nonfiction
            sheets.

    Returns:
        out (str): A string of one or multiple explicit IDs separated by
            space.
    """
    refs = []
    subrefs = sourceref.split(", ")
    for subref in subrefs:
        plus = subref.split("+")
        for sref in plus:
            if sref.strip() == '':
                continue
            if sref[0].isdigit():
                if prefix_default in lang_prefixes:
                    prefix = prefix_nf + prefix_default
                else:
                    prefix = prefix_other + prefix_default
                sref = prefix + sref
            else:
                prefix = re.match(r'[A-Za-z]+', sref).group()
                number = sref[len(prefix):].strip(":")
                if prefix:
                    if prefix not in lang_prefixes:
                        sref = prefix_other + prefix + number
                        continue
                    else:
                        sref = prefix_nf + prefix + number
            parts = sref.split("÷")
            if len(parts) > 1:
                idfirst = parts[0].rsplit(".", 1)
                idlast = parts[-1].rsplit(".", 1)
                lastid = idlast[-1]
                if ";" in lastid:
                    allparts = lastid.split(";")
                    lastid = allparts[0]
                    for p in allparts[1:]:
                        nump = re.match(r"\d+", p)
                        if nump:
                            refs.append(f'{idfirst[0]}.{nump.group()}')
                numf = re.match(r"\d+", idfirst[-1])
                numl = re.match(r"\d+", lastid)
                if numf and numl:
                    f = int(numf.group())
                    l = int(numl.group())
                    refs += [f'{idfirst[0]}.{x}' for x in range(f, l+1)]
            elif ";" in sref:
                mainid, subids = sref.split(".", 1)
                for subid in subids.split(";"):
                    refs.append(f'{mainid}.{subid}')
            else:
                if not sref.endswith("?"):
                    refs.append(sref)
    return " ".join(refs)

def is_same_name(a: str, b: str) -> bool:
    """Return True if two names match up to first dot."""
    anorm = a.upper().strip()
    bnorm = b.upper().strip()
    if anorm == bnorm:
        return True
    if not anorm.endswith(".") ^ bnorm.endswith("."):
        return False
    ini = anorm if anorm.endswith(".") else bnorm
    full = bnorm if anorm.endswith(".") else anorm
    if len(ini) > len(full):
        return False
    return ini[:len(ini)-1] == full[:len(ini)-1]

def expand_brackets_names(x: str) -> list[str]:
    """Transform name with alternatives in brackets into list of all
    possible full names.
    
    - If name in brackets is longer than 2 words and at the end of
      string, it is considered a full name alternative.
    - If name in brackets is a single word before the end of full name,
      it is alternative only to the word before itself.
    """
    # if not isinstance(x, str):
    #     return x
    fullsplit = re.split(r" \((\w+ \w+)\)$", x)
    if fullsplit[-1] == "":
        fullsplit.pop()
    words = re.findall(r"((?:\w+-\w+)|\w+\.? \(.*?\)|\w+\.?)", fullsplit[0])
    words = [re.findall(r"(?:\w+-\w+|\w+\.?)", w) for w in words]
    names = list(itertools.product(*words))
    names = [" ".join(name) for name in names]
    
    if fullsplit[-1] != fullsplit[0]:
        names.append(fullsplit[-1])
    return names

def cutout_issue_number(source: str, patterns: tuple[re.Pattern]) -> str:
    """Cut out parts of string around issue number instead of trying to
    extract it itself, as parts around are more consistent. This
    approach allows for including notations that are otherwise hard to
    extract explicitly."""
    year = re.search(patterns[0], source)
    if not year:
        return ""
    start = year.span(0)[1]
    if len(source) <= start:
        return ""
    rest = source[start:]
    spl = re.split(patterns[1], rest, 1)
    result = spl[0].strip().strip(".")
    op = result.count("(")
    cl = result.count(")")
    missing = op - cl
    if missing > 0:
        result += ")" * missing
    return result

class __StripHTML(HTMLParser):
    text = ""
    def plainify(self, data):
        self.text = ""
        self.feed(data)
        result = self.text
        self.text = ""
        return result
    def handle_data(self, data):
        self.text += data

__striphtml = __StripHTML()

def striphtml(data):
    """Remove HTML tags and unescape text."""
    return __striphtml.plainify(data)

