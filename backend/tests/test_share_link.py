"""The share / join link.

The invite URL is the one artefact that leaves the host's machine, so it has
exactly two hard rules:

* it is a plain public URL - ``https://playoot.onrender.com/join?pin=123456``
  - built from ``window.location.origin`` so it works from any origin,
* it never carries a token, a JWT or any other credential, so copying it into
  a chat window cannot hand somebody the host session.

Everything else here (copy feedback, native share, the fallback path, the
remove-player confirmation) is asserted at source level, which is how this
suite checks the frontend: there is no JS test runner in this repo.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

FRONTEND_SRC = Path(__file__).resolve().parents[2] / "frontend" / "src"

# Every template literal that builds the invite URL must look exactly like
# ``${window.location.origin}/join?pin=${game.game_pin}``.
INVITE_TEMPLATE = re.compile(
    r"^`?\$\{window\.location\.origin\}/join\?pin=\$\{game\.game_pin\}`?$"
)
TEMPLATE_LITERAL = re.compile(r"`[^`]*`", re.DOTALL)


def _strip_comments(source: str) -> str:
    """Drop //, /* */ and JSX {/* */} comments.

    Guards written against raw text otherwise trip over prose like
    "no browser alert()" - the comment is telling the truth about the code,
    it is not the code.
    """
    source = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    kept = []
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith(("//", "*", "/*")):
            continue
        # A trailing `// note` never has a scheme right before it, so this
        # cannot eat `https://`.
        line = re.sub(r"\s//[^/].*$", "", line)
        kept.append(line)
    return "\n".join(kept)


def _require(name: str) -> Path:
    path = FRONTEND_SRC / name
    if not path.exists():
        pytest.skip("frontend sources are not available in this checkout")
    return path


def _read(name: str) -> str:
    return _require(name).read_text(encoding="utf-8")


def _code(name: str) -> str:
    """Source with comments removed - what the browser will actually run."""
    return _strip_comments(_read(name))


def _template_literals_containing(source: str, needle: str) -> list[str]:
    source = _strip_comments(source)
    return [m.group(0) for m in TEMPLATE_LITERAL.finditer(source) if needle in m.group(0)]


# ===========================================================================
# The URL itself
# ===========================================================================
def test_the_share_link_is_built_from_the_public_origin_only():
    source = _read("pages/HostLobbyPage.tsx")

    literals = _template_literals_containing(source, "/join?pin=")
    assert literals, "no share link template literal found in HostLobbyPage"

    for literal in literals:
        assert INVITE_TEMPLATE.match(literal), (
            "the share link must be `${window.location.origin}/join?pin="
            f"${{game.game_pin}}`, got {literal}"
        )


def test_the_share_link_never_carries_a_credential():
    """Copying the link must not export a host token, a JWT or a player token."""
    source = _read("pages/HostLobbyPage.tsx")

    for literal in _template_literals_containing(source, "/join?pin="):
        lowered = literal.lower()
        for forbidden in ("token", "jwt", "secret", "bearer", "authorization"):
            assert forbidden not in lowered, f"invite URL leaks `{forbidden}`: {literal}"

    # The clipboard payload is the URL state variable and nothing else.
    assert "navigator.clipboard.writeText(shareLink)" in source
    assert "input.value = shareLink;" in source


def test_the_join_route_is_registered_and_prefills_the_pin():
    app = _read("App.tsx")
    assert 'path="join"' in app, "the /join route must exist for the link to open"

    join_page = _read("pages/JoinPage.tsx")
    assert 'searchParams.get("pin")' in join_page, (
        "JoinPage must read ?pin= from the URL so a cold / incognito / "
        "other-device visit lands with the PIN already filled in"
    )
    assert "useSearchParams" in join_page


def test_the_link_opens_on_a_cold_load_not_just_on_navigation():
    """The URL must be handled by the router itself - no client-side-only
    deep link handling that a fresh browser tab would skip."""
    app = _read("App.tsx")
    assert 'path="join"' in app and "<JoinPage />" in app, (
        "the /join path must be routed to JoinPage"
    )
    # A bare `navigate()` deep link is not enough: the route itself must exist.
    assert re.search(r'<Route\s+path="join"', app), "join route missing from App.tsx"


# ===========================================================================
# Copy / share affordances
# ===========================================================================
def test_the_copy_button_copies_and_confirms_visibly():
    source = _read("pages/HostLobbyPage.tsx")
    code = _code("pages/HostLobbyPage.tsx")

    # Prominent copy control...
    assert "Copy Link" in source
    # ...with a visible inline confirmation, never a browser dialog.
    assert "Link copied!" in source
    assert 'role="status"' in source
    assert "alert(" not in code, "the share card must not use browser alert()"

    # Primary path plus the insecure-origin fallback.
    assert "navigator.clipboard && navigator.clipboard.writeText" in source
    assert 'document.execCommand("copy")' in source
    assert 'document.createElement("textarea")' in source


def test_the_native_share_api_is_offered_but_optional():
    source = _read("pages/HostLobbyPage.tsx")
    assert "navigator.share" in source
    # Guarded, so a browser without Web Share still gets the copy fallback.
    assert re.search(r"if\s*\(\s*navigator\.share\s*\)", source)
    assert "navigator.share" in source


def test_the_share_card_is_a_prominent_standalone_card():
    source = _read("pages/HostLobbyPage.tsx")

    # GAME PIN + SHARE LINK box + Copy/Share buttons, in its own card.
    assert "Game PIN" in source
    assert "Share link" in source
    assert "Share" in source
    assert "aria-label=\"Game join link\"" in source

    # It renders above the roster grid rather than as a tiny inline control.
    share_at = source.index("SHARE / JOIN")
    grid_at = source.index("MAIN GRID")
    assert share_at < grid_at, "the share card must come before the main grid"


# ===========================================================================
# Participant-removal confirmation (same page, same no-alert() rule)
# ===========================================================================
def test_removal_uses_a_dialog_with_cancel_and_remove_not_alert():
    source = _read("pages/HostLobbyPage.tsx")
    code = _code("pages/HostLobbyPage.tsx")

    assert "removeConfirm" in source, "the host must confirm before ejecting"
    assert "from this game?" in source, (
        "the confirmation must read `Remove <name> from this game?`"
    )
    assert "removeConfirm.nickname" in source, "the dialog must name the participant"

    # Cancel / Remove actions...
    assert "cancelRemovePlayer" in source
    assert "confirmRemovePlayer" in source
    # ...and no native dialog behind them.
    assert "alert(" not in code

    # The actual eject call goes through the REST endpoint (backend-authoritative).
    assert "api.removePlayer(" in source


def test_the_remove_player_endpoint_exists_on_the_backend():
    routes = (
        Path(__file__).resolve().parents[1] / "app" / "api" / "routes_game.py"
    ).read_text(encoding="utf-8")
    assert '@router.delete("/{pin}/players/{player_id}"' in routes
