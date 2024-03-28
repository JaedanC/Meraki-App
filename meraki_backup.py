from __future__ import annotations
import datetime
import json
import time
from threading import Thread, Lock
from typing import Callable, List, Any
import itertools

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
        for port in switch.ports:
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
        def __init__(self, switch_name: str, port: dict):
            port = RelaxedDictionary(port)
            self.switch_name = switch_name
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
        
        def get_default_sort(self):
            return [self.switch_name, int(self.portId)]

        def get_column_field(self, idx: int):
            return [
                None,
                self.switch_name,
                int(self.portId),
                self.name or "",
                self.type,
                self.vlan or 0,
                self.poeEnabled,
            ][idx]
        
        def draw(self, sz_x, sz_y, top_row=True, sfp=False, stack=False):
            """This function is responsible for drawing a singular port. The room
            you have to draw is denoted by sz_x and sz_y.
            
            - `sfp` will be True if this port is an additional SFP port
            - `stack` will be True if this port is a stacking port
            - Otherwise treat this as a regular port. TODO: This currently does
            not take into consideration fibre switches.
            """
            def show_tooltip():
                if pygui.is_item_hovered() and pygui.begin_tooltip():
                    pygui.text(json.dumps(self.__dict__, indent=4))
                    pygui.end_tooltip()

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
                show_tooltip()
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
            show_tooltip()
        
    def __init__(self, switch_info: RelaxedDictionary):
        self.name = switch_info.get("name")
        self.serial = switch_info.get("serial")
        self.mac = switch_info.get("mac")
        self.network_id = switch_info.get("network", "id")
        self.model = switch_info.get("model")

        self.switchport_profile = switch_profiles.get_switch_profile(
            self.model, len(switch_info.get("ports")))
        self.ports = [Switch.SwitchPort(self.name or self.mac, p) for p in switch_info.get("ports")]

        # If the switch only has one row, treat it as a bottom row. This will
        # make the labels appear on the bottom.
        if len(self.switchport_profile) == 1:
            iterator = itertools.zip_longest([], self.switchport_profile[0])
        else:
            iterator = itertools.zip_longest(self.switchport_profile[0], self.switchport_profile[1])
        
        self.top_line = []
        self.bot_line = []
        running_port_idx = 0
        for top, bot in iterator:
            top: switch_profiles.p
            bot: switch_profiles.p

            if top is not None:
                if top == switch_profiles.p.Gap or top == switch_profiles.p.RJ45_Gap:
                    self.top_line.append(top)
                elif isinstance(top, tuple):
                    self.top_line.append(top)
                    running_port_idx += 1
                else:
                    self.top_line.append((running_port_idx, top))
                    running_port_idx += 1

            if bot is not None:
                if bot == switch_profiles.p.Gap or bot == switch_profiles.p.RJ45_Gap:
                    self.bot_line.append(bot)
                elif isinstance(bot, tuple):
                    self.bot_line.append(bot)
                    running_port_idx += 1
                else:
                    self.bot_line.append((running_port_idx, bot))
                    running_port_idx += 1
    

    def draw(self):
        """Draw the switch and its ports."""
        PORT_HEIGHT = 40
        RJ45_WIDTH = 40
        SFP_WIDTH = 45
        STACK_WIDTH = 80
        GAP_WIDTH = 5

        def _show_port_text(port_text: str, width: float):
            port_text_len = pygui.calc_text_size(port_text)[0]
            pygui.set_cursor_pos_x(
                pygui.get_cursor_pos_x() + width / 2 - port_text_len / 2)
            
            pygui.push_style_color(pygui.COL_TEXT, pygui.color_convert_float4_to_u32((0.4, 0.4, 0.4, 1)))
            pygui.text(port_text)
            pygui.pop_style_color()
        
        for i, port_type in enumerate(self.top_line + self.bot_line):
            is_first_line = i < len(self.top_line)
            if i > 0 and i != len(self.top_line):
                pygui.same_line()
            
            if isinstance(port_type, tuple):
                assert port_type[0] < len(self.ports), \
                    "Error: Remember, port_id must be an index. len(ports): {}, index: {}".format(
                        len(self.ports), port_type[0]
                )
                port = self.ports[port_type[0]]
                port_type = port_type[1]
            else:
                port = None
            
            if port_type == switch_profiles.p.Gap:
                pygui.dummy((GAP_WIDTH, 0))
                continue

            if port_type == switch_profiles.p.RJ45_Gap:
                pygui.dummy((RJ45_WIDTH, PORT_HEIGHT))
                continue
            
            # Draw the port
            assert port != None
            port: Switch.SwitchPort

            sfp = False
            stack = False
            if port_type == switch_profiles.p.RJ45:
                size = RJ45_WIDTH
            elif port_type == switch_profiles.p.SFP:
                size = SFP_WIDTH
                sfp = True
            else:
                size = STACK_WIDTH
                stack = True
            
            pygui.begin_group()
            if is_first_line:
                _show_port_text(port.portId, size)
                port.draw(size, PORT_HEIGHT, is_first_line, sfp, stack)
            else:
                port.draw(size, PORT_HEIGHT, is_first_line, sfp, stack)
                _show_port_text(port.portId, size)
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

        self.switches_filtered: List[Switch] = None
        self.switch_search = pygui.String("")
        self.switchports: List[Switch.SwitchPort] = None
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


    def switch_draw(self):
        pygui.text("FPS: {:.1f}".format(pygui.get_io().framerate))
        self.p_organization_switches.draw_refresh_button("Get Organisation Switch Ports")
        self.p_organization_networks.draw_refresh_button("Get Organisation Networks")

        if not self.p_organization_networks.response_exists() \
            or not self.p_organization_switches.response_exists():
            return
        
        if pygui.input_text("Filter", self.switch_search) or self.switches_filtered is None:
            self.switches_filtered = switch_filter(self.switch_search.value, self.switches)

        if len(self.switch_search.value) == 0:
            for network in self.networks:
                if not pygui.collapsing_header(network.get("name")):
                    continue
                
                switches: List[Switch] = list(filter(lambda s: s.network_id == network.get("id"), self.switches))
                for switch in switches:
                    if pygui.tree_node((switch.name or switch.mac) + " " + switch.model):
                        switch.draw()
                        pygui.tree_pop()
        else:
            for switch in self.switches_filtered:
                if pygui.tree_node((switch.name or switch.mac) + " " + switch.model):
                    switch.draw()
                    pygui.tree_pop()

    
    def switchports_draw(self):
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
        
        if pygui.begin_table("switchport_sorting", 7, table_flags):
            pygui.table_setup_column("Preview",   pygui.TABLE_COLUMN_FLAGS_NO_SORT)
            pygui.table_setup_column("Switch",    pygui.TABLE_COLUMN_FLAGS_DEFAULT_SORT | pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("Port Id",   pygui.TABLE_COLUMN_FLAGS_DEFAULT_SORT | pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("Name",      pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_column("Port Type", pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_column("VLAN",      pygui.TABLE_COLUMN_FLAGS_WIDTH_FIXED)
            pygui.table_setup_column("POE",       pygui.TABLE_COLUMN_FLAGS_WIDTH_STRETCH)
            pygui.table_setup_scroll_freeze(0, 1) # Make row always visible
            pygui.table_headers_row()

            if self.switchports is None:
                self.switchports = []
                for switch in self.switches_filtered[:50]:
                    for port in switch.ports:
                        self.switchports.append(port)

            def custom_key(port: Switch.SwitchPort):
                # From: https://stackoverflow.com/a/75123782
                # name changed; otherwise the same
                class negated:
                    def __init__(self, obj):
                        self.obj = obj

                    def __eq__(self, other):
                        return other.obj == self.obj

                    def __lt__(self, other):
                        return other.obj < self.obj

                sort_specs = pygui.table_get_sort_specs()
                sort_with = []
                for sort_spec in sort_specs.specs:
                    compare_obj = None
                    compare_obj = port.get_column_field(sort_spec.column_index)

                    if sort_spec.sort_direction == pygui.SORT_DIRECTION_DESCENDING:
                        compare_obj = negated(compare_obj)
                    sort_with.append(compare_obj)
                
                # Add some default sorting fields
                sort_with += port.get_default_sort()
                return tuple(sort_with)

            # Sort our data if sort specs have been changed!
            if (sort_specs := pygui.table_get_sort_specs()):
                if sort_specs.specs_dirty:
                    self.switchports.sort(key=custom_key)
                sort_specs.specs_dirty = False
            
            # Demonstrate using clipper for large vertical lists
            clipper = pygui.ImGuiListClipper.create()

            # This is our first example of not being able to share heap objects
            # across the dll. I need to get a pointer to a valid type that it
            # creates, not me. This requires adding a custom constructor and 
            # destructor for the ImGuiListClipper class.
            clipper.begin(len(self.switchports))
            while clipper.step():
                for row_n in range(clipper.display_start, clipper.display_end):
                    # Display a data item
                    port: Switch.SwitchPort = self.switchports[row_n]
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
                    pygui.text(str(port.poeEnabled))
                    pygui.pop_id()
            clipper.destroy()

            pygui.end_table()


    def draw(self):
        pygui.begin("Meraki Backup")
        self.switch_draw()
        pygui.end()
        pygui.begin("Switch Ports")
        self.switchports_draw()
        pygui.end()
