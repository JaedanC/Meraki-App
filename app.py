import argparse
import sys
import pygui_app


def main():
    parser = argparse.ArgumentParser(
        prog="python " + sys.argv[0],
        description="Interactive Meraki API App"
    )
    meraki_key_or_file = parser.add_mutually_exclusive_group(required=True)
    meraki_key_or_file.add_argument(
        "-k",
        action="store",
        dest="meraki_key",
        help="The meraki api key to use",
    )
    meraki_key_or_file.add_argument(
        "-kf",
        action="store",
        dest="meraki_key_file",
        help="The file to load the meraki api key from"
    )
    args = parser.parse_args()

    meraki_key = args.meraki_key
    if args.meraki_key_file is not None:
        with open(args.meraki_key_file) as f:
            meraki_key = f.read()
    
    pygui_app.main(meraki_key)


if __name__ == "__main__":
    main()
