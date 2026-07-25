import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

STACK = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "profile.yaml"


def _resolved():
    roster = render.load_roster(STACK / "roster.yaml")
    profile = render.load_profile(FIXTURE)
    return render.resolve_agents(roster, profile), profile


def test_unbound_slots_are_skipped():
    agents, _ = _resolved()
    names = sorted(a.name for a in agents)
    assert names == ["coder-primary", "reviewer-fast", "reviewer-primary"]


def test_agent_carries_role_permissions():
    agents, _ = _resolved()
    coder = next(a for a in agents if a.name == "coder-primary")
    reviewer = next(a for a in agents if a.name == "reviewer-primary")
    assert coder.write == "allow"
    assert coder.acceptance == "writer"
    assert reviewer.write == "deny"
    assert reviewer.acceptance == "read-only"


def test_provider_spelling_differs_per_harness():
    agents, profile = _resolved()
    coder = next(a for a in agents if a.name == "coder-primary")
    assert render.model_ref(coder, profile, "pi") == "prov-anthropic/model-big"
    assert render.model_ref(coder, profile, "opencode") == "anthropic-prov/model-big"


def test_emit_pi_frontmatter():
    agents, profile = _resolved()
    reviewer = next(a for a in agents if a.name == "reviewer-primary")
    fname, content = render.emit_pi(reviewer, profile)
    assert fname == "reviewer-primary.md"
    assert "name: reviewer-primary" in content
    assert "model: prov-anthropic/model-big" in content
    assert "acceptanceRole: read-only" in content
    assert "write" not in content.split("---")[1]
    assert "You are a strict code reviewer." in content


def test_emit_opencode_permissions():
    agents, profile = _resolved()
    reviewer = next(a for a in agents if a.name == "reviewer-primary")
    coder = next(a for a in agents if a.name == "coder-primary")
    _, rc = render.emit_opencode(reviewer, profile)
    _, cc = render.emit_opencode(coder, profile)
    assert "edit: deny" in rc
    assert "edit: allow" in cc
    assert "mode: subagent" in rc


def test_public_roster_names_slots_not_models():
    """roster.yaml ships in a PUBLIC repo, so it must describe abstract slots only.

    This asserts the positive shape rather than checking against a denylist of
    real model identifiers: a denylist would have to embed those identifiers in
    this file, publishing the very strings it exists to keep out.
    """
    roster = render.load_roster(STACK / "roster.yaml")
    known_slots = {"primary", "alt", "alt-xhigh", "fast"}
    for role, slots in roster["emit"].items():
        unknown = set(slots) - known_slots
        assert not unknown, f"{role} emits unknown slot(s): {sorted(unknown)}"

    for role, spec in roster["roles"].items():
        assert "model" not in spec, f"role {role} must not bind a model"

    text = (STACK / "roster.yaml").read_text()
    # A provider-qualified model reference looks like "<provider>/<model>".
    # The only legitimate slashes are prompt paths under prompts/.
    refs = [m for m in re.findall(r"\S+/\S+", text) if not m.startswith("prompts/")]
    assert refs == [], f"roster.yaml must not name concrete models: {refs}"
