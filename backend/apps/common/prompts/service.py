"""Prompt lookup and rendering.

The extraction pipeline renders a prompt and records which version produced the
result, so every entry in the wiki can say which prompt version extracted it.
"""

from string import Formatter

from apps.common.exceptions import PromptRenderError

from .models import PromptTemplate


def _active(key: str) -> PromptTemplate:
    try:
        template = PromptTemplate.objects.select_related("current_version").get(key=key)
    except PromptTemplate.DoesNotExist:
        raise PromptRenderError(f"PromptTemplate '{key}' not found") from None

    if template.current_version is None:
        raise PromptRenderError(f"PromptTemplate '{key}' has no active version")

    return template


def _placeholders(text: str) -> set[str]:
    """Variable names in *text*, honouring `{{`/`}}` escapes."""
    return {name for _, name, _, _ in Formatter().parse(text) if name}


def render(key: str, ctx: dict) -> str:
    """Return the active version of prompt *key* with `{var}` placeholders filled."""
    template = _active(key)
    text = template.current_version.text

    try:
        missing = sorted(_placeholders(text) - ctx.keys())
    except ValueError as exc:
        # `Formatter().parse` rejects an unbalanced brace before `format` ever
        # sees it. Same class of prompt bug as below, and it must not leave this
        # module as a bare ValueError.
        raise PromptRenderError(f"Cannot parse prompt '{key}': {exc}") from exc

    if missing:
        raise PromptRenderError(f"Missing template variables for '{key}': {missing}")

    try:
        return text.format(**ctx)
    except (IndexError, KeyError, ValueError) as exc:
        # Unbalanced or positional braces in the stored text — a prompt bug, not
        # a caller bug, so surface the key.
        raise PromptRenderError(f"Cannot render prompt '{key}': {exc}") from exc


def get_version(key: str) -> int:
    """Return the active `version_no` of prompt *key*.

    Snapshotted at the start of a run and written onto every `Evidence` row, so
    that later prompt edits don't retroactively relabel old extractions.
    """
    return _active(key).current_version.version_no
