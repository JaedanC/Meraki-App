import json
import csv

from extra.api import dict_diff, dict_to_csv, safe_open_w


def main():
    try:
        with open("cache/getOrganizationSwitchPortsBySwitch - Before.csv", encoding="utf-8") as b,\
            open("cache/getOrganizationSwitchPortsBySwitch.csv",           encoding="utf-8") as c,\
            open("cache/getOrganizationSwitchPortsBySwitch - Desired.csv", encoding="utf-8") as d:
            before_file = csv.DictReader(b)
            current_file = csv.DictReader(c)
            desired_file = csv.DictReader(d)

            before_file_lookup = {c["switch"] + " " + c["portId"]: c for c in before_file}
            desired_file_lookup = {d["switch"] + " " + d["portId"]: d for d in desired_file}

            keep_edits = []
            for current_port_config in current_file:
                key = current_port_config["switch"] + " " + current_port_config["portId"]
                if key not in desired_file_lookup:
                    continue

                before_port_config = before_file_lookup[key]
                desired_port_config = desired_file_lookup[key]
                diff = dict_diff(desired_port_config, before_port_config)
                # print(json.dumps(before_port_config, indent=4))
                # print(json.dumps(desired_port_config, indent=4))
                # print(json.dumps(diff, indent=4))

                for field, current_value in current_port_config.items():
                    if field not in before_port_config:
                        diff.pop(field, None)

                    if field not in desired_port_config:
                        diff.pop(field, None)

                    if before_port_config.get(field) != current_value:
                        diff.pop(field, None)

                if len(diff) == 0:
                    continue

                keep_edits.append({
                        "switch": current_port_config["switch"],
                        "portId": current_port_config["portId"],
                        "name": current_port_config["name"],
                    } | diff)

            with safe_open_w("cache/diff.csv") as f:
                f.write(dict_to_csv(keep_edits))
                print("Created cache/diff.csv")


    except FileNotFoundError as f:
        print(f)
        return

if __name__ == "__main__":
    main()
