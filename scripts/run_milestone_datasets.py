import logging

from biomapper2.config import PROJECT_ROOT
from biomapper2.mapper import Mapper
from biomapper2.utils import AnnotationMode
from biomapper2.visualizer import Visualizer

name = "name_col"
ids = "id_cols"
vocab = "vocab"
delimiters = "delimiters"

datasets = {
    "arivale_proteins": {name: "gene_name", ids: ["uniprot", "gene_id"]},
    "arivale_labs": {name: "Display Name", ids: ["Labcorp LOINC ID", "Quest LOINC ID"]},
    "arivale_metabolites": {
        name: "CHEMICAL_NAME",
        ids: ["CAS", "KEGG", "HMDB", "PUBCHEM", "INCHIKEY", "SMILES"],
        vocab: "refmet",
    },
    "arivale_lipids": {name: "CHEMICAL_NAME", ids: ["HMDB", "KEGG"], vocab: "HMDB"},
    "ukbb_proteins": {name: "Assay", ids: ["UniProt"], delimiters: ["_"]},
    "ukbb_labs": {name: "field_name", ids: []},
    "ukbb_metabolites": {
        name: "nightingale_name",
        ids: ["source_chebi_id", "source_hmdb_id", "source_pubchem_id"],
        vocab: "refmet",
    },
    "hpp_proteins": {name: "nightingale_name", ids: []},
}

datasets_dir = PROJECT_ROOT / "data" / "milestone"


mapper = Mapper()
mode: AnnotationMode = "all"
results_dir = datasets_dir / "results"

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
        vocab=params.get(vocab),
        annotation_mode=mode,
        output_dir=results_dir,
    )


viz = Visualizer()
viz_dir = results_dir / "viz"

stats_df = viz.aggregate_stats(stats_dir=results_dir)
suffix = f"- KRAKEN (mode={mode})"

viz.render_heatmap(df=stats_df, output_path=viz_dir / f"heatmap_{mode}", title=f"Mapping Summary {suffix}")

viz.render_breakdown(df=stats_df, output_path=viz_dir / f"breakdown_{mode}", title=f"Mapping Breakdown {suffix}")
