import pygui_cython as pygui
import pyperclip


_remember_dict = {}

def text_copy(
        text: str,
        unique_id: str,
        text_to_copy=None,
        reset_time=120
    ):
    to_copy = str(text_to_copy or text)

    if unique_id not in _remember_dict:
        _remember_dict[unique_id] = 0
    else:
        _remember_dict[unique_id] -= 1

    if _remember_dict[unique_id] > 0:
        pygui.button("Copied###{}".format(unique_id))
    elif pygui.button("Copy###{}".format(unique_id)):
        _remember_dict[unique_id] = reset_time
        pyperclip.copy(to_copy)
    pygui.same_line()
    pygui.text_disabled(text)
