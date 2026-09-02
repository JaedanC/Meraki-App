from abc import ABC
from enum import Enum, auto
from typing import Tuple, List, Dict, Any, Callable, Optional
import json
import os

import pygui_cython as pygui

from extra.api import safe_open_w, dict_to_csv


class Sortable:
    def __init__(self, obj):
        self.obj = obj

    def __eq__(self, other):
        if self.obj is None:
            return True
        return str(other.obj) == str(self.obj)

    def __lt__(self, other):
        if self.obj is None:
            return True
        if type(self.obj) != type(other.obj):
            return str(other.obj) > str(self.obj)
        return other.obj > self.obj


class SortableNegative:
    # From: https://stackoverflow.com/a/75123782
    def __init__(self, obj):
        self.obj = obj

    def __eq__(self, other):
        if self.obj is None:
            return False
        return str(other.obj) == str(self.obj)

    def __lt__(self, other):
        if self.obj is None:
            return False
        if type(self.obj) != type(other.obj):
            return str(other.obj) < str(self.obj)
        return other.obj < self.obj


def text_widget(text: str, text_colour: int, width_colour: int):
    ROUNDING = 5
    text_size = pygui.calc_text_size(text)
    rect_width  = text_size[0] + ROUNDING
    rect_height = text_size[1]

    dl = pygui.get_window_draw_list()
    cx, cy = pygui.get_cursor_screen_pos()
    dl.add_rect_filled(
        (cx, cy),
        (cx + rect_width, cy + rect_height),
        width_colour,
        ROUNDING
    )
    dl.add_text(
        (cx + rect_width/2 - text_size[0]/2, cy + rect_height/2 - text_size[1]/2),
        text_colour,
        text
    )
    pygui.dummy((text_size[0] + ROUNDING, pygui.get_text_line_height()))


def IS_TERM_IN_FIELD(query: str, data_value: str) -> bool:
    query = query.replace("_", " ").lower()
    return query in data_value.lower()


def IS_TERM_EQUAL_TO_FIELD(query: str, data_value: str) -> bool:
    return query.lower() == data_value.lower()


def IS_VLAN_ALLOWED(query: str, data_value: str) -> bool:
    if query.startswith("a") and data_value == "all":
        return True
    
    vlans = data_value.split(",")
    return query in vlans


def IS_TAG_ON_DEVICE(query: str, data_value_tags: List[str]) -> bool:
    for tag in data_value_tags:
        if query.lower() in tag.lower():
            return True
    return False


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
    # query = query.lower()
    terms = {}
    for t in query.split(" "):
        if not any(delim in t for delim in [":", "!", "=", "!="]):
            terms[default] = (t.split("|"), True)
            continue

        if "!=" in t:
            t = t.split("!=", 1)
            terms[t[0]] = (t[1].split("|"), False)
        elif "!" in t:
            t = t.split("!", 1)
            terms[t[0]] = (t[1].split("|"), False)
        elif ":" in t:
            t = t.split(":", 1)
            terms[t[0]] = (t[1].split("|"), True)
        elif "=" in t:
            t = t.split("=", 1)
            terms[t[0]] = (t[1].split("|"), True)
    return terms


class Field:
    def __init__(
            self,
            field_match_func: Callable[[str, str], bool],
            field_types: type | Tuple[type],
            name: str,
            api_name: str,
        ):
        self.field_match_func = field_match_func
        self.field_types = field_types
        self.name = name
        self.api_name = api_name

    def sort_key(self, row: dict) -> Optional[Any]:
        """This can be overidden if you want this field to be sorted using
        some custom value"""
        return row[self.api_name]

    def draw(self, row: dict):
        """This can be overidden to customise how this field is drawn"""
        val = row[self.api_name]
        if val is not None:
            pygui.text_unformatted(str(val))

    def as_type(self, row: dict, fallback=str) -> Optional[Any]:
        """Attempts to convert an element in this field to:
        
            field_types: type | Tuple[type]
            
        If it's a tuple, it will go through the list until a conversion is found.
        If no suitable type is found, use the fallback."""
        obj = self.sort_key(row)
        if obj is None:
            return ""
        
        try:
            if isinstance(self.field_types, type):
                return self.field_types(obj)
        except (ValueError, TypeError):
            print(f"Cannot convert {obj} to type {self.field_types} fallingback to str()")
            return fallback(obj)

        for field_type in self.field_types:
            try:
                return field_type(obj)
            except (ValueError, TypeError):
                continue

        print(f"Cannot convert {obj} to type {self.field_types} fallingback to str()")
        return fallback(obj)

    def draw_boolean(self, row: dict):
        """Default reusable implementing of drawing a checkbox for booleans
        """
        pygui.begin_disabled()
        pygui.checkbox(
            "###enabled ".format(self.api_name),
            pygui.Bool(row[self.api_name])
        )
        pygui.end_disabled()


class Table(ABC):
    class HeadingStyle(Enum):
        Both = auto()
        NameOnly = auto()
        APIOnly = auto()
    """
    An abstracted Pygui table that can handle sorting, filtering, and rendering
    of the table.
    """
    def __init__(
            self,
            table_name: str,
            fields_spec: List[Field],
            data: List[dict]
        ):
        """
        ```
        e.g.
        fields_spec = [
            Field(IS_TAG_ON_DEVICE, str,       "Name",   "name"),
            Field(IS_TAG_ON_DEVICE, str,       "Serial", "serial"),
            Field(IS_TAG_ON_DEVICE, int | str, "MAC",    "portId"),
        ]
        ```

        `data` does not need to be a dictionary. By default each field uses
        Field.api_name as the key in to lookup inside data for the relevant
        value. If you need more customised behaviour, override each field's .draw
        and .sort_key methods. Then you can retrieve any value from your `data`
        and draw it however you want.
        """
        self._table_name = table_name
        self._fields_spec = fields_spec
        self._data = data
        self._filtered_data = data
        self._flags = \
            pygui.TABLE_FLAGS_RESIZABLE | \
            pygui.TABLE_FLAGS_REORDERABLE | \
            pygui.TABLE_FLAGS_HIDEABLE | \
            pygui.TABLE_FLAGS_SORTABLE | \
            pygui.TABLE_FLAGS_SORT_MULTI | \
            pygui.TABLE_FLAGS_ROW_BG | \
            pygui.TABLE_FLAGS_SCROLL_Y | \
            pygui.TABLE_FLAGS_SCROLL_X

        self._parsed_tokens = {}
        self.option_save_location = pygui.String("cache/getOrganizationSwitchPortsBySwitch.csv", buffer_size=2048)
        self.option_show_parsing = pygui.Bool(False)
        self.option_show_heading_style = pygui.Int(2) # API Only
        self.option_show_heading_styles = [
            ("Both",      Table.HeadingStyle.Both),
            ("Name Only", Table.HeadingStyle.NameOnly),
            ("API Only",  Table.HeadingStyle.APIOnly),
        ]

    def __len__(self) -> int:
        return len(self._data)

    def len_filtered(self) -> int:
        return len(self._filtered_data)

    def get_default_sort_field(self):
        return self._fields_spec[0]

    def _custom_key(self, element: dict) -> Tuple[Sortable | SortableNegative]:
        def _get_compare_obj_new(field: Field, row: dict):
            cell = field.as_type(row)
            if sort_spec.sort_direction == pygui.SORT_DIRECTION_ASCENDING:
                return Sortable(cell)
            else:
                return SortableNegative(cell)

        sort_specs = pygui.table_get_sort_specs()
        sort_with = []
        for sort_spec in sort_specs.specs:
            field = self._fields_spec[sort_spec.column_index]
            sort_with.append(_get_compare_obj_new(field, element))

        # Add a default sorting method
        default_sorting_field = self.get_default_sort_field()
        sort_with.append(_get_compare_obj_new(default_sorting_field, element))
        return tuple(sort_with)

    def sort(self):
        self._data.sort(key=self._custom_key)
        self._filtered_data.sort(key=self._custom_key)

    def draw_settings(self):
        if pygui.tree_node("Options"):
            if pygui.button("Open folder"):
                # Windows only
                os.startfile(os.path.abspath("cache"))
            pygui.same_line()
            if pygui.button("Save to csv"):
                try:
                    with safe_open_w(self.option_save_location.value) as f:
                        f.write(dict_to_csv([row for row in self._filtered_data]))
                        print("Saved to cache/getOrganizationSwitchPortsBySwitch.csv")
                except IOError as e:
                    print(e)
            pygui.same_line()
            pygui.input_text("###Save location", self.option_save_location)
            pygui.checkbox("Show filter parsing", self.option_show_parsing)
            if self.option_show_parsing:
                pygui.text_unformatted(json.dumps(self._parsed_tokens, indent=4))
            heading_options = [name for name, _ in self.option_show_heading_styles]
            pygui.push_item_width(100)
            pygui.combo("Heading style", self.option_show_heading_style, heading_options)
            pygui.pop_item_width()
            pygui.tree_pop()
            

    def draw(self):
        """
        Draw the table. Requires all rows to have the same height. Make sure no
        text includes newlines. If rows have unequal heights and the number of
        rows is short, consider using `.draw_unequal_height()`.
        """
        self.draw_settings()
        if pygui.begin_table(self._table_name, len(self._fields_spec), self._flags):
            # Declare columns
            for field in self._fields_spec:
                _, heading_style = self.option_show_heading_styles[self.option_show_heading_style.value]
                heading_style: Table.HeadingStyle
                if heading_style == Table.HeadingStyle.Both:
                    heading_name = field.name if len(self._data) == len(self._filtered_data) else f"{field.name} ({field.api_name})"
                elif heading_style == Table.HeadingStyle.NameOnly:
                    heading_name = field.name
                else:
                    heading_name = field.api_name
                pygui.table_setup_column(heading_name)
            pygui.table_setup_scroll_freeze(0, 1) # Make row always visible
            pygui.table_headers_row()

            if (sort_specs := pygui.table_get_sort_specs()):
                if sort_specs.specs_dirty:
                    self.sort()
                sort_specs.specs_dirty = False

            # Demonstrate using clipper for large vertical lists
            clipper: pygui.ImGuiListClipper = pygui.ImGuiListClipper.create()

            # This is our first example of not being able to share heap objects
            # across the dll. I need to get a pointer to a valid type that it
            # creates, not me. This requires adding a custom constructor and
            # destructor for the ImGuiListClipper class.
            clipper.begin(len(self._filtered_data))
            while clipper.step():
                for i in range(clipper.display_start, clipper.display_end):
                    pygui.push_id(i)
                    # Display a data item
                    row = self._filtered_data[i]
                    pygui.table_next_row()

                    for field in self._fields_spec:
                        pygui.push_id(field.api_name)
                        pygui.table_next_column()
                        field.draw(row)
                        pygui.pop_id()
                    pygui.pop_id()
            clipper.destroy()
            pygui.end_table()

    def draw_unequal_height(self):
        """
        This function draws the table, but enables row to have differing heights,
        at the expense of extra computation due to not using ImguiListClipper.
        Thus, unless there is a requirement for multi-height rows, use `.draw()`
        instead. Since this function must "submit" every row, consider the
        length of the table being drawn.
        """
        self.draw_settings()
        if pygui.begin_table(self._table_name, len(self._fields_spec), self._flags):
            # Declare columns
            for field in self._fields_spec:
                _, heading_style = self.option_show_heading_styles[self.option_show_heading_style.value]
                heading_style: Table.HeadingStyle
                if heading_style == Table.HeadingStyle.Both:
                    heading_name = field.name if len(self._data) == len(self._filtered_data) else f"{field.name} ({field.api_name})"
                elif heading_style == Table.HeadingStyle.NameOnly:
                    heading_name = field.name
                else:
                    heading_name = field.api_name
                pygui.table_setup_column(heading_name)
            pygui.table_setup_scroll_freeze(0, 1) # Make row always visible
            pygui.table_headers_row()

            if (sort_specs := pygui.table_get_sort_specs()):
                if sort_specs.specs_dirty:
                    self.sort()
                sort_specs.specs_dirty = False

            for row in self._filtered_data:
                pygui.push_id(row[self._fields_spec[0][2]])
                pygui.table_next_row()

                for field in self._fields_spec:
                    pygui.push_id(field.api_name)
                    pygui.table_next_column()
                    field.draw(row)
                    pygui.pop_id()

                pygui.pop_id()
            pygui.end_table()

    def reapply_filter(self, filter_string: str):
        """
        Call this function when you have a new filter string that you would like
        to use. This allows you to avoid parsing the string and filtering every
        frame which is wasteful.
        """
        default_field = self.get_default_sort_field()
        self._parsed_tokens = tokenise_query_into_dict(filter_string, default=default_field.api_name)

        to_keep = []
        for row in self._data:
            if self._should_show(row, self._parsed_tokens):
                to_keep.append(row)
        self._filtered_data = to_keep

    def _should_show(
            self,
            row: dict,
            parsed_tokens: Dict[str, Tuple[List[str], bool]],
        ) -> bool:
        """Only returns true if every query term passes the lookup function,
        otherwise returns False.
        """
        for field in self._fields_spec:
            if (query_and_is_negated := parsed_tokens.get(field.api_name)) is None:
                continue

            query_values, true_is_pass = query_and_is_negated
            field_value = row[field.api_name]

            if isinstance(field_value, list):
                field_value = [str(f).lower() for f in field_value]
            else:
                field_value = str(field_value).lower()
            
            for query_value in query_values:
                is_matching = field.field_match_func(query_value, field_value)

                if is_matching and true_is_pass:
                    continue
                elif not is_matching and not true_is_pass:
                    continue

                return False
        return True
