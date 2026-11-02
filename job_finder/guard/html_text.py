"""Turn HTML into visible text while separating out what a human reader never sees."""
from __future__ import annotations

import re
from html.parser import HTMLParser
from typing import Dict, List, NamedTuple, Optional, Tuple

_VOID = {"br", "img", "input", "meta", "link", "hr", "wbr", "source", "area",
         "base", "col", "embed", "param", "track"}
_BLOCK = {"p", "div", "li", "ul", "ol", "h1", "h2", "h3", "h4", "h5", "h6", "tr",
          "br", "section", "article", "header", "footer", "table", "dl", "dt", "dd",
          "blockquote", "pre", "hr", "form", "fieldset", "main", "nav", "aside"}
_DROPPED = {"script", "style", "noscript", "svg", "template", "head", "title", "object",
            "audio", "video", "canvas", "iframe", "noframes"}
_IMPLIED_END = {"p", "li", "dd", "dt", "tr", "td", "th", "option"}
_CLOSES_P = _BLOCK - {"br", "hr"}

_NEWLINE = "\x00"  # sentinel: a block boundary, distinct from whitespace in the source

_CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_CSS_ESCAPE = re.compile(r"\\([0-9a-fA-F]{1,6})\s?|\\(.)", re.S)
_ZERO_LENGTH = re.compile(r"^[+-]?0*\.?0+(?:px|em|rem|pt|%|vw|vh|ex|ch)?$")
_NUMBER = re.compile(r"^\s*([+-]?\d*\.?\d+)\s*([a-z%]*)")
_OFFSCREEN_PROPS = {"left", "top", "right", "bottom", "text-indent", "margin-left", "margin-top"}
_OFFSCREEN_LOW, _OFFSCREEN_HIGH = -1000.0, 10000.0
_MIN_OPACITY = 0.1
_MIN_FONT_SIZE = {"px": 2.0, "pt": 1.5, "em": 0.15, "rem": 0.15, "ex": 0.3, "ch": 0.3,
                  "%": 10.0, "vw": 0.2, "vh": 0.2}
_MAX_SCALE = 0.05
_MAX_TRANSLATE = 1000.0


class HtmlText(NamedTuple):
    visible: str
    hidden: Tuple[str, ...]   # elements styled/marked as invisible
    dropped: Tuple[str, ...]  # comments, scripts, styles


def _decode_css_escapes(text: str) -> str:
    def replace(match: "re.Match[str]") -> str:
        if match.group(1):
            try:
                return chr(int(match.group(1), 16))
            except (ValueError, OverflowError):
                return ""
        return match.group(2)
    return _CSS_ESCAPE.sub(replace, text)


def _declarations(style: str) -> Dict[str, str]:
    props: Dict[str, str] = {}
    cleaned = _decode_css_escapes(_CSS_COMMENT.sub("", style)).lower()
    for part in cleaned.split(";"):
        name, _, value = part.partition(":")
        if name.strip():
            props[name.strip()] = value.replace("!important", "").strip()
    return props


def _number(value: str) -> Optional[Tuple[float, str]]:
    match = _NUMBER.match(value)
    return (float(match.group(1)), match.group(2)) if match else None


def _alpha_is_zero(token: str) -> bool:
    parsed = _number(token)
    if parsed is None:
        return False
    amount, unit = parsed
    return (amount / 100 if unit == "%" else amount) <= 0


def _color_invisible(value: str) -> bool:
    if value == "transparent":
        return True
    hex_color = re.fullmatch(r"#(?:[0-9a-f]{3}([0-9a-f])|[0-9a-f]{6}([0-9a-f]{2}))", value)
    if hex_color:
        alpha = hex_color.group(1) or hex_color.group(2)
        return int(alpha, 16) == 0
    if re.match(r"(?:rgb|hsl)a?\(", value) and ")" in value:
        inner = value[value.index("(") + 1:value.rindex(")")]
        if "/" in inner:
            return _alpha_is_zero(inner.split("/")[-1])
        parts = [p for p in re.split(r"[,\s]+", inner.strip()) if p]
        return len(parts) == 4 and _alpha_is_zero(parts[3])
    return False


def _font_too_small(value: str) -> bool:
    parsed = _number(value)
    if parsed is None:
        return False
    amount, unit = parsed
    if amount <= 0:
        return True
    return amount < _MIN_FONT_SIZE.get(unit, 0.0)


def _transform_hides(value: str) -> bool:
    scale = re.search(r"scale[xy]?\(\s*([+-]?\d*\.?\d+)", value)
    if scale and abs(float(scale.group(1))) <= _MAX_SCALE:
        return True
    shift = re.search(r"translate[xy]?\(\s*([+-]?\d*\.?\d+)", value)
    return bool(shift and abs(float(shift.group(1))) >= _MAX_TRANSLATE)


def _offscreen(props: Dict[str, str]) -> bool:
    for name in _OFFSCREEN_PROPS & props.keys():
        parsed = _number(props[name])
        if parsed and (parsed[0] <= _OFFSCREEN_LOW or parsed[0] >= _OFFSCREEN_HIGH):
            return True
    return False


def _style_hides(style: str) -> bool:
    props = _declarations(style)
    if props.get("display") == "none" or props.get("content-visibility") == "hidden":
        return True
    if props.get("visibility") in ("hidden", "collapse"):
        return True
    opacity = _number(props.get("opacity", ""))
    if opacity is not None and opacity[0] < _MIN_OPACITY:
        return True
    if _font_too_small(props.get("font-size", "")):
        return True
    if _color_invisible(props.get("color", "")):
        return True
    if re.search(r"inset\(\s*(?:50|100)%|circle\(\s*0", props.get("clip-path", "")):
        return True
    if re.search(r"rect\(\s*0", props.get("clip", "")):
        return True
    if _transform_hides(props.get("transform", "")) or _offscreen(props):
        return True
    collapsed = any(_ZERO_LENGTH.match(props.get(k, "x"))
                    for k in ("height", "width", "max-height", "max-width"))
    return collapsed and bool(re.search(r"hidden|clip", props.get("overflow", "")))


def _is_hidden(attrs: List[Tuple[str, Optional[str]]]) -> bool:
    # Browsers honour the first occurrence of a repeated attribute.
    names: Dict[str, str] = {}
    for name, value in attrs:
        names.setdefault(name, value or "")
    # aria-hidden only hides content from assistive tech; a sighted reader still sees it.
    return "hidden" in names or _style_hides(names.get("style", ""))


class _Extractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._stack: List[Tuple[str, str]] = []  # (tag, "visible" | "hidden" | "dropped")
        self._open: Dict[str, int] = {}
        self._chunks: Dict[str, List[str]] = {"visible": [], "hidden": [], "dropped": []}

    @property
    def _state(self) -> str:
        return self._stack[-1][1] if self._stack else "visible"

    def _newline(self) -> None:
        self._chunks[self._state].append(_NEWLINE)

    def _child_state(self, tag: str, attrs: List[Tuple[str, Optional[str]]]) -> str:
        if self._state != "visible":
            return self._state
        if tag in _DROPPED:
            return "dropped"
        return "hidden" if _is_hidden(attrs) else "visible"

    def handle_starttag(self, tag, attrs):
        if tag in _VOID:
            if tag in _BLOCK:
                self._newline()
            return
        top = self._stack[-1][0] if self._stack else ""
        if top in _IMPLIED_END and (tag == top or (top == "p" and tag in _CLOSES_P)):
            self._close_to(len(self._stack) - 1)
        if tag in _BLOCK:
            self._newline()
        self._stack.append((tag, self._child_state(tag, attrs)))
        self._open[tag] = self._open.get(tag, 0) + 1

    def handle_startendtag(self, tag, attrs):
        if tag in _BLOCK:
            self._newline()

    def _close_to(self, index: int) -> None:
        for closed, _ in self._stack[index:]:
            self._open[closed] -= 1
        del self._stack[index:]

    def handle_endtag(self, tag):
        # The counter makes an end tag with no matching start tag O(1); scanning
        # the stack for it would be quadratic on adversarial input.
        if self._open.get(tag, 0) > 0:
            for index in range(len(self._stack) - 1, -1, -1):
                if self._stack[index][0] == tag:
                    self._close_to(index)
                    break
        if tag in _BLOCK:
            self._newline()

    def handle_data(self, data):
        self._chunks[self._state].append(re.sub(r"\s+", " ", data))

    def handle_comment(self, data):
        self._chunks["dropped"].append(data)

    def result(self) -> HtmlText:
        def join(key: str) -> str:
            return "".join(self._chunks[key])
        return HtmlText(join("visible"), (join("hidden"),), (join("dropped"),))


def extract_html(markup: str) -> HtmlText:
    parser = _Extractor()
    parser.feed(markup)
    parser.close()
    return parser.result()


def fold_block_text(text: str) -> str:
    """Collapse the extractor's output into trimmed lines separated by single newlines."""
    lines = [re.sub(r" +", " ", part).strip() for part in re.split(f"{_NEWLINE}+", text)]
    return "\n".join(line for line in lines if line)
