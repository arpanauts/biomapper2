import logging

from biomapper2.config import PROJECT_ROOT
from biomapper2.mapper import Mapper

name = "name_col"
ids = "id_cols"
delimiters = "delimiters"

datasets = {
    "arivale_metabolites": {name: "CHEMICAL_NAME", ids: ["CAS", "KEGG", "HMDB", "PUBCHEM", "INCHIKEY", "SMILES"]},
    "arivale_proteins": {name: "gene_name", ids: ["uniprot", "gene_id"]},
    "ukbb_proteins": {name: "Assay", ids: ["UniProt"], delimiters: ["_"]},
}

datasets_dir = PROJECT_ROOT / "data" / "milestone"


mapper = Mapper()

for dataset_shortname, params in datasets.items():
    logging.info(f"On dataset {dataset_shortname}")
    entity_type = dataset_shortname.split("_")[1]
    tsv_path = datasets_dir / f"{dataset_shortname}.tsv"
    # TODO: make 'output_prefix' work for input paths as well, specify that? (vs. having to use certain file names) #45

    mapper.map_dataset_to_kg(
        dataset=tsv_path,
        entity_type=entity_type,
        name_column=params[name],
        provided_id_columns=params[ids],
        array_delimiters=params.get(delimiters),
        annotation_mode="all",
    )
