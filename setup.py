import os
from py2exe import freeze
from typing import List, Tuple


def collect_files(root_folder) -> List[Tuple[str, List[str]]]:
    """Returns the files in the root_folder recursively in the freeze format.
    Format:

    ```json
    [
        ("destination_directory", ["files_to_copy_to_directory"])
    ]
    ```

    For example:

    ```json
    [
        ("my_folder", ["my_folder/file1.txt",
                       "my_folder/file2.txt"]),
        ("my_folder/nested", ["my_folder/nested/file3.txt",
                              "my_folder/nested/file4.txt"])
    ]
    ```
    """
    src_files = []
    for base, _, filenames in os.walk(root_folder):
        for filename in filenames:
            src_files.append((base, os.path.join(base, filename)))
    
    # Aggregate in src_files in the same directory to the one 
    # destination_directory
    files_consolidated = {}
    for destination_directory, file in src_files:
        if destination_directory not in files_consolidated:
            files_consolidated[destination_directory] = []
        
        files_consolidated[destination_directory].append(file)
    
    freeze_format = []
    for destination_directory, src_paths in files_consolidated.items():
        freeze_format.append((destination_directory, src_paths))
    return freeze_format


# Make sure to recursively include pygui
additional_files = collect_files("pygui")

# --- Include any other files that need to be copied here ---
additional_files.append((".", ["./meraki_api_key_jaedan.txt"]))


for destination_folder, src_files in additional_files:
    for src_file in src_files:
        print("Copying to {} \t->\t {}".format(destination_folder, src_file))


# Be sure to update the name of the entry script
freeze(
    console=[{
        "script": "app.py",
        "icon_resources": [(1, "icons8-thin-client-96.ico")],
    }],
    data_files=additional_files,
    options={
        "bundle_files": 1
    }
)
