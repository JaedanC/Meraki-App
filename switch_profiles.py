from enum import Enum

class p(Enum):
    Gap = 0
    RJ45_Gap = 1
    RJ45 = 2
    SFP = 3
    STACK = 4


_default_8 = [
    8*[p.RJ45] + [p.Gap] + 2*[p.SFP]
]
_default_24 = [
    12*[p.RJ45],
    12*[p.RJ45] + [p.Gap] + 4*[p.SFP] + [p.Gap] + 2*[p.STACK],
]
_default_48 = [
    24*[p.RJ45],
    24*[p.RJ45] + [p.Gap] + 4*[p.SFP] + [p.Gap] + 2*[p.STACK],
]

profiles = {
    # "C9200L-24P-4Xe": _default_24, # Testing that this works
    "default_8": _default_8,
    "default_24": _default_24,
    "default_48": _default_48,
    "MS120-8FP": _default_8,
    "MS120-48FP": [
        24*[p.RJ45] + [p.Gap] + 2*[p.SFP],
        24*[p.RJ45] + [p.Gap] + 2*[p.SFP],
    ],
    "MS125-24P": [
        12*[p.RJ45] + [p.Gap] + 2*[p.SFP],
        12*[p.RJ45] + [p.Gap] + 2*[p.SFP],
    ],
    "MS125-48FP": [
        24*[p.RJ45] + [p.Gap] + 2*[p.SFP],
        24*[p.RJ45] + [p.Gap] + 2*[p.SFP],
    ],
    "MS130R-8P": [
        4*[p.RJ45] + [p.Gap] + [p.SFP],
        4*[p.RJ45] + [p.Gap] + [p.SFP],
    ],
    "MS210-24P":  _default_24,
    "MS210-48FP": _default_48,
    "MS220-8P": [
        8*[p.RJ45_Gap]                  + [p.Gap] + [(8, p.SFP)],
        [(i, p.RJ45) for i in range(8)] + [p.Gap] + [(9, p.SFP)],
    ],
    "MS220-24P": [
        12*[p.RJ45],
        12*[p.RJ45] + [p.Gap] + [(20 + i, p.SFP) for i in range(4)],
    ],
    "MS225-48FP": _default_48,
    "MS250-24P":  _default_24,
    "MS250-48FP": _default_48,
    "MS410-16": [
        8*[p.SFP],
        8*[p.SFP] + [p.Gap] + 2*[p.SFP] + [p.Gap] + 2*[p.STACK],
    ],
    "MS425-32": [
        16*[p.SFP],
        16*[p.SFP] + [p.Gap] + 2*[p.STACK], # TODO: QSFP?
    ],
}


def get_switch_profile(model: str, n_ports: int):
    if model in profiles:
        return profiles[model]

    # Try to guess a default
    n_rj45_ports = n_ports - n_ports % 8
    n_sfp_ports = ((n_ports - n_rj45_ports) // 4) * 4
    n_stack_ports = n_ports - n_rj45_ports - n_sfp_ports

    if n_rj45_ports == 24 and n_sfp_ports == 4 and n_stack_ports == 2:
        return profiles["default_24"]
    if n_rj45_ports == 48 and n_sfp_ports == 4 and n_stack_ports == 2:
        return profiles["default_48"]
    if n_rj45_ports == 8 and n_sfp_ports == 2 and n_stack_ports == 0:
        return profiles["default_8"]

    # Try to calculate the profile
    has_gap = int(n_sfp_ports > 0 or n_stack_ports > 0)
    return [
        (n_ports // 2) * [p.RJ45],
        (n_ports // 2) * [p.RJ45] + has_gap * [p.Gap] + n_sfp_ports * [p.SFP] + n_stack_ports * [p.STACK],
    ]

def get_port_count(profile: list, port_type: p):
    count = 0
    for row in profile:
        for port in row:
            if isinstance(port, tuple):
                port = port[1]
            if port is port_type:
                count += 1
    return count