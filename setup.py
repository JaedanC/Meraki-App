import os
from py2exe import freeze
from typing import List, Tuple


# Function to collect additional files required by the script
def collect_files(root_folder) -> List[Tuple[str, List[str]]]:
    files = []
    for base, _, filenames in os.walk(root_folder):
        for filename in filenames:
            files.append((base, os.path.join(base, filename)))
    
    files_consolidated = {}
    for folder, file in files:
        if folder not in files_consolidated:
            files_consolidated[folder] = []
        
        files_consolidated[folder].append(file)
    
    freeze_format = []
    for folder, files in files_consolidated.items():
        freeze_format.append((folder, files))
    return freeze_format


# Define the script and its dependencies
additional_files_folder = 'pygui'
additional_files = collect_files(additional_files_folder)

additional_files.append((".", ["./meraki_api_key_jaedan.txt"]))

for destination_folder, src_files in additional_files:
    for src_file in src_files:
        print("Copying to {} \t->\t {}".format(destination_folder, src_file))

freeze(
    console=[{"script": 'app.py'}],
    data_files=additional_files,
    options={
        "bundle_files": 1
    }
)
