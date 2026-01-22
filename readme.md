# User Manual

The Yaznevich database extractor processes data from the source Excel database *Lem Non Fiction* into an RDF graph based on the CIDOC CRM and LRMOO ontologies, plus the project's internal ontology, LKG.core. The data is processed using the `pandas` library and regular expressions. From the processed data, a graph is built using the `rdflib` library. The graph is constructed according to the mapping shown in the *Excel WJ to RDF* diagrams in `diagrams/LKG.core diagrams.drawio`.

With a ready environment and the source data files, a single run of the program should take a couple of minutes.

We also present an excerpt of the Yaznevich file for the reader to understand the challenges in processing this file and creating the graph:

`Excerpt_yaznevich_file`: an excerpt from the full Yaznevich database and includes only information on editions and translations of Lem’s 1957 long essay Dialogues; the excerpt illustrates the structure of the main file.

## 1. Installation and Running

1. Make sure you have Python 3.12. The project was developed on version 3.12.10.

    ```ps1
    python --version
    ```

2. The working directory for the instructions below is `scripts/`. In this directory, create a virtual environment.

    ```ps1
    python -m venv .venv
    ```

    Then activate it:

    ```ps1
    # PowerShell
    & .venv\Scripts\Activate.ps1
    ```

3. Install the packages.

    ```ps1
    pip install -r requirements.txt
    ```

4. Make sure the `data/` directory contains the current database `Lem Non Fiction BPK-25o_LKG_v2.4.xlsx`, the required auxiliary files `types.xlsx`, `langs.xlsx`, and `cities.xlsx`, and optionally the Geonames data cache `geocache.json`.

5. The environment is ready. To generate the graph, run:

    ```ps1
    cd scripts
    python main.py
    ```

    It will be saved as `output/lkg_yaz.ttl`.

## 2. Auxiliary Data

In the `data/` directory there should be the following files, where you can place additional/required data missing from the database:

- **types.xlsx** — types, instances of `E55 Type`.
- **langs.xlsx** — languages, instances of `E56 Language`. The `langs` sheet contains ISO 639-1 codes and labels. The `errors` sheet maps a code spelling from the left column to the code in the right column—for cases where you want to override the code in the database with another specific code (errors, inconsistencies).
- **cities.xlsx** — places, instances of `E53 Place`, together with their corresponding Geoname IDs. They must be written exactly as they appear in the database. If in the database a place is a list `"{City1}, {City2}"`, then the first column must contain exactly that string, and the second column must contain the list of the corresponding Geoname IDs separated by a space — `"{GeonameID1} {GeonameID2}"`. The third column may contain the name of the first publisher associated with that place and serves only as context when completing Geoname IDs.
  - With a new version of the database, new places will likely appear. During script execution, a message will be displayed that N publishers do not have cities in `cities.xlsx`. A file `cities_new.xlsx` will be generated containing those publishers and the missing places associated with them. In a dozen or so cases these are non-places or misinterpreted data and should be ignored. However, entries that truly are places must be added to `cities.xlsx`, and then their Geoname IDs must be found and filled in.
- **geocache.json** — a saved record of responses from the Geonames API with supplementary data for the places in `cities.xlsx`, such as the city and country name in English. If you change `cities.xlsx`, you need to regenerate this file. In `config.py`, set **FETCH_GEONAME_INFO** to `True`, and in the `.env` file in the working directory assign your Geonames username to **GEONAMES_KEY**. After a one-time run of the extractor, `geocache.json` should appear; then set the changed values back.

## 3. Additional Configuration

The file `config.py` contains additional configuration options:

- **FETCH_GEONAME_INFO** — if `True`, the extractor will fetch data from Geonames and save it to `geocache.json`.
- **AUTODETECT_LANG** — if `True`, the extractor will use the `lingua-py` library to automatically determine the language for first/last names/names that do not have language information. When the library cannot determine the language, it leaves the name without language information.
- **AUTODETECT_LANG_LIST** — a list of ISO 639-1 language codes to detect. `lingua-py` must support the language.
- **\*_DIR**, **\*_PATH** — paths to directories and files used by the extractor.
- **\*_PREFIX** — prefixes added by the extractor to `YID` (the index in the database) to distinguish indices by source sheets.
- **\*_SHEETNAME** — the name of a specific sheet.
- **\*_COLMAP** — a map of column names to names that are easier to work with. With a new version of the database, you will need to paste the current names as keys.
- **\*_ROWS** — a `slice` object specifying the range of rows in the sheet to consider. `None` means no limit. Necessary when the extractor incorrectly considers working rows that look similar to the relevant ones.
- **NF_SHEETLIST** — a list of Non-Fiction sheets suitable for processing.
- **NF_COLS** — a list of column names for Non-Fiction sheets. Sheets have the same column order, so a separate map is not needed for each sheet.
- **NF_STARTCOL** — a default dict that specifies for each Non-Fiction sheet the starting column number for the **NF_COLS** sequence.
- **NF_ENDROW** — a default dict that specifies for each Non-Fiction sheet the row number where relevant data ends.
- **NF_PAGEMARKS** — a list of all symbols/notations that mark pages in Non-Fiction sheets. This makes it possible to construct a regular expression that extracts the journal issue number from the combined column "year, issue, page".
- **NF_ISSUE_PATTERNS** — a default dict that, if needed, allows you to specify an alternative regular expression for selected Non-Fiction sheets to extract the issue number.

---


