# Meraki App

## Running

Optional, use python virtual env.

```bash
python -m venv venv
./venv/Scripts/activate
```

Install dependencies

```bash
pip install -r requirements
```

Run `app.py`

```bash
python app.py
```

## Compiling to exe

```bash
python setup.py
```

Compiles to `dist`

## Interesting Filters

Show VLANs outside the typical spec

```txt
vlan!None|1|10|20|30|40|80|250|254|100|101|200|201|300|800|900|911|990|999
```
