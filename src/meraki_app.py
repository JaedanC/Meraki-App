from __future__ import annotations
from typing import List, Optional

import extra.meraki_util
import pygui_cython as pygui
from extra.api import RelaxedDictionary

from .cache import Cache
from .future import Future
from .model import Switch, MerakiDevice, PortProfile
from .filtering import switch_filter, appliance_filter, tokenise_query_into_dict
from .tables.switchports_table import SwitchportsTable


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
        self.switchport_table = SwitchportsTable("Switchports", [])
        self.reapply_switch_port_filter = True
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
        self.networks.sort(key=lambda x: x.get("name"))
        self.switches_filtered = None
        self.reapply_switch_port_filter = True


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
            self.switchport_table = SwitchportsTable("Switchport Table", self.switches_filtered_ports)
            self.switchport_table.reapply_filter(self.switch_port_search.value)

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
        if pygui.input_text("Filter Ports", self.switch_port_search) or self.reapply_switch_port_filter:
            self.switchport_table.reapply_filter(self.switch_port_search.value)
            self.reapply_switch_port_filter = False

        pygui.text("Showing {} ports".format(self.switchport_table.len_filtered()))
        self.switchport_table.draw()


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
            self.appliances.append(MerakiDevice(appliance, self.meraki_api_key))
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
