import itertools
import json
import random
import time
from typing import List

import pygui
import extra.meraki_util
from extra.api import RelaxedDictionary

from . import switch_profiles
from .cache import Cache
from .future import Future
from .pygui_ext import Sortable, text_copy

import requests


def createDeviceLiveToolsSpeedTest(api_key: str, device_serial: str, uplink: str):
    print(f"Testing the speed of {device_serial}")
    # https://developer.cisco.com/meraki/api-v1/create-device-live-tools-speed-test/
    url = f"https://api.meraki.com/api/v1/devices/{device_serial}/liveTools/speedTest"

    payload = {
        "interface": f"{uplink}"
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    res = requests.request("POST", url, headers=headers, data=json.dumps(payload), timeout=10)
    return res.json()


def getDeviceLiveToolsSpeedTest(api_key: str, device_serial: str, speed_test_id: str):
    print(f"Checking if {device_serial} has completed the speedtest: {speed_test_id}")
    # https://developer.cisco.com/meraki/api-v1/get-device-live-tools-speed-test/
    url = f"https://api.meraki.com/api/v1/devices/{device_serial}/liveTools/speedTest/{speed_test_id}"

    payload = None

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Accept": "application/json"
    }

    response = requests.request("GET", url, headers=headers, data = payload, timeout=10)
    return response.json()



class MerakiDevice:
    def __init__(self, device: dict, meraki_api_key: pygui.String):
        self._raw = device
        self.meraki_api_key = meraki_api_key
        device = RelaxedDictionary(device)
        self.name = device.get("name")
        self.serial = device.get("serial")
        self.mac = device.get("mac")
        self.network_id = device.get("networkId")
        self.product_type = device.get("productType")
        self.model = device.get("model")
        self.address = device.get("address")
        self.lat = device.get("lat")
        self.lng = device.get("lng")
        self.notes = device.get("notes")
        self.tags = device.get("tags", default=[])
        self.wan1_ip = device.get("wan1Ip")
        self.wan2_ip = device.get("wan2Ip")
        self.lan_ip = device.get("lanIp")
        self.configuration_updated_at = device.get("configurationUpdatedAt")
        self.firmware = device.get("firmware")
        self.url = device.get("url")
        self.details = device.get("details", default=[])

        self.lldp: List[RelaxedDictionary] = []
        self.p_lldp = Future(
            extra.meraki_util.get_device_lldp_cdp,
                [],
                {
                    "serial": self.serial
                },
            Cache("pygui_cache/appliance {} {}.json".format(self.name or self.mac.replace(":", ""), self.serial)),
            "appliance {}.json".format(self.serial),
        )
        self.lldp_callback()

        self.wan1_speedtest = None
        self.wan2_speedtest = None
        if self.product_type == "appliance" and self.serial is not None:
            speedtest_cache = Cache("pygui_cache/appliance {} {} speedtest.json".format(self.name or self.mac.replace(":", ""), self.serial))
            self.wan1_speedtest = Future(
                createDeviceLiveToolsSpeedTest,
                [],
                {
                    "device_serial": self.serial,
                    "uplink": "wan1",
                },
                speedtest_cache,
                "wan1",
            )
            self.wan2_speedtest = Future(
                createDeviceLiveToolsSpeedTest,
                [],
                {
                    "device_serial": self.serial,
                    "uplink": "wan2",
                },
                speedtest_cache,
                "wan2",
            )
            self.wan1_speedtest_result = Future(
                getDeviceLiveToolsSpeedTest,
                [],
                {
                    "device_serial": self.serial,
                },
                speedtest_cache,
                "wan1_result",
            )
            self.wan2_speedtest_result = Future(
                getDeviceLiveToolsSpeedTest,
                [],
                {
                    "device_serial": self.serial,
                },
                speedtest_cache,
                "wan2_result",
            )
            self.speedtest_wait_timer = 3 # Seconds
            self.wan1_query_after_time_is = 0
            self.wan2_query_after_time_is = 0


    def lldp_callback(self):
        if not self.p_lldp.response_exists():
            return

        response = self.p_lldp.response()
        if "ports" not in response:
            return

        self.lldp.clear()
        for port_name, port in self.p_lldp.response()["ports"].items():
            port_name: str
            for i, char in enumerate(port_name):
                if char.isdigit():
                    break

            port_iden = port_name[:i]
            port_iden = port_iden if len(port_iden) > 0 else "Port"
            port_id = int(port_name[i:]) if port_name[i:].isnumeric() else port_name[i:]
            self.lldp.append(RelaxedDictionary(port | {
                "port_iden": port_iden,
                "port_id": port_id,
            }))

        self.lldp.sort(key=lambda x: (x.get("port_iden"), Sortable(x.get("port_id"))))

    def pygui_enqueue_speed_test(self):
        self.wan1_speedtest.draw_refresh_button("Speedtest WAN 1", (self.name or self.mac) + " wan1", api_key=self.meraki_api_key.value)
        self.wan2_speedtest.draw_refresh_button("Speedtest WAN 2", (self.name or self.mac) + " wan2", api_key=self.meraki_api_key.value)

        if self.wan1_speedtest.is_response_new():
            self.wan1_speedtest_result.begin_task(api_key=self.meraki_api_key.value, speed_test_id=self.wan1_speedtest.response()["speedTestId"])
            self.wan1_query_after_time_is = time.time() + self.speedtest_wait_timer
            self.wan1_speedtest.mark_response_used()
        
        if self.wan2_speedtest.is_response_new():
            self.wan2_speedtest_result.begin_task(api_key=self.meraki_api_key.value, speed_test_id=self.wan2_speedtest.response()["speedTestId"])
            self.wan2_query_after_time_is = time.time() + self.speedtest_wait_timer
            self.wan2_speedtest.mark_response_used()

        if self.wan1_speedtest_result is not None \
            and self.wan1_speedtest_result.response_exists() \
            and self.wan1_speedtest_result.response()["status"] != "complete" \
            and self.wan1_speedtest_result.response()["status"] != "failed" \
            and time.time() > self.wan1_query_after_time_is:
            self.wan1_speedtest_result.begin_task(api_key=self.meraki_api_key.value, speed_test_id=self.wan1_speedtest.response()["speedTestId"])
        
        if self.wan2_speedtest_result is not None \
            and self.wan2_speedtest_result.response_exists() \
            and self.wan2_speedtest_result.response()["status"] != "complete" \
            and self.wan2_speedtest_result.response()["status"] != "failed" \
            and time.time() > self.wan2_query_after_time_is:
            self.wan2_speedtest_result.begin_task(api_key=self.meraki_api_key.value, speed_test_id=self.wan2_speedtest.response()["speedTestId"])


    def draw(self, mki_dashboard):
        self.p_lldp.draw_refresh_button(f"Get Device CP & LLDP", self.name or self.mac, dashboard=mki_dashboard)

        if not self.p_lldp.queried_at_least_once():
            self.p_lldp.begin_task(dashboard=mki_dashboard)

        if self.p_lldp.is_response_new():
            self.lldp_callback()
            self.p_lldp.mark_response_used()

        pygui.text(self.name)
        pygui.same_line()
        pygui.text_disabled("(?)")
        if pygui.is_item_hovered() and pygui.begin_tooltip():
            pygui.text(str(self))
            pygui.end_tooltip()
        pygui.same_line()
        pygui.text_disabled("CDP")
        pygui.same_line()
        if self.p_lldp.get_error_status() is not None:
            pygui.text_colored((1, 0, 0, 1), "(?)")
        else:
            pygui.text_disabled("(?)")
        if pygui.is_item_hovered() and pygui.begin_tooltip():
            if self.p_lldp.response_exists():
                txt = json.dumps(self.p_lldp.response(), indent=4)
            else:
                txt = self.p_lldp.get_error_status() or "[No data]"
            pygui.text_unformatted(txt)
            pygui.end_tooltip()
        pygui.separator()
        pygui.begin_group()
        text_copy(self.serial, self.name + "serial")
        text_copy(self.mac, self.name + "mac")
        pygui.end_group()

        pygui.same_line()
        pygui.text_wrapped(self.notes)
        pygui.separator()

        longest_ip = max(len(self.wan1_ip or ""), len(self.wan2_ip or ""))

        if "wan1Ip" in self._raw:
            pygui.text("WAN 1 ")
            pygui.same_line()
            if self.wan1_ip is not None:
                pygui.text_colored((0, 0.8, 0, 1), "[active] ")
                pygui.same_line()
                pygui.text(self.wan1_ip)
            else:
                pygui.text_colored((0.8, 0, 0, 1), "[inactive]")
            if self.wan1_speedtest_result.response_exists() and self.wan1_speedtest_result.response()["status"] == "complete":
                pygui.same_line()
                pygui.text_colored((0, 1, 0, 1), "{}{} Mbps".format(" " * (longest_ip - len(self.wan1_ip or "")), self.wan1_speedtest_result.response()["results"]["speeds"]["average"]))
            elif self.wan1_speedtest_result.response_exists() and self.wan1_speedtest_result.response()["status"] == "running":
                pygui.same_line()
                pygui.text_colored((0, 1, 0, 1), "{}Running".format(" " * (longest_ip - len(self.wan1_ip or ""))))
            elif self.wan1_speedtest_result.response_exists() and self.wan1_speedtest_result.response()["status"] == "failed":
                pygui.same_line()
                pygui.text_colored((1, 0, 0, 1), "{}Speedtest Failed".format(" " * (longest_ip - len(self.wan1_ip or ""))))

        if "wan2Ip" in self._raw:
            pygui.text("WAN 2 ")
            pygui.same_line()
            if self.wan2_ip is not None:
                pygui.text_colored((0, 1, 0, 1), "[active] ")
                pygui.same_line()
                pygui.text(self.wan2_ip)
            else:
                pygui.text_colored((1, 0, 0, 1), "[inactive]")
            if self.wan2_speedtest_result.response_exists() and self.wan2_speedtest_result.response()["status"] == "complete":
                pygui.same_line()
                pygui.text_colored((0, 1, 0, 1), "{}{} Mbps".format(" " * (longest_ip - len(self.wan2_ip or "")), self.wan2_speedtest_result.response()["results"]["speeds"]["average"]))
            elif self.wan2_speedtest_result.response_exists() and self.wan2_speedtest_result.response()["status"] == "running":
                pygui.same_line()
                pygui.text_colored((0, 1, 0, 1), "{}Running".format(" " * (longest_ip - len(self.wan2_ip or ""))))
            elif self.wan2_speedtest_result.response_exists() and self.wan2_speedtest_result.response()["status"] == "failed":
                pygui.same_line()
                pygui.text_colored((1, 0, 0, 1), "{}Speedtest Failed".format(" " * (longest_ip - len(self.wan2_ip or ""))))
        
        if self.product_type == "appliance":
            self.pygui_enqueue_speed_test()

        if "lanIp" in self._raw:
            pygui.text("LAN IP")
            pygui.same_line()
            if self.lan_ip is not None:
                pygui.text_colored((0, 0.8, 0, 1), "[active] ")
                pygui.same_line()
                pygui.text(self.lan_ip)
            else:
                pygui.text_colored((0.8, 0, 0, 1), "[inactive]")

        pygui.separator()

        if not self.p_lldp.response_exists():
            return

        WIDTH = 30
        HEIGHT = pygui.get_text_line_height_with_spacing() * 4

        draw_list = pygui.get_window_draw_list()
        for port in self.lldp:
            port_iden = port.get("port_iden")
            if port_iden == "port":
                port_colour = (0, 1, 0, 1)
            elif port_iden == "wan":
                port_colour = (1, 0, 0, 1)
            elif port_iden == "lan":
                port_colour = (0, 0, 1, 1)
            else:
                port_colour = (1, 1, 1, 0.3)

            cx, cy = pygui.get_cursor_screen_pos()
            draw_list.add_rect(
                (cx, cy),
                (cx + WIDTH, cy + HEIGHT),
                pygui.color_convert_float4_to_u32(port_colour),
            )

            pygui.dummy((WIDTH, HEIGHT))
            if pygui.is_item_hovered() and pygui.begin_tooltip():
                pygui.text(json.dumps(port.get_base(), indent=4))
                pygui.end_tooltip()
            pygui.same_line()

            # Device Recognition Bar
            device_name = port.get("lldp", "systemName") or port.get("cdp", "deviceId") or "None"
            device_url = port.get("device", "url") or ""
            port_id = port.get("port_id")
            connected_port: str = port.get("lldp", "portId") or port.get("cdp", "portId") or "None"
            device_id = port.get("cdp", "deviceId") or "None"
            device_ip = port.get("cdp", "address") or port.get("lldp", "managementAddress")

            device_bar = None
            if "Meraki" in device_name or len(device_url) > 0:
                device_bar = (0, 0.8, 0, 1)
            elif connected_port.count("/") == 2:
                device_bar = (1, 0.7, 0.1, 1)
            elif device_name.startswith("SEP"):
                device_bar = (0.8, 0.8, 0.8, 1)
            else:
                device_bar = (0.3, 0.3, 0.3, 1)

            cx, cy = pygui.get_cursor_screen_pos()
            draw_list.add_rect_filled(
                (cx, cy),
                (cx + 5, cy + HEIGHT),
                pygui.color_convert_float4_to_u32(device_bar)
            )
            pygui.dummy((5, HEIGHT))
            pygui.same_line()

            pygui.begin_group()
            pygui.text("({} {}) -> {} ({})".format(
                port.get("port_iden"),
                port_id,
                device_name,
                connected_port,
            ))

            pygui.same_line()
            pygui.text_disabled("(?)")
            if pygui.is_item_hovered() and pygui.begin_tooltip():
                pygui.text(json.dumps(port.get_base(), indent=4))
                pygui.end_tooltip()

            device_id_unique = f"device {port_id} {device_id} {self.model}"
            device_ip_unique = f"ip {port_id} {device_ip} {self.model}"
            device_name_unique = f"name {port_id} {device_name} {connected_port} {self.model}"

            pygui.begin_group()
            text_copy(f"mac: {device_id}", device_id_unique, text_to_copy=device_id)
            text_copy(f"ip: {device_ip}", device_ip_unique,  text_to_copy=device_ip)
            pygui.end_group()
            pygui.same_line()
            text_copy(f"device: {device_name}", device_name_unique, text_to_copy=device_name)

            pygui.end_group()

    def __repr__(self):
        return json.dumps(self._raw, indent=4)


class Switch:
    class SwitchPort:
        def __init__(self, switch_name: str, port: dict):
            self._raw = port
            port = RelaxedDictionary(port)
            self.switch_name = switch_name
            self.portId = port.get("portId")
            self.name = port.get("name")
            self.tags = port.get("tags", [])
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

        def get_json(self) -> dict:
            return self._raw

        def get_default_sort(self):
            try:
                port_id = int(self.portId)
            except ValueError:
                port_id = self.portId

            return (self.switch_name, port_id)

        def get_column_field(self, idx: int):
            try:
                port_id = int(self.portId)
            except ValueError:
                port_id = self.portId

            field = [
                None,
                self.switch_name,
                port_id,
                self.name or "",
                self.type,
                self.vlan or 0,
                self.voiceVlan or 0,
                str(self.allowedVlans) or "",
                self.poeEnabled,
                self.stpGuard,
                self.rstpEnabled,
            ][idx]
            return field

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
                    pygui.text(str(self))
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
                pygui.invisible_button(str(hash(self)), (sz_x, sz_y))
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

            pygui.invisible_button(str(hash(self)), (sz_x, sz_y))
            show_tooltip()

        def __repr__(self):
            return json.dumps(self._raw, indent=4)

    def __init__(self, switch_info: RelaxedDictionary):
        self.name = switch_info.get("name")
        self.serial = switch_info.get("serial")
        self.mac = switch_info.get("mac")
        self.network_id = switch_info.get("network", "id")
        self.network_name = switch_info.get("network", "name")
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
            port_text = port_text[-6:]
            port_text_len = pygui.calc_text_size(port_text)[0]
            pygui.set_cursor_pos_x(
                pygui.get_cursor_pos_x() + width / 2 - port_text_len / 2)

            d = pygui.get_window_draw_list()
            d.add_text(
                pygui.get_cursor_screen_pos(),
                pygui.color_convert_float4_to_u32((0.4, 0.4, 0.4, 1)),
                port_text
            )
            pygui.dummy((1, pygui.get_text_line_height_with_spacing()))
            # pygui.text(port_text)

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

            if port_type == switch_profiles.p.SFP_Gap:
                pygui.dummy((SFP_WIDTH, PORT_HEIGHT))
                continue

            if port_type == switch_profiles.p.STACK_Gap:
                pygui.dummy((STACK_WIDTH, PORT_HEIGHT))
                continue

            # Draw the port
            assert port is not None
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
            if False and pygui.begin_drag_drop_source():
                pygui.set_drag_drop_payload("Port", port)
                port.draw(size, PORT_HEIGHT, is_first_line, sfp, stack)
                pygui.end_drag_drop_source()

            if not is_first_line:
                _show_port_text(port.portId, size)


            pygui.end_group()


class PortProfile:
    def __init__(self, port: Switch.SwitchPort):
        self.port = port
        self.included_fields = {f: pygui.Bool(True) for f in port.get_json().keys()}
        self.port_colour = pygui.Vec4(
            random.random(),
            random.random(),
            random.random(),
            1
        )

    def includes(self, other_port: Switch.SwitchPort):
        my_json = self.port.get_json()
        other_json = other_port.get_json()
        for field, is_selected in self.included_fields.items():
            if not is_selected:
                continue

            if my_json.get(field) != other_json.get(field):
                return False
        return True

    def draw(self):
        pygui.begin_group()
        self.port.draw(50, 50)
        pygui.color_edit4(f"Colour ##{hash(self)}", self.port_colour, pygui.COLOR_EDIT_FLAGS_NO_INPUTS)
        for field, is_selected in self.included_fields.items():
            pygui.checkbox(f"{field}: {self.port.get_json()[field]} ##{hash(self)}", is_selected)
        pygui.end_group()
