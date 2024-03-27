from __future__ import annotations
import datetime
import json
import time
from threading import Thread, Lock
from typing import Callable, List, Any

import meraki_util
import pygui
import switch_profiles
from api import RelaxedDictionary, ListDictFilter


def switch_filter(query: str, switches: List[Switch]) -> List[Switch]:
    """This filter is responsible for filtering switches. Returnt the switches
    you want to keep from the query string. This function is run whenever the
    query string updates (not every frame) so we can get away with an expensive
    operation.
    """
    query = query.lower()

    terms = {} 
    for t in query.split(" "):
        if ":" not in t:
            terms["name"] = t
            continue

        t = t.split(":", 1)
        terms[t[0]] = t[1]
    
    terms = RelaxedDictionary(terms)

    to_keep = []
    for switch in switches:
        if terms.get("name") is not None and terms.get("name") not in switch.name.lower():
            continue

        if terms.get("model") is not None and terms.get("model") not in switch.model.lower():
            continue
        
        keep_port = False
        for port in switch.ports + switch.sfp_ports:
            if terms.get("vlan") is not None and terms.get("vlan") != str(port.vlan):
                continue

            if terms.get("voice") is not None and terms.get("voice") != str(port.voiceVlan):
                continue
            
            if terms.get("poe") is not None and terms.get("poe") != str(port.poeEnabled).lower():
                continue

            keep_port = True
            break
        
        if keep_port:
            to_keep.append(switch)

    return to_keep


class Switch:
    class SwitchPort:
        def __init__(self, port: dict):
            port = RelaxedDictionary(port)
            self.portId = port.get("portId")
            self.name = port.get("name")
            self.tags = port.get("tags")
            self.enabled = port.get("enabled", False)
            self.poeEnabled = port.get("poeEnabled", False)
            self.type = port.get("type")
            self.vlan = port.get("vlan")
            self.voiceVlan = port.get("voiceVlan") if port.get("type") == "access" else None
            self.allowedVlans = port.get("allowedVlans")
            self.rstpEnabled = port.get("rstpEnabled", False)
            self.stpGuard = port.get("stpGuard")
            self.linkNegotiation = port.get("linkNegotiation")
            self.accessPolicyType = port.get("accessPolicyType")
            self.stickyMacAllowList = port.get("stickyMacAllowList", [])
            self.stickyMacAllowListLimit = port.get("stickyMacAllowListLimit")
        
        def draw(self, sz_x, sz_y, sfp=False, stack=False):
            """This function is responsible for drawing a singular port. The room
            you have to draw is denoted by sz_x and sz_y.
            
            - `sfp` will be True if this port is an additional SFP port
            - `stack` will be True if this port is a stacking port
            - Otherwise treat this as a regular port. TODO: This currently does
            not take into consideration fibre switches.
            """
            draw_list = pygui.get_window_draw_list()

            cx, cy = pygui.get_cursor_screen_pos()

            # Background: Enabled
            if self.enabled:
                bg_colour = (0.5, 0.5, 0.5, 1)
            else:
                bg_colour = (0.2, 0.2, 0.2, 1)
            draw_list.add_rect_filled(
                (cx, cy),
                (cx + sz_x, cy + sz_y),
                pygui.color_convert_float4_to_u32(bg_colour),
            )

            # We don't need to show anything more for stack ports...
            if stack:
                pygui.dummy((sz_x, sz_y))
                return

            # Border: PoE
            if self.poeEnabled:
                border_colour = (0.8, 0.8, 0.1, 1)
            else:
                border_colour = (0, 0, 0, 0)
            draw_list.add_rect(
                (cx, cy),
                (cx + sz_x, cy + sz_y),
                pygui.color_convert_float4_to_u32(border_colour),
                0,
                0,
                2
            )
            
            # Inner circle: Type
            middle_x = cx + sz_x / 2
            middle_y = cy + sz_y / 2

            # if self.vlan == 201 and self.voiceVlan == 100:
                # print(self)

            if self.type == "access":
                draw_list.add_circle_filled(
                    (middle_x, middle_y),
                    min(sz_x, sz_y) / 3,
                    pygui.color_convert_float4_to_u32((0, 0, 0, 1)),
                )
            
            if self.voiceVlan is not None and self.type == "access":
                idx = int(pygui.get_time()) % 2
                text = [self.vlan, self.voiceVlan][idx]
                text_colour = [(0.8, 1, 0.8, 1), (1, 0.5, 0.5, 1)][idx]
            else:
                text = self.vlan
                text_colour = (1, 1, 1, 1)
            text_width = pygui.calc_text_size(str(text))
            draw_list.add_text(
                (
                    middle_x - text_width[0] / 2,
                    middle_y - text_width[1] / 2
                ),
                pygui.color_convert_float4_to_u32(text_colour),
                str(text)
            )

            pygui.dummy((sz_x, sz_y))
        
    def __init__(self, switch_info: RelaxedDictionary):
        self.name = switch_info.get("name")
        self.serial = switch_info.get("serial")
        self.mac = switch_info.get("mac")
        self.network_id = switch_info.get("network", "id")
        self.model = switch_info.get("model")

        self.switchport_profile = switch_profiles.get_switch_profile(
            self.model, len(switch_info.get("ports")))
        self.ports = [Switch.SwitchPort(p) for p in switch_info.get("ports")]
        
        all_ports = switch_info.get("ports", [])
        normal_ports = ListDictFilter(switch_info.get("ports", [])) \
            .filter_function(["type"], lambda t: t != "stack") \
            .compile_no_relaxed()
        stack_ports = ListDictFilter(all_ports) \
            .filter_function(["type"], lambda t: t == "stack") \
            .compile_no_relaxed()
        
        ports = [Switch.SwitchPort(p) for p in normal_ports]

        _extra = len(ports) % 8
        self._common_ports = len(ports) - _extra

        self.ports = ports[:self._common_ports]
        self.sfp_ports = ports[self._common_ports:]
        self.stack_ports = [Switch.SwitchPort(p) for p in stack_ports]
    
    def draw(self):
        """Draw the switch and its ports."""
        SIZE = 40
        SFP_MULTIPLIER = 1.1
        STACK_MULTIPLER = 2

        def show_port_text(port_text: str, width: float):
            port_text_len = pygui.calc_text_size(port_text)[0]
            pygui.set_cursor_pos_x(
                pygui.get_cursor_pos_x() + width / 2 - port_text_len / 2)
            
            pygui.push_style_color(pygui.COL_TEXT, pygui.color_convert_float4_to_u32((0.4, 0.4, 0.4, 1)))
            pygui.text(port_text)
            pygui.pop_style_color()

        switch_has_one_port_line = len(self.ports) < 16
        for i in range(len(self.ports)):
            # Same line the SFP etc. ports
            if i > 0 and (i != self._common_ports // 2 or switch_has_one_port_line):
                pygui.same_line()
            
            # Gap between sets of 12 ports
            if (self._common_ports % 6 == 0 \
                    and i % 6 == 0 \
                    and i != 0 \
                    and i != self._common_ports // 2):
                pygui.dummy((5, 0))
                pygui.same_line()
            
            pygui.begin_group()


            if switch_has_one_port_line:
                # 0, 1, 2, 3, 4
                port_id = i
                in_first_line = False
            elif  i < len(self.ports) // 2:
                # 0, 2, 4, 6,
                port_id = i * 2
                in_first_line = True
            else:
                # 1, 3, 5, 7
                port_id = (i * 2 % len(self.ports)) + 1
                in_first_line = False

            port = self.ports[port_id]
            
            if not in_first_line:
                port.draw(SIZE, SIZE)
            show_port_text(str(port_id + 1), SIZE)
            if in_first_line:
                port.draw(SIZE, SIZE)
            
            pygui.end_group()
        
        pygui.same_line()
        pygui.dummy((10, 0))

        for i, sfp in enumerate(self.sfp_ports):
            pygui.same_line()
            pygui.begin_group()
            sfp.draw(SIZE * SFP_MULTIPLIER, SIZE, sfp=True)
            show_port_text(str(len(self.ports) + i + 1), SIZE * SFP_MULTIPLIER)
            pygui.end_group()

        # Gap for stack ports
        pygui.same_line()
        pygui.dummy((10, 0))

        for i, stack_port in enumerate(self.stack_ports):
            pygui.same_line()
            pygui.begin_group()
            stack_port.draw(SIZE * STACK_MULTIPLER, SIZE, stack=True)
            show_port_text(str(i + 1), SIZE * STACK_MULTIPLER)
            pygui.end_group()


class Cache:
    def __init__(self, cache: dict):
        self._cache = RelaxedDictionary(cache)
        self._lock = Lock()
    
    def set(self, keys, set_key, value):
        self._lock.acquire()
        self._cache.set(keys, set_key, value)
        with open("query_cache.json", "w") as f:
            json.dump(self._cache.get_base(), f, indent=4)
        self._lock.release()

    
    def get(self, *keys, **kwargs):
        self._lock.acquire()
        found = self._cache.get(*keys, **kwargs)
        self._lock.release()
        return found


class Future:
    def __init__(
            self,
            request: Callable,
            args: List[Any],
            cache: Cache,
            lookup: str,
            callback: Callable=None
        ):
        self._request: Callable = request
        self._request_args = args
        self._lookup = lookup
        self._response = cache.get(lookup, "response")
        self._time = cache.get(lookup, "time")
        self._refreshing = False
        self._cache = cache
        self._callback = callback

    def draw_refresh_button(self, label: str):
        label = "{}".format(label, self._lookup)
        if self._refreshing:
            pygui.button(label + " " + "/-\|"[(pygui.get_frame_count() // 60) % 4])
        elif pygui.button(label):
            self.begin_task()
        
        pygui.same_line()
        if self._time is not None:
            time_struct = datetime.datetime.fromtimestamp(self._time)
            pygui.text("Last refreshed: {}".format(time_struct.strftime("%m/%d/%Y, %H:%M:%S")))
        else:
            pygui.text("Last refreshed: Never")

    def response_exists(self):
        return self._response is not None

    def response(self):
        return self._response
    
    def get_last_updated(self):
        return self._time

    def _task(self):
        try:
            self._response = self._request(*self._request_args)
            self._time = time.time()
            self._cache.set([self._lookup], "response", self._response)
            self._cache.set([self._lookup], "time", self._time)
        except Exception as e:
            raise e
        finally:
            self._refreshing = False
            if self._callback is not None:
                self._callback()
    
    def begin_task(self):
        self._refreshing = True
        self.t = Thread(target=self._task)
        self.t.start()


class BackupApp:
    def __init__(self):
        with open("meraki_api_key_jaedan.txt") as f:
            self.mki_dashboard = meraki_util.init(f.read())

        try:
            with open("query_cache.json") as f:
                cache = json.load(f)
        except FileNotFoundError:
            cache = {}
        
        self.response_cache = Cache(cache)


        HC_ORG = "34581"
        self.p_organization_networks = Future(
            meraki_util.get_organization_networks, [self.mki_dashboard, HC_ORG],
            self.response_cache,
            "get_organization_networks",
            self.refresh_callback
        )
        self.p_organization_switches = Future(
            meraki_util.get_organization_switch_ports_by_switch, [self.mki_dashboard, HC_ORG],
            self.response_cache,
            "get_organization_switch_ports_by_switch",
            self.refresh_callback
        )

        self.filtered_switches: List[Switch] = None
        self.network_search = pygui.String("")
        self.refresh_callback()
        

    def refresh_callback(self):
        if not self.p_organization_networks.response_exists() \
            or not self.p_organization_switches.response_exists():
            return
        
        self.switches: List[Switch] = []
        network_set = set()
        for switch in self.p_organization_switches.response():
            switch = RelaxedDictionary(switch)
            self.switches.append(Switch(switch))
            network_set.add(switch.get("network", "id"))
        
        self.networks = [RelaxedDictionary(n) for n in self.p_organization_networks.response() if n["id"] in network_set]


    def logic(self):
        self.p_organization_switches.draw_refresh_button("Get Organisation Switch Ports")
        self.p_organization_networks.draw_refresh_button("Get Organisation Networks")

        if not self.p_organization_networks.response_exists() \
            or not self.p_organization_switches.response_exists():
            return
        
        if pygui.input_text("Filter", self.network_search) or self.filtered_switches is None:
            self.filtered_switches = switch_filter(self.network_search.value, self.switches)

        if len(self.network_search.value) == 0:
            for network in self.networks:
                if not pygui.collapsing_header(network.get("name")):
                    continue
                
                switches: List[Switch] = list(filter(lambda s: s.network_id == network.get("id"), self.switches))
                for switch in switches:
                    if pygui.tree_node((switch.name or switch.mac) + " " + switch.model):
                        switch.draw()
                        pygui.tree_pop()
        else:
            for switch in self.filtered_switches:
                if pygui.tree_node((switch.name or switch.mac) + " " + switch.model):
                    switch.draw()
                    pygui.tree_pop()

                    
    def draw(self):
        pygui.begin("Meraki Backup")
        self.logic()
        pygui.end()
