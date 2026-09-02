from typing import List, override

import pygui_cython as pygui

from .table import Table, Field
from .colour import Colour
from ..pygui_ext import text_widget, Sortable
from ..filtering import IS_TERM_IN_FIELD, IS_TAG_ON_DEVICE, IS_VLAN_ALLOWED
from ..model import Switch


class SwitchportsTable(Table):
    def __init__(self, table_name: str, switch_ports: List[Switch.SwitchPort]):
        spec = [
            preview          := Field(IS_TERM_IN_FIELD, str,        "Preview",            "preview"),
            switch           := Field(IS_TERM_IN_FIELD, str,        "Switch",             "switch"),
            portId           := Field(IS_TERM_IN_FIELD, [int, str], "Port Id",            "portId"),
            name             := Field(IS_TERM_IN_FIELD, str,        "Name",               "name"),
            tags             := Field(IS_TAG_ON_DEVICE, str,        "Tags",               "tags"),
            enabled          := Field(IS_TERM_IN_FIELD, bool,       "Enabled",            "enabled"),
            poeEnabled       := Field(IS_TERM_IN_FIELD, bool,       "POE",                "poeEnabled"),
            type             := Field(IS_TERM_IN_FIELD, str,        "Type",               "type"),
            vlan             := Field(IS_TERM_IN_FIELD, str,        "VLAN",               "vlan"),
            voiceVlan        := Field(IS_TERM_IN_FIELD, str,        "Voice VLAN",         "voiceVlan"),
            allowedVlans     := Field(IS_VLAN_ALLOWED,  str,        "Allowed VLANs",      "allowedVlans" ),
            rstpEnabled      := Field(IS_TERM_IN_FIELD, bool,       "RSTP Enabled",       "rstpEnabled"),
            stpGuard         := Field(IS_TERM_IN_FIELD, str,        "STP Guard",          "stpGuard"),
            linkNegotiation  := Field(IS_TERM_IN_FIELD, str,        "Link Negotiation",   "linkNegotiation"),
            accessPolicyType := Field(IS_TERM_IN_FIELD, str,        "Access Policy Type", "accessPolicyType"),
        ]
        preview.draw = self._preview
        preview.sort_key = self._preview_sort
        tags.draw = self._tags
        enabled.draw = enabled.draw_boolean
        poeEnabled.draw = poeEnabled.draw_boolean
        rstpEnabled.draw = rstpEnabled.draw_boolean

        self.name = name

        data = [
            s.get_json() | {
                "switchport": s,
                "switch": s.switch_name,
            } for s in switch_ports
        ]
        super().__init__(table_name, spec, data)

    @override
    def get_default_sort_field(self) -> Field:
        return self.name

    def _preview(self, switch_port: dict):
        port: Switch.SwitchPort = switch_port["switchport"]
        port.draw(30, 20, False)

    def _preview_sort(self, switch_port: dict):
        return (switch_port["switch"], Sortable(switch_port["portId"]))

    def _tags(self, switch_port: dict):
        # Not including the pygui.same_line(), causes the table to bug out.
        for i, tag in enumerate(switch_port["tags"]):
            if i > 0:
                pygui.same_line()
            white = pygui.color_convert_float4_to_u32((1, 1, 1, 1))
            text_widget(tag, white, Colour.get_colour(tag).to_u32())
