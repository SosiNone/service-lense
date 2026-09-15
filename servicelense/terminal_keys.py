"""Translate enhanced terminal keys for prompt_toolkit's legacy key names."""
from functools import cache

from prompt_toolkit.input.ansi_escape_sequences import ANSI_SEQUENCES
from prompt_toolkit.input.vt100_parser import _IS_PREFIX_OF_LONGER_MATCH_CACHE
from prompt_toolkit.keys import Keys


@cache
def register_keys() -> None:
    # Kitty's disambiguation mode also changes Ctrl+letters and Escape.
    # https://sw.kovidgoyal.net/kitty/keyboard-protocol/
    controls = {chr(n + 96): ANSI_SEQUENCES[chr(n)] for n in range(1, 27)}
    controls.update({" ": Keys.ControlAt, "@": Keys.ControlAt,
                     "[": Keys.Escape, "\\": Keys.ControlBackslash,
                     "]": Keys.ControlSquareClose, "^": Keys.ControlCircumflex,
                     "_": Keys.ControlUnderscore})
    functional = {9: Keys.Tab, 13: Keys.Enter, 27: Keys.Escape, 127: Keys.Backspace,
                  57414: Keys.Enter}
    functional.update(dict(zip(range(57417, 57427), [
        Keys.Left, Keys.Right, Keys.Up, Keys.Down, Keys.PageUp, Keys.PageDown,
        Keys.Home, Keys.End, Keys.Insert, Keys.Delete])))
    for code in sorted(set(range(128)) | functional.keys()):
        for modifier in range(1, 9):
            shift, alt, ctrl = (bool((modifier - 1) & bit) for bit in (1, 2, 4))
            # Unbound modified text keys are ignored, so their escape sequences
            # cannot leak into search/profile text or trigger tree shortcuts.
            key = functional.get(code, Keys.Ignore)
            if ctrl:
                key = controls.get(chr(code).lower(), Keys.Ignore)
                if code in {13, 57414}:
                    key = Keys.ControlJ  # Ctrl+Enter and the portable Ctrl+J fallback.
            elif shift and code == 9:
                key = Keys.BackTab
            if alt:
                key = Keys.Ignore
            ANSI_SEQUENCES.setdefault(f"\x1b[{code};{modifier}u", key)
            if modifier == 1:
                ANSI_SEQUENCES.setdefault(f"\x1b[{code}u", key)
    # Xterm's modifyOtherKeys encoding, when supplied by the terminal.
    ANSI_SEQUENCES["\x1b[27;5;13~"] = Keys.ControlJ
    _IS_PREFIX_OF_LONGER_MATCH_CACHE.clear()


class KeyboardMode:
    """Push enhanced keys inside the alternate screen, then pop before leaving."""
    def __init__(self):
        self.enabled = False

    def before_render(self, app):
        if app.is_done and self.enabled:
            app.output.write_raw("\x1b[<u")
            app.output.flush()
            self.enabled = False

    def after_render(self, app):
        if not app.is_done and not self.enabled and hasattr(app.input, "vt100_parser"):
            app.output.write_raw("\x1b[>1u")
            app.output.flush()
            self.enabled = True
