from copy import deepcopy
import re
import sys
from pathlib import Path

import pytest

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


def test_model_ref_requires_provider_names_section():
    agents, profile = _resolved()
    coder = next(a for a in agents if a.name == "coder-primary")
    broken = dict(profile)
    del broken["provider_names"]

    with pytest.raises(render.ConfigError) as exc:
        render.model_ref(coder, broken, "pi")

    msg = str(exc.value)
    assert "profile.yaml" in msg
    assert "provider_names" in msg
    assert "pi" in msg


def test_model_ref_requires_harness_provider_names():
    agents, profile = _resolved()
    coder = next(a for a in agents if a.name == "coder-primary")

    with pytest.raises(render.ConfigError) as exc:
        render.model_ref(coder, profile, "missing-harness")

    assert "provider_names.missing-harness" in str(exc.value)


def test_model_ref_requires_provider_spelling():
    agents, profile = _resolved()
    coder = next(a for a in agents if a.name == "coder-primary")
    broken = deepcopy(profile)
    del broken["provider_names"]["opencode"][coder.provider]

    with pytest.raises(render.ConfigError) as exc:
        render.model_ref(coder, broken, "opencode")

    assert f"provider_names.opencode.{coder.provider}" in str(exc.value)


def test_load_profile_requires_existing_path(tmp_path):
    profile_path = tmp_path / "profile.yaml"

    with pytest.raises(render.ConfigError) as exc:
        render.load_profile(profile_path)

    assert f"No profile at {profile_path}" in str(exc.value)
    assert "Copy profile.example.yaml" in str(exc.value)


def test_resolve_agents_rejects_partially_bound_slots(tmp_path):
    roster = render.load_roster(STACK / "roster.yaml")
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "slots:\n"
        "  primary:\n"
        "    model: abstract-slot-model\n"
    )
    profile = render.load_profile(profile_path)

    with pytest.raises(render.ConfigError) as exc:
        render.resolve_agents(roster, profile)

    assert "slots.primary.provider" in str(exc.value)


def test_resolve_agents_rejects_partially_bound_slots_missing_model(tmp_path):
    roster = render.load_roster(STACK / "roster.yaml")
    profile_path = tmp_path / "profile.yaml"
    profile_path.write_text(
        "slots:\n"
        "  primary:\n"
        "    provider: abstract-slot-provider\n"
    )
    profile = render.load_profile(profile_path)

    with pytest.raises(render.ConfigError) as exc:
        render.resolve_agents(roster, profile)

    assert "slots.primary.model" in str(exc.value)


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


def _assert_public_roster_names_slots_not_models(path: Path):
    """roster.yaml ships in a PUBLIC repo, so it must describe abstract slots only.

    This asserts the positive shape rather than checking against a denylist of
    real model identifiers: a denylist would have to embed those identifiers in
    this file, publishing the very strings it exists to keep out.
    """
    roster = render.load_roster(path)
    document_keys = {"roles", "emit"}
    role_keys = {"prompt", "write", "bash", "acceptance"}
    known_slots = {"primary", "alt", "alt-xhigh", "fast"}

    assert set(roster) == document_keys, (
        f"roster.yaml has unsupported top-level key(s): {sorted(set(roster) - document_keys)}"
    )

    for role, slots in roster["emit"].items():
        unknown = set(slots) - known_slots
        assert not unknown, f"{role} emits unknown slot(s): {sorted(unknown)}"

    for role, spec in roster["roles"].items():
        assert set(spec) == role_keys, (
            f"role {role} keys must be {sorted(role_keys)}, got {sorted(spec)}"
        )

    text = path.read_text()
    # A provider-qualified model reference looks like "<provider>/<model>".
    # The only legitimate slashes are prompt paths under prompts/.
    refs = [m for m in re.findall(r"\S+/\S+", text) if not m.startswith("prompts/")]
    assert refs == [], f"roster.yaml must not name concrete models: {refs}"


def test_public_roster_names_slots_not_models():
    _assert_public_roster_names_slots_not_models(STACK / "roster.yaml")


def test_public_roster_rejects_top_level_leak(tmp_path):
    roster_path = tmp_path / "roster.yaml"
    roster_path.write_text(
        "roles:\n"
        "  coder:\n"
        "    prompt: prompts/coder.md\n"
        "    write: allow\n"
        "    bash: ask\n"
        "    acceptance: writer\n"
        "emit:\n"
        "  coder: [primary]\n"
        "endpoints:\n"
        "  primary: abstract-slot-label\n"
    )

    with pytest.raises(AssertionError) as exc:
        _assert_public_roster_names_slots_not_models(roster_path)

    assert "endpoints" in str(exc.value)


def test_public_roster_rejects_extra_role_keys(tmp_path):
    roster_path = tmp_path / "roster.yaml"
    roster_path.write_text(
        "roles:\n"
        "  coder:\n"
        "    prompt: prompts/coder.md\n"
        "    write: allow\n"
        "    bash: ask\n"
        "    acceptance: writer\n"
        "    model_id: abstract-slot-label\n"
        "emit:\n"
        "  coder: [primary]\n"
    )

    with pytest.raises(AssertionError) as exc:
        _assert_public_roster_names_slots_not_models(roster_path)

    assert "model_id" in str(exc.value)
