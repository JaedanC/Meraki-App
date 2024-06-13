from typing import List, Tuple, Dict, Any, Callable

from .model import Switch, MerakiDevice


SWITCH_FILTER_HELP_TEXT = """
Filtering is done using a key:value system. Some keys target details on the switch
itself, others target ports on the switch.

Inclusive with      :
Exclusive with      !
Spaces are          _
Chain queries with  |

Valid switch filters:
 - model
 - name
 - network
 - site

Valid switch/port filters:
 - allowed
 - id
 - poe
 - rstp
 - stp
 - type
 - vlan
 - voice

E.g. My_switch vlan:100|200 poe:enabled model!MS250-24P
""".strip()


SWITCH_PORT_FILTER_HELP_TEXT = """
Filtering is done using a key:value system.

Inclusive with      :
Exclusive with      !
Spaces are          _
Chain queries with  |

Valid switch port filters:
 - allowed
 - id
 - poe
 - rstp
 - stp
 - type
 - vlan
 - voice
 - name
 - switch
 - enabled


E.g. Data/Voice vlan:100|200 poe:enabled
""".strip()


APPLIANCE_FILTER_HELP_TEXT = """
Filtering is done using a key:value system.

Inclusive with      :
Exclusive with      !
Spaces are          _
Chain queries with  |

Valid switch port filters:
 - mac
 - model
 - name
 - notes
 - serial
 - wan1
 - wan2

E.g. AS01 wan1:200 serial:Q2
""".strip()


def IS_TERM_IN_FIELD(query: str, data_value: str) -> bool:
    query = query.replace("_", " ")
    return query in data_value


def IS_TERM_EQUAL_TO_FIELD(query: str, data_value: str) -> bool:
    return query == data_value


def IS_VLAN_ALLOWED(query: str, data_value: str) -> bool:
    if query.startswith("a") and data_value == "all":
        return True
    
    vlans = data_value.split(",")
    return query in vlans


def tokenise_query_into_dict(
        query: str,
        default="name"
    ) -> Dict[str, Tuple[List[str], bool]]:
    """Returns a dictionary containing the query terms. Eg.

    Waratah poe:true vlan:999|200 voice:100 allowed!990|all

    {
        "name":  (["Waratah"],    True),
        "poe":   (["true"],       True),
        "vlan":  (["999", "200"], True),
        "voice": (["100"],        True),
        "stp":   (["990", "all"], False),
    }

    : Is a normal match
    ! is a negated result
    """
    query = query.lower()
    terms = {}
    for t in query.split(" "):
        if ":" not in t and "!" not in t:
            terms[default] = (t.split("|"), True)
            continue

        if ":" in t:
            t = t.split(":", 1)
            terms[t[0]] = (t[1].split("|"), True)
        elif "!" in t:
            t = t.split("!", 1)
            terms[t[0]] = (t[1].split("|"), False)
    return terms


def should_show(
        query_dict: Dict[str, Tuple[List[str], bool]],
        lookups: List[Tuple[str, Any, Callable[[Any, Any], bool]]],
    ) -> bool:
    """Only returns true if every query term passes the lookup function,
    otherwise returns False.
    """
    for query_term, field, func in lookups:
        if (query_extract := query_dict.get(query_term)) is None:
            continue

        query_values, true_is_pass = query_extract

        field = str(field).lower()
        for query_value in query_values:
            func_result = func(query_value, field)

            if func_result and true_is_pass:
                continue
            elif not func_result and not true_is_pass:
                continue

            return False
    return True


def switch_filter(query: str, switches: List[Switch]) -> List[Switch]:
    """This filter is responsible for filtering switches. Return the switches
    you want to keep from the query string. This function is run whenever the
    query string updates (not every frame) so we can get away with an expensive
    operation.
    """
    terms = tokenise_query_into_dict(query)

    to_keep = []
    for switch in switches:
        lookups = [
            ("model",   switch.model,        IS_TERM_IN_FIELD),
            ("name",    switch.name,         IS_TERM_IN_FIELD),
            ("network", switch.network_name, IS_TERM_IN_FIELD),
            ("site",    switch.network_name, IS_TERM_IN_FIELD),
        ]
        if not should_show(terms, lookups):
            continue

        keep_port = False
        for port in switch.ports:
            lookups = [
                ("allowed", port.allowedVlans, IS_VLAN_ALLOWED),
                ("id",      port.portId,       IS_TERM_EQUAL_TO_FIELD),
                ("poe",     port.poeEnabled,   IS_TERM_IN_FIELD),
                ("rstp",    port.rstpEnabled,  IS_TERM_IN_FIELD),
                ("stp",     port.stpGuard,     IS_TERM_IN_FIELD),
                ("type",    port.type,         IS_TERM_IN_FIELD),
                ("vlan",    port.vlan,         IS_TERM_EQUAL_TO_FIELD),
                ("voice",   port.voiceVlan,    IS_TERM_EQUAL_TO_FIELD),
            ]
            if should_show(terms, lookups):
                keep_port = True
                break

        if keep_port:
            to_keep.append(switch)

    return to_keep


def switch_port_filter(query: str, ports: List[Switch.SwitchPort]) -> List[Switch.SwitchPort]:
    terms = tokenise_query_into_dict(query)
    to_keep = []

    for port in ports:
        lookups = [
            ("allowed", port.allowedVlans, IS_VLAN_ALLOWED),
            ("id",      port.portId,       IS_TERM_EQUAL_TO_FIELD),
            ("poe",     port.poeEnabled,   IS_TERM_IN_FIELD),
            ("rstp",    port.rstpEnabled,  IS_TERM_IN_FIELD),
            ("stp",     port.stpGuard,     IS_TERM_IN_FIELD),
            ("type",    port.type,         IS_TERM_IN_FIELD),
            ("vlan",    port.vlan,         IS_TERM_EQUAL_TO_FIELD),
            ("voice",   port.voiceVlan,    IS_TERM_EQUAL_TO_FIELD),
            ("name",    port.name,         IS_TERM_IN_FIELD),
            ("switch",  port.switch_name,  IS_TERM_IN_FIELD),
            ("enabled", port.enabled,      IS_TERM_IN_FIELD),
        ]

        if should_show(terms, lookups):
            to_keep.append(port)

    return to_keep


def appliance_filter(query, appliances: List[MerakiDevice]) -> List[MerakiDevice]:
    """This filter is responsible for filtering switches. Return the switches
    you want to keep from the query string. This function is run whenever the
    query string updates (not every frame) so we can get away with an expensive
    operation.
    """
    terms = tokenise_query_into_dict(query)

    to_keep = []
    for appliance in appliances:
        lookups = [
            ("mac",     appliance.mac,     IS_TERM_IN_FIELD),
            ("model",   appliance.model,   IS_TERM_IN_FIELD),
            ("name",    appliance.name,    IS_TERM_IN_FIELD),
            ("notes",   appliance.notes,   IS_TERM_IN_FIELD),
            ("serial",  appliance.serial,  IS_TERM_IN_FIELD),
            ("wan1",    appliance.wan1_ip, IS_TERM_IN_FIELD),
            ("wan2",    appliance.wan2_ip, IS_TERM_IN_FIELD),
        ]
        if should_show(terms, lookups):
            to_keep.append(appliance)

    return to_keep
