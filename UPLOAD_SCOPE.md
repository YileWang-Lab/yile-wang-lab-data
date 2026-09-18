# Upload scope

The organization repository should contain `data_processed/`, `data_raw/`, `metadata/`, `scripts/`, `docs/`, `examples/`, and `code_sources/`.

`source_snapshots/` is retained locally for provenance but should not be uploaded as a whole: it contains duplicate raw files, large workbooks, and files whose redistribution permissions require separate verification. The normalized outputs preserve source paths, SHA-256 prefixes, original Chinese headers, English standardized headers, and field dictionaries.

Before publication, review `metadata/file_inventory_bilingual.csv` for license status and remove any restricted dataset.
