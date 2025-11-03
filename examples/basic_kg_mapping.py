import json

from biomapper2.kg_mapper import map_to_kg

# Define an entity with a name and local identifier
entity = {
    'name': 'carnitine',
    'kegg.compound': 'C00487'
}

# Run through the full KG mapping pipeline
mapped_entity = map_to_kg(entity)

# Print original and final mapped entity
print(f"\nOriginal entity:")
print(json.dumps(entity, indent=2))
print(f"\nMapped entity:")
print(json.dumps(mapped_entity, indent=2))
