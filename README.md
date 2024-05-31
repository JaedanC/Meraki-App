# Meraki App

## Installing

Download this repository with:

```bash
git clone https://github.com/JaedanC/Meraki-App.git --recursive
```

Install pygui. Download the latest release from [https://github.com/JaedanC/pygui/releases](JaedanC/pygui) and extract:

- 📁 `pygui`
- 📃 `pygui_demo.py`

Then run

```bash
python -m venv venv
./venv/scripts/activate
pip install -r requirements.txt
```

## Running

You must supply a Meraki API Key with `-k` or `-kf`.

Example:

```bash
./venv/scripts/activate
python app.py -kf meraki_api_key.txt
```

## Creating an exe

To compile this tool into an exe, run `setup.py`. The resulting .exe will be inside the `dist` directory.

## Interesting Filters

Show VLANs outside the typical spec

```txt
vlan!None|1|10|20|30|40|80|250|254|100|101|200|201|300|800|900|911|990|999
```
