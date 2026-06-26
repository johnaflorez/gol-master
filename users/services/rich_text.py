import re

import tinycss2
from bleach import Cleaner
from bleach.css_sanitizer import CSSSanitizer


MAX_PROFILE_BIO_LENGTH = 5000

ALLOWED_TAGS = [
    "a",
    "blockquote",
    "br",
    "div",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "span",
    "strong",
    "b",
    "s",
    "u",
    "ul",
]

ALLOWED_ATTRIBUTES = {
    "a": ["href", "title"],
    "div": ["style"],
    "p": ["style"],
    "span": ["style"],
}

ALLOWED_CSS_PROPERTIES = [
    "background-color",
    "color",
    "font-size",
    "font-style",
    "font-weight",
    "text-align",
    "text-decoration",
]

CSS_DANGEROUS_VALUE_RE = re.compile(
    r"(expression\s*\(|url\s*\(|javascript:|data:|vbscript:|behavior\s*:|-moz-binding)",
    flags=re.IGNORECASE,
)
CSS_COLOR_RE = re.compile(
    r"^(#[0-9a-f]{3,8}|[a-z]+|rgba?\([0-9\s,%.]+\)|hsla?\([0-9\s,%.deg]+\))$",
    flags=re.IGNORECASE,
)
CSS_SIZE_RE = re.compile(r"^(\d+(?:\.\d+)?)(rem|em|px|%)$", flags=re.IGNORECASE)


class ProfileBioCSSSanitizer(CSSSanitizer):
    """CSS sanitizer that validates allowed style values, not only property names."""

    def sanitize_css(self, style):
        parsed = tinycss2.parse_declaration_list(style, skip_comments=True, skip_whitespace=True)
        safe_tokens = []

        for token in parsed:
            if token.type != "declaration" or token.lower_name not in self.allowed_css_properties:
                continue
            if self._is_safe_declaration(token.lower_name, tinycss2.serialize(token.value).strip()):
                safe_tokens.append(token)

        return tinycss2.serialize(safe_tokens).strip() if safe_tokens else ""

    def _is_safe_declaration(self, name, value):
        normalized_value = value.strip().lower()
        if not normalized_value or CSS_DANGEROUS_VALUE_RE.search(normalized_value):
            return False

        if name in {"background-color", "color"}:
            return bool(CSS_COLOR_RE.fullmatch(normalized_value))

        if name == "font-size":
            return self._is_safe_font_size(normalized_value)

        if name == "font-style":
            return normalized_value in {"normal", "italic", "oblique"}

        if name == "font-weight":
            return normalized_value in {"normal", "bold", "bolder", "lighter"} or normalized_value in {
                "100",
                "200",
                "300",
                "400",
                "500",
                "600",
                "700",
                "800",
                "900",
            }

        if name == "text-align":
            return normalized_value in {"left", "right", "center", "justify", "start", "end"}

        if name == "text-decoration":
            parts = set(normalized_value.split())
            return bool(parts) and parts <= {"none", "underline", "line-through", "overline"}

        return False

    def _is_safe_font_size(self, value):
        match = CSS_SIZE_RE.fullmatch(value)
        if not match:
            return value in {"small", "medium", "large", "larger", "smaller"}

        amount = float(match.group(1))
        unit = match.group(2).lower()
        max_by_unit = {"rem": 3, "em": 3, "px": 48, "%": 300}
        min_by_unit = {"rem": 0.5, "em": 0.5, "px": 8, "%": 50}
        return min_by_unit[unit] <= amount <= max_by_unit[unit]

PROFILE_BIO_CLEANER = Cleaner(
    tags=ALLOWED_TAGS,
    attributes=ALLOWED_ATTRIBUTES,
    protocols=["http", "https", "mailto"],
    css_sanitizer=ProfileBioCSSSanitizer(allowed_css_properties=ALLOWED_CSS_PROPERTIES),
    strip=True,
    strip_comments=True,
)

UNSAFE_BLOCK_RE = re.compile(
    r"<\s*(script|style|iframe|object|embed)\b[^>]*>.*?<\s*/\s*\1\s*>",
    flags=re.IGNORECASE | re.DOTALL,
)
EMPTY_STYLE_RE = re.compile(r"\sstyle=(['\"])\s*\1", flags=re.IGNORECASE)


def sanitize_profile_bio(value):
    """Return safe HTML for profile bios while preserving allowed rich formatting."""
    raw_value = (value or "").strip()
    if not raw_value:
        return ""
    raw_value = UNSAFE_BLOCK_RE.sub("", raw_value)
    cleaned_value = PROFILE_BIO_CLEANER.clean(raw_value).strip()
    return EMPTY_STYLE_RE.sub("", cleaned_value).strip()

