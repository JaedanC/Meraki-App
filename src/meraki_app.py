from __future__ import annotations
from typing import List, Optional

import extra.meraki_util
import pygui
from extra.api import RelaxedDictionary

from .cache import Cache
from .future import Future
from .pygui_ext import Sortable, SortableNegative
from .model import Switch, MerakiDevice, PortProfile
from .filtering import switch_filter, switch_port_filter, appliance_filter, tokenise_query_into_dict


class MerakiApp:
    def __init__(
            self,
            meraki_api_key: Optional[str],
            meraki_organisation_id: str,
            query_cache: Cache,
        ):
        self.set_meraki_api_key(meraki_api_key)
        self.meraki_organisation_id = meraki_organisation_id
        self.query_cache = query_cache

        self.p_organization_networks = Future(
            extra.meraki_util.get_organization_networks,
                [],
                {
                    "organization_id": self.meraki_organisation_id
                },
            self.query_cache,
            "get_organization_networks",
        )
        self.p_organization_switches = Future(
            extra.meraki_util.get_organization_switch_ports_by_switch,
                [],
                {
                    "organization_id": self.meraki_organisation_id
                },
            self.query_cache,
            "get_organization_switch_ports_by_switch",
        )
        self.port_profiles = []
        self.networks = []
        self.switches: List[Switch] = []
        self.switch_search = pygui.String("")
        self.switch_port_search = pygui.String("")
        self.switches_filtered: List[Switch] = None
        self.switches_filtered_ports: List[Switch.SwitchPort] = None
        self.switches_filtered_ports_filtered: List[Switch.SwitchPort] = None
        self.switch_callback()

        self.p_organization_appliances = Future(
            extra.meraki_util.get_organization_devices,
                [],
                {
                    "organization_id": self.meraki_organisation_id,
                    "productTypes": ["appliance", "switch"]
                },
            self.query_cache,
            "get_organization_appliances",
        )
        self.appliances: List[MerakiDevice] = []
        self.appliances_filtered: List[MerakiDevice] = []
        self.appliance_search = pygui.String("")
        self.appliance_callback()


    def set_meraki_api_key(self, meraki_api_key: str):
        self.meraki_api_key = pygui.String(meraki_api_key or "")
        self.mki_dashboard = extra.meraki_util.init(meraki_api_key or "Placeholder")


    def switch_callback(self):
        if not self.p_organization_networks.response_exists() \
            or not self.p_organization_switches.response_exists():
            return

        self.switches.clear()
        network_set = set()
        for switch in self.p_organization_switches.response():
            switch = RelaxedDictionary(switch)
            self.switches.append(Switch(switch))

            network_set.add(switch.get("network", "id"))

        self.networks = [RelaxedDictionary(n) for n in self.p_organization_networks.response() if n["id"] in network_set]
        self.switches_filtered = None


    def switch_window(self):
        pygui.text("FPS: {:.1f}".format(pygui.get_io().framerate))
        if pygui.tree_node("API Key"):
            if pygui.button("Show") or pygui.is_item_active():
                input_flags = pygui.INPUT_TEXT_FLAGS_NONE
            else:
                input_flags = pygui.INPUT_TEXT_FLAGS_PASSWORD

            pygui.same_line()
            pygui.input_text("Meraki API key", self.meraki_api_key, input_flags)
            if pygui.is_item_deactivated_after_edit():
                self.set_meraki_api_key(self.meraki_api_key.value)
                print("Set to", self.meraki_api_key.value)
            pygui.tree_pop()

        self.p_organization_switches.draw_refresh_button("Get Organisation Switch Ports", dashboard=self.mki_dashboard)
        self.p_organization_networks.draw_refresh_button("Get Organisation Networks",     dashboard=self.mki_dashboard)

        if not self.p_organization_networks.response_exists() \
            or not self.p_organization_switches.response_exists():
            return

        if self.p_organization_networks.is_response_new():
            self.switch_callback()
            self.p_organization_networks.mark_response_used()

        if self.p_organization_switches.is_response_new():
            self.switch_callback()
            self.p_organization_switches.mark_response_used()

        if pygui.input_text("Filter", self.switch_search) or self.switches_filtered is None:
            self.switches_filtered = switch_filter(self.switch_search.value, self.switches)
            self.switches_filtered_ports = sum([s.ports for s in self.switches_filtered], start=[])
            self.switches_filtered_ports_filtered = None

        qt = tokenise_query_into_dict(self.switch_search.value)
        filtering_by_network = (qt.get("network") or qt.get("site")) is not None
        if len(self.switch_search.value) == 0 or filtering_by_network:
            for network in self.networks:
                switches: List[Switch] = list(filter(lambda s: s.network_id == network.get("id"), self.switches_filtered))
                for i, switch in enumerate(switches):
                    if i == 0 and not pygui.collapsing_header(network.get("name")):
                        break

                    if pygui.tree_node((switch.name or switch.mac) + " " + switch.model):
                        switch.draw()
                        pygui.tree_pop()
        else:
            for switch in self.switches_filtered:
                if pygui.tree_node((switch.name or switch.mac) + " " + switch.model):
                    switch.draw()
                    pygui.tree_pop()


    def switchports_window(self):
        if self.switches_filtered_ports is None:
            return

        if pygui.input_text("Filter Ports", self.switch_port_search) or self.switches_filtered_ports_filtered is None:
            self.switches_filtered_ports_filtered = switch_port_filter(self.switch_port_search.value, self.switches_filtered_ports)

        pygui.text("Showing {} ports".format(len(self.switches_filtered_ports_filtered)))

        table_flags = pygui.TABLE_FLAGS_RESIZABLE | \
            pygui.TABLE_FLAGS_REORDERABLE | \
            pygui.TABLE_FLAGS_HIDEABLE | \
            pygui.TABLE_FLAGS_SORTABLE | \
            pygui.TABLE_FLAGS_SORT_MULTI | \
            pygui.TABLE_FLAGS_ROW_BG | \
            pygui.TABLE_FLAGS_BORDERS_OUTER | \
            pygui.TABLE_FLAGS_BORDERS_V | \
            pygui.TABLE_FLAGS_NO_BORDERS_IN_BODY | \
            pygui.TABLE_FLAGS_SCROLL_Y

        if pygui.begin_table("switchport_sorting", 11, table_flags):
            pygui.table_setup_column("Preview",      pygui.TABLE_COLUMN_FLAGS_NO_SORT)
            pygui.table_setup_column("Switch",       pygui.TABLE_COLUMN_FLAGS_DEFAULT_SORT | pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("Port Id",      pygui.TABLE_COLUMN_FLAGS_DEFAULT_SORT | pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("Name",         pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_column("Type",         pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_column("VLAN",         pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("Voice VLAN",   pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("Allowed VLAN", pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("POE",          pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_column("STP Guard",    pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_column("RSTP Enabled", pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_scroll_freeze(0, 1) # Make row always visible
            pygui.table_headers_row()

            def custom_key(port: Switch.SwitchPort):
                sort_specs = pygui.table_get_sort_specs()
                sort_with = []
                for sort_spec in sort_specs.specs:
                    compare_obj = port.get_column_field(sort_spec.column_index)

                    if sort_spec.sort_direction == pygui.SORT_DIRECTION_DESCENDING:
                        compare_obj = SortableNegative(compare_obj)
                    else:
                        compare_obj = Sortable(compare_obj)

                    sort_with.append(compare_obj)

                # Add some default sorting fields
                if sort_spec.sort_direction == pygui.SORT_DIRECTION_DESCENDING:
                    sort_with += [SortableNegative(d) for d in port.get_default_sort()]
                else:
                    sort_with += [Sortable(d) for d in port.get_default_sort()]
                return tuple(sort_with)

            # Sort our data if sort specs have been changed!
            if (sort_specs := pygui.table_get_sort_specs()):
                if sort_specs.specs_dirty:
                    self.switches_filtered_ports_filtered.sort(key=custom_key)
                sort_specs.specs_dirty = False

            # Demonstrate using clipper for large vertical lists
            clipper = pygui.ImGuiListClipper.create()

            # This is our first example of not being able to share heap objects
            # across the dll. I need to get a pointer to a valid type that it
            # creates, not me. This requires adding a custom constructor and
            # destructor for the ImGuiListClipper class.
            clipper.begin(len(self.switches_filtered_ports_filtered))
            while clipper.step():
                for row_n in range(clipper.display_start, clipper.display_end):
                    # Display a data item
                    port: Switch.SwitchPort = self.switches_filtered_ports_filtered[row_n]
                    pygui.push_id((port.switch_name, port.portId))
                    pygui.table_next_row()
                    pygui.table_next_column()
                    port.draw(30, 20, False)
                    pygui.table_next_column()
                    pygui.text_unformatted(port.switch_name)
                    pygui.table_next_column()
                    pygui.text(str(port.portId))
                    pygui.table_next_column()
                    pygui.text(port.name or "")
                    pygui.table_next_column()
                    pygui.text(port.type)
                    pygui.table_next_column()
                    pygui.text(str(port.vlan))
                    pygui.table_next_column()
                    pygui.text(str(port.voiceVlan))
                    pygui.table_next_column()
                    pygui.text(str(port.allowedVlans))
                    pygui.table_next_column()
                    pygui.text(str(port.poeEnabled))
                    pygui.table_next_column()
                    pygui.text(str(port.stpGuard))
                    pygui.table_next_column()
                    pygui.text(str(port.rstpEnabled))
                    pygui.pop_id()
            clipper.destroy()

            pygui.end_table()


    def port_profile_draw(self):
        pygui.begin_group()
        if len(self.port_profiles) == 0:
            pygui.text("Drag profiles here")
        else:
            for i, port_profile in enumerate(self.port_profiles):
                if i > 0:
                    pygui.same_line()

                port_profile.draw()
        pygui.end_group()

        if pygui.begin_drag_drop_target():
            payload = pygui.accept_drag_drop_payload("Port")
            if payload is not None:
                self.port_profiles.append(PortProfile(payload.data))
            pygui.end_drag_drop_target()


    def appliance_callback(self):
        if not self.p_organization_appliances.response_exists():
            return

        self.appliances.clear()
        for appliance in self.p_organization_appliances.response():
            self.appliances.append(MerakiDevice(appliance))
        self.appliances.sort(key=lambda x: (x.name, x.mac))

        self.appliances_filtered = None


    def appliance_lldp_window(self):
        self.p_organization_appliances.draw_refresh_button("Get Organisation Appliances", dashboard=self.mki_dashboard)

        if not self.p_organization_appliances.response_exists():
            return

        if self.p_organization_appliances.is_response_new():
            self.appliance_callback()
            self.p_organization_appliances.mark_response_used()

        if pygui.input_text("Filter", self.appliance_search) or self.appliances_filtered is None:
            self.appliances_filtered = appliance_filter(self.appliance_search.value, self.appliances)

        for appliance in self.appliances_filtered:
            if pygui.collapsing_header((appliance.name or appliance.mac) + " " + appliance.model):
                appliance.draw(self.mki_dashboard)


    def draw(self):
        main_viewport = pygui.get_main_viewport()
        id_ = pygui.get_id("Main view")
        ds = pygui.dock_space_over_viewport(id_, main_viewport)

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Switches"):
            self.switch_window()
        pygui.end()

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Switch Ports"):
            self.switchports_window()
        pygui.end()

        # pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        # if pygui.begin("Port Profiles"):
        #     self.port_profile_draw()
        # pygui.end()

        pygui.set_next_window_dock_id(ds, pygui.COND_FIRST_USE_EVER)
        if pygui.begin("Appliance LLDP"):
            self.appliance_lldp_window()
        pygui.end()
