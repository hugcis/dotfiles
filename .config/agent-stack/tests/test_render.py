from copy import deepcopy
import re
import shlex
import shutil
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render

STACK = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).parent / "fixtures" / "profile.yaml"
ALL_SLOTS_FIXTURE = Path(__file__).parent / "fixtures" / "profile-all-slots.yaml"


def _resolved(fixture: Path = FIXTURE):
    roster = render.load_roster(STACK / "roster.yaml")
    profile = render.load_profile(fixture)
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


def test_final_test_audit_skill_is_stack_managed():
    skill = STACK / "skills" / "auditing-final-tests" / "SKILL.md"
    assert skill.is_file(), "final-test audit must be a canonical agent-stack skill"
    text = skill.read_text()
    assert "name: auditing-final-tests" in text
    assert "description: Use when" in text


def test_full_review_and_fix_wires_final_test_audit():
    skill = (STACK / "skills" / "full-review-and-fix" / "SKILL.md").read_text()
    reviewers = (STACK / "skills" / "full-review-and-fix" / "REVIEWERS.md").read_text()

    assert "final-test audit using `auditing-final-tests`" in skill
    assert "final-test audit reviewer" in skill
    assert "## Final-Test Audit" in reviewers
    assert "Use `auditing-final-tests`" in reviewers


def test_tdd_and_verification_reference_final_test_audit():
    tdd = (STACK / "skills" / "test-driven-development" / "SKILL.md").read_text()
    verification = (
        STACK / "skills" / "verification-before-completion" / "SKILL.md"
    ).read_text()

    assert "auditing-final-tests" in tdd
    assert "auditing-final-tests" in verification


def test_full_review_and_fix_has_scaling_contract():
    skill_dir = STACK / "skills" / "full-review-and-fix"
    skill = (skill_dir / "SKILL.md").read_text()
    reviewers = (skill_dir / "REVIEWERS.md").read_text()
    schema = skill_dir / "review-finding-schema.md"

    assert schema.is_file(), "review findings need a reusable schema artifact"
    schema_text = schema.read_text()
    for field in ("id", "severity", "confidence", "evidence", "fix_eligibility"):
        assert field in schema_text
    assert "## 2. Choose Review Mode" in skill
    assert "quick" in skill
    assert "standard" in skill
    assert "deep" in skill
    assert "wide" in skill
    assert "postfix" in skill
    assert "review-finding-schema.md" in skill
    assert "review-finding-schema.md" in reviewers


def test_review_finding_schema_is_public_safe():
    schema = (
        STACK / "skills" / "full-review-and-fix" / "review-finding-schema.md"
    ).read_text().lower()
    placeholders_for_private_details = {
        "private-marker",
        "internal-only-marker",
        "nonpublic-marker",
    }
    assert placeholders_for_private_details.isdisjoint(
        set(re.findall(r"[a-z0-9_-]+", schema))
    )


def test_pr_feedback_skill_set_is_stack_managed():
    expected = {
        "drafting-github-replies",
        "ci-red-triage",
        "pr-feedback-watch-loop",
    }
    for name in expected:
        skill = STACK / "skills" / name / "SKILL.md"
        assert skill.is_file(), f"{name} must be a canonical agent-stack skill"
        text = skill.read_text()
        assert f"name: {name}" in text
        assert "description: Use when" in text


def test_drafting_github_replies_forbids_posting():
    text = (STACK / "skills" / "drafting-github-replies" / "SKILL.md").read_text()

    assert "copy-pasteable draft" in text
    assert "Never post" in text
    assert "gh pr comment" in text
    assert "gh pr review" in text
    assert "gh api" in text
    assert "AI" not in text.split("## Rules", 1)[1]


def test_ci_red_triage_requires_logs_and_classification():
    text = (STACK / "skills" / "ci-red-triage" / "SKILL.md").read_text()

    for phrase in (
        "Do not guess from check names",
        "Fetch the exact failing job",
        "Classify the failure",
        "code regression",
        "stale branch",
        "unknown",
    ):
        assert phrase in text


def test_pr_feedback_watch_loop_composes_other_skills_and_uses_loops():
    text = (STACK / "skills" / "pr-feedback-watch-loop" / "SKILL.md").read_text()

    assert "LoopCreate" in text
    assert "MonitorCreate" in text
    assert "Do not use raw shell sleep loops" in text
    for skill in (
        "ci-red-triage",
        "receiving-code-review",
        "drafting-github-replies",
        "merging-main-resolving-conflicts",
        "verification-before-completion",
    ):
        assert skill in text


def test_new_pr_feedback_skills_are_public_safe():
    text = "\n".join(
        (STACK / "skills" / name / "SKILL.md").read_text().lower()
        for name in (
            "drafting-github-replies",
            "ci-red-triage",
            "pr-feedback-watch-loop",
        )
    )
    placeholders_for_private_details = {
        "private-marker",
        "internal-only-marker",
        "nonpublic-marker",
    }
    assert placeholders_for_private_details.isdisjoint(
        set(re.findall(r"[a-z0-9_-]+", text))
    )


def test_review_branch_uses_structured_finding_schema():
    skill_dir = STACK / "skills" / "review-branch"
    skill = (skill_dir / "SKILL.md").read_text()
    reviewers = (skill_dir / "REVIEWERS.md").read_text()

    assert "review-finding-schema.md" in skill
    assert "review-finding-schema.md" in reviewers
    assert "finding ID" in skill
    assert "Do not modify code" in skill


def test_rationalizing_code_comments_skill_is_stack_managed():
    skill = STACK / "skills" / "rationalizing-code-comments" / "SKILL.md"
    assert skill.is_file(), "comment rationalization must be a canonical skill"
    text = skill.read_text()

    assert "name: rationalizing-code-comments" in text
    assert "description: Use when" in text
    assert "verbose inline explanations" in text
    assert "why, not how" in text
    assert "delete" in text.lower()
    assert "compress" in text.lower()


def test_review_contracts_apply_comment_rationalization():
    for skill_name in ("full-review-and-fix", "review-branch"):
        reviewers = (STACK / "skills" / skill_name / "REVIEWERS.md").read_text()
        assert "rationalizing-code-comments" in reviewers
        assert "why, not how" in reviewers
        assert "Delete comments" in reviewers


def test_auditing_final_tests_curates_against_development_artifacts():
    """The gate has to keep saying how a useful RED-GREEN test becomes wrong.

    The four outcomes and the record schema are asserted by the gate suite; what
    is asserted here is the curation semantics an auditor applies to reach them.
    """
    text = (STACK / "skills" / "auditing-final-tests" / "SKILL.md").read_text()

    for phrase in (
        "durable behavior",
        "Merge duplicates unless each protects a distinct boundary.",
        "Exercise public behavior instead of private helpers when possible.",
        "Extract durable coverage from stabilization or graveyard files",
        "A test can help during RED-GREEN development and still be wrong for the "
        "final suite.",
    ):
        assert phrase in text


def test_comment_and_test_rationalization_are_public_safe():
    text = "\n".join(
        (STACK / "skills" / name / "SKILL.md").read_text().lower()
        for name in ("rationalizing-code-comments", "auditing-final-tests")
    )
    placeholders_for_private_details = {
        "private-marker",
        "internal-only-marker",
        "nonpublic-marker",
    }
    assert placeholders_for_private_details.isdisjoint(
        set(re.findall(r"[a-z0-9_-]+", text))
    )


def test_skill_provenance_record_is_public_safe():
    path = STACK / "skills" / "provenance.yaml"
    assert path.is_file()
    provenance = render.yaml.safe_load(path.read_text())

    assert provenance["version"] == 1
    skill_names = {
        path.parent.name for path in (STACK / "skills").glob("*/SKILL.md")
    }
    assert set(provenance["skills"]) == skill_names
    assert provenance["skills"]["diagnose"]["origin"] == "external-upstream"
    assert provenance["skills"]["write-a-skill"]["origin"] == "external-upstream"
    assert provenance["skills"]["full-review-and-fix"]["origin"] == "local-adapted"
    assert provenance["skills"]["ci-red-triage"]["origin"] == "local"
    assert provenance["skills"]["auditing-final-tests"]["origin"] == "local-adapted"
    assert provenance["skills"]["pr-feedback-watch-loop"]["origin"] == "local"

    text = path.read_text().lower()
    placeholders_for_private_details = {
        "private-marker",
        "internal-only-marker",
        "nonpublic-marker",
    }
    assert placeholders_for_private_details.isdisjoint(
        set(re.findall(r"[a-z0-9_-]+", text))
    )


def test_provenance_origins_are_declared_and_immutable_skills_keep_origins():
    """Origin decides edit rights, so immutable ownership changes must be explicit."""
    provenance = render.yaml.safe_load(
        (STACK / "skills" / "provenance.yaml").read_text()
    )
    declared = set(provenance["origins"])
    origins = {
        name: record["origin"] for name, record in provenance["skills"].items()
    }

    undeclared = sorted(n for n, o in origins.items() if o not in declared)
    assert undeclared == [], f"skills carry an undeclared origin: {undeclared}"

    locally_owned = {"local", "local-adapted"}
    assert locally_owned <= declared, "local ownership categories must stay declared"

    immutable_origin_names = {"inherited-process", "external-upstream"}
    expected_immutable_origins = frozenset(
        {
            ("brainstorming", "inherited-process"),
            ("diagnose", "external-upstream"),
            ("dispatching-parallel-agents", "inherited-process"),
            ("evaluate-codebase", "inherited-process"),
            ("executing-plans", "inherited-process"),
            ("finishing-a-development-branch", "inherited-process"),
            ("grill-me", "external-upstream"),
            ("grill-with-docs", "external-upstream"),
            ("merging-main-resolving-conflicts", "inherited-process"),
            ("receiving-code-review", "inherited-process"),
            ("requesting-code-review", "inherited-process"),
            ("subagent-driven-development", "inherited-process"),
            ("systematic-debugging", "inherited-process"),
            ("test-driven-development", "inherited-process"),
            ("using-git-worktrees", "inherited-process"),
            ("using-superpowers", "inherited-process"),
            ("verification-before-completion", "inherited-process"),
            ("write-a-skill", "external-upstream"),
            ("writing-plans", "inherited-process"),
            ("writing-skills", "inherited-process"),
        }
    )
    actual_immutable_origins = frozenset(
        (name, origin)
        for name, origin in origins.items()
        if origin in immutable_origin_names
    )
    assert actual_immutable_origins == expected_immutable_origins, (
        "inherited-process and external-upstream origins are an explicit immutable "
        "contract; update this contract for an intentional ownership change"
    )


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


def _parse_flat_toml(content: str) -> dict:
    """Parse the small flat TOML shape emitted by emit_vibe."""
    document = {}
    current = document
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            current = document
            for part in line[1:-1].split("."):
                current = current.setdefault(part, {})
            continue
        key, value = [part.strip() for part in line.split("=", 1)]
        if value.startswith('"') and value.endswith('"'):
            value = value[1:-1]
        current[key] = value
    return document


def _assert_vibe_permissions(content: str, *, safety: str, write_permission: str):
    document = _parse_flat_toml(content)
    assert document["agent_type"] == "subagent"
    assert document["safety"] == safety
    assert set(document["tools"]) == {"bash", "write_file", "edit"}
    assert document["tools"]["bash"]["permission"] == "ask"
    assert document["tools"]["write_file"]["permission"] == write_permission
    assert document["tools"]["edit"]["permission"] == write_permission


def test_emit_filename_stems_match_agent_identity_across_harnesses():
    agents, profile = _resolved()
    for agent in agents:
        emitted = [
            render.emit_vibe(agent),
            render.emit_pi(agent, profile),
            render.emit_opencode(agent, profile),
            render.emit_claude(agent),
        ]
        assert [Path(fname).stem for fname, _ in emitted] == [agent.name] * len(emitted)


def test_emit_vibe_is_subagent_only_and_reviewer_is_safe_read_only():
    agents, _ = _resolved()
    reviewer = next(a for a in agents if a.name == "reviewer-primary")
    _, content = render.emit_vibe(reviewer)
    _assert_vibe_permissions(content, safety="safe", write_permission="never")


def test_emit_vibe_coder_is_destructive_and_writable():
    agents, _ = _resolved()
    coder = next(a for a in agents if a.name == "coder-primary")
    _, content = render.emit_vibe(coder)
    _assert_vibe_permissions(content, safety="destructive", write_permission="always")


def test_emit_claude_frontmatter():
    agents, profile = _resolved()
    reviewer = next(a for a in agents if a.name == "reviewer-primary")
    fname, content = render.emit_claude(reviewer)
    assert fname == "reviewer-primary.md"
    assert "name: reviewer-primary" in content
    assert "You are a strict code reviewer." in content


def test_methodology_name_defaults_to_superpowers():
    assert render.methodology_name({}) == "superpowers"


def test_methodology_name_accepts_compound_engineering():
    assert render.methodology_name({"methodology": "compound-engineering"}) == "compound-engineering"


def test_methodology_name_rejects_unknown_value():
    with pytest.raises(render.ConfigError, match="methodology"):
        render.methodology_name({"methodology": "unknown"})


@pytest.mark.parametrize(
    "value",
    [["superpowers"], {"superpowers": None}, 3, None],
    ids=["list", "dict", "int", "null"],
)
def test_methodology_name_rejects_non_string_value(value):
    with pytest.raises(render.ConfigError, match="methodology"):
        render.methodology_name({"methodology": value})


@pytest.mark.parametrize("name", sorted(render.METHODOLOGY_FRAGMENTS))
def test_every_mapped_methodology_is_selectable_and_renders(name):
    profile = render.load_profile(FIXTURE)
    profile["methodology"] = name

    assert render.methodology_name(profile) == name
    assert render.compose_agents_md(profile).strip()


def test_compose_agents_md_selects_exactly_one_methodology():
    profile = render.load_profile(FIXTURE)
    profile["methodology"] = "compound-engineering"
    text = render.compose_agents_md(profile)
    assert "Compound Engineering Workflow" in text
    assert "Superpowers Skill Use" not in text
    assert "~/docs/<repository-identity>" in text


def test_compose_agents_md_includes_extra_fragments(tmp_path):
    extra = STACK / "agents.md.d" / "_test_fragment.md"
    extra.write_text("WORK ONLY MARKER\n")
    try:
        profile = render.load_profile(FIXTURE)
        profile["methodology"] = "superpowers"
        profile["agents_md_extra"] = ["_test_fragment.md"]
        text = render.compose_agents_md(profile)
        assert "Superpowers Skill Use" in text
        assert "WORK ONLY MARKER" in text
    finally:
        extra.unlink()


@pytest.mark.parametrize(
    "selected,extra",
    [
        ("superpowers", "10-compound-engineering.md"),
        ("compound-engineering", "10-superpowers.md"),
        ("superpowers", "10-superpowers.md"),
        ("compound-engineering", "10-compound-engineering.md"),
        ("superpowers", "./10-compound-engineering.md"),
        ("compound-engineering", "../agents.md.d/10-superpowers.md"),
    ],
    ids=[
        "opposite-ce",
        "opposite-sp",
        "duplicate-sp",
        "duplicate-ce",
        "dot-alias",
        "parent-alias",
    ],
)
def test_compose_agents_md_rejects_methodology_fragment_in_extra(selected, extra):
    profile = render.load_profile(FIXTURE)
    profile["methodology"] = selected
    profile["agents_md_extra"] = [extra]

    with pytest.raises(render.ConfigError) as exc:
        render.compose_agents_md(profile)

    msg = str(exc.value)
    assert extra in msg
    assert "methodology" in msg


def test_compose_agents_md_rejects_fragment_path_outside_directory():
    outside = STACK / "_test_outside_fragment.md"
    outside.write_text("OUTSIDE MARKER\n")
    try:
        profile = render.load_profile(FIXTURE)
        profile["agents_md_extra"] = ["../_test_outside_fragment.md"]

        with pytest.raises(render.ConfigError) as exc:
            render.compose_agents_md(profile)

        assert "must stay within" in str(exc.value)
    finally:
        outside.unlink()


def test_compose_agents_md_missing_fragment_raises_config_error():
    profile = render.load_profile(FIXTURE)
    profile["agents_md_extra"] = ["_no_such_fragment.md"]

    with pytest.raises(render.ConfigError) as exc:
        render.compose_agents_md(profile)

    msg = str(exc.value)
    assert "_no_such_fragment.md" in msg
    assert str(STACK / "agents.md.d") in msg


def test_composed_agents_md_does_not_reference_unavailable_trash_tools():
    extra = STACK / "agents.md.d" / "_test_no_unavailable_trash_tools.md"
    extra.write_text("Avoid destructive cleanup unless explicitly disposable.\n")
    try:
        profile = render.load_profile(FIXTURE)
        profile["agents_md_extra"] = [extra.name]

        assert "vtrash" not in render.compose_agents_md(profile)
    finally:
        extra.unlink()


def test_composed_agents_md_requires_signed_commits_and_socket_recovery():
    text = render.compose_agents_md(render.load_profile(FIXTURE))

    assert "Always keep git commit signing enabled" in text
    assert "do not bypass" in text
    assert "--no-gpg-sign" in text
    assert "commit.gpgsign=false" in text
    assert "SSH_AUTH_SOCK" in text
    assert "/tmp/ssh-*/agent.*" in text
    assert "ssh-add -l" in text


def test_prune_stale_moves_unknown_files_aside(tmp_path):
    target = tmp_path / "agents"
    target.mkdir()
    (target / "reviewer-primary.md").write_text("keep")
    (target / "legacy-coder.md").write_text("stale")
    moved = render.prune_stale(target, {"reviewer-primary.md"})
    assert moved == ["legacy-coder.md"]
    assert (target / "reviewer-primary.md").read_text() == "keep"
    assert not (target / "legacy-coder.md").exists()
    backups = list(tmp_path.glob("agents.pre-render-*/legacy-coder.md"))
    assert len(backups) == 1, "stale file must be preserved, not deleted"
    assert backups[0].read_text() == "stale", "backup must keep the original content"


def test_prune_stale_back_to_back_keeps_both_backups(tmp_path):
    """Two renders in the same second must not overwrite each other's backup."""
    target = tmp_path / "agents"
    target.mkdir()

    (target / "legacy-coder.md").write_text("first generation")
    assert render.prune_stale(target, set()) == ["legacy-coder.md"]
    (target / "legacy-coder.md").write_text("second generation")
    assert render.prune_stale(target, set()) == ["legacy-coder.md"]

    backups = sorted(tmp_path.glob("agents.pre-render-*/legacy-coder.md"))
    assert len(backups) == 2, "each prune needs its own backup directory"
    assert sorted(p.read_text() for p in backups) == [
        "first generation",
        "second generation",
    ]


def test_prune_stale_refuses_to_clobber_an_existing_backup_file(tmp_path, monkeypatch):
    target = tmp_path / "agents"
    target.mkdir()
    (target / "legacy-coder.md").write_text("stale")
    occupied = tmp_path / "occupied"
    occupied.mkdir()
    (occupied / "legacy-coder.md").write_text("someone else's backup")
    monkeypatch.setattr(render.tempfile, "mkdtemp", lambda **kwargs: str(occupied))

    with pytest.raises(FileExistsError):
        render.prune_stale(target, set())

    assert (target / "legacy-coder.md").read_text() == "stale"
    assert (occupied / "legacy-coder.md").read_text() == "someone else's backup"


def test_prune_stale_is_a_noop_when_nothing_is_stale(tmp_path):
    target = tmp_path / "agents"
    target.mkdir()
    (target / "reviewer-primary.md").write_text("keep")
    assert render.prune_stale(target, {"reviewer-primary.md"}) == []
    assert not list(tmp_path.glob("agents.pre-render-*"))


def test_profile_env_contains_endpoints():
    profile = render.load_profile(FIXTURE)
    env = render.render_profile_env(profile)
    assert "ANTHROPIC_FOUNDRY_BASE_URL='https://example.test/anthropic'" in env
    assert "CLAUDE_CODE_USE_VERTEX" not in env


def test_profile_env_quotes_hostile_values():
    profile = render.load_profile(FIXTURE)
    hostile = "it's a; rm -rf $HOME `boom`"
    profile["env"] = {"SOME_TOKEN": hostile}
    profile["endpoints"] = dict(profile["endpoints"], anthropic=hostile)

    env = render.render_profile_env(profile)

    exports = {}
    for line in env.splitlines():
        if not line.startswith("export "):
            continue
        words = shlex.split(line)  # raises on unbalanced quoting
        assert len(words) == 2, f"line does not survive shell word splitting: {line}"
        key, _, value = words[1].partition("=")
        exports[key] = value
    assert exports["SOME_TOKEN"] == hostile
    assert exports["ANTHROPIC_FOUNDRY_BASE_URL"] == hostile


@pytest.mark.parametrize("key", ["2BAD", "HAS-DASH", "HAS SPACE", "", "X;rm -rf /"])
def test_profile_env_rejects_illegal_export_keys(key):
    profile = render.load_profile(FIXTURE)
    profile["env"] = {key: "value"}

    with pytest.raises(render.ConfigError) as exc:
        render.render_profile_env(profile)

    assert key in str(exc.value)
    assert "shell identifier" in str(exc.value)


def _sandbox(tmp_path, monkeypatch) -> dict:
    """Redirect every write target into tmp_path. Never touch a real harness dir."""
    stack = tmp_path / "stack"
    stack.mkdir()
    shutil.copytree(STACK / "prompts", stack / "prompts")
    (stack / "agents.md.d").mkdir()
    for fragment in ("00-universal.md", *sorted(render.METHODOLOGY_FRAGMENTS.values())):
        shutil.copy(STACK / "agents.md.d" / fragment, stack / "agents.md.d")
    monkeypatch.setattr(render, "STACK", stack)

    home = tmp_path / "home"
    targets = {h: home / h / "agents" for h in ("pi", "opencode", "vibe", "claude")}
    monkeypatch.setattr(render, "TARGETS", targets)
    monkeypatch.setattr(render, "AGENTS_MD_TARGETS", [home / "pi" / "AGENTS.md"])
    monkeypatch.setattr(render, "BACKUP_ROOT", tmp_path / "backups")
    return {"stack": stack, "home": home, "targets": targets}


def _tree_contents(root: Path) -> dict[str, bytes | None]:
    return {
        str(path.relative_to(root)): path.read_bytes() if path.is_file() else None
        for path in root.rglob("*")
    }


def test_validate_builds_every_output_without_writing(tmp_path, monkeypatch, capsys):
    box = _sandbox(tmp_path, monkeypatch)
    shutil.copy(STACK / "roster.yaml", box["stack"] / "roster.yaml")
    profile = box["stack"] / "profile.yaml"
    shutil.copy(FIXTURE, profile)
    before = _tree_contents(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["render.py", "validate", "--profile", str(profile)]
    )

    render.main()

    assert _tree_contents(tmp_path) == before
    assert capsys.readouterr().out == "agent-stack render validation: ok\n"


def test_validate_reports_late_phase_one_errors_without_writing(
    tmp_path, monkeypatch
):
    box = _sandbox(tmp_path, monkeypatch)
    shutil.copy(STACK / "roster.yaml", box["stack"] / "roster.yaml")
    profile = box["stack"] / "profile.yaml"
    profile.write_text(FIXTURE.read_text() + "env:\n  ILLEGAL-KEY: value\n")
    before = _tree_contents(tmp_path)
    monkeypatch.setattr(
        sys, "argv", ["render.py", "validate", "--profile", str(profile)]
    )

    with pytest.raises(SystemExit, match="shell identifier"):
        render.main()

    assert _tree_contents(tmp_path) == before


def test_write_all_writes_and_prunes(tmp_path, monkeypatch):
    box = _sandbox(tmp_path, monkeypatch)
    stale = box["targets"]["pi"] / "legacy-coder.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("hand written")
    roster = render.load_roster(STACK / "roster.yaml")

    render.write_all(roster, render.load_profile(FIXTURE))

    for directory in box["targets"].values():
        assert sorted(p.stem for p in directory.iterdir() if p.is_file()) == [
            "coder-primary",
            "reviewer-fast",
            "reviewer-primary",
        ]
    assert (box["home"] / "pi" / "AGENTS.md").exists()
    assert (box["stack"] / "profile.env").exists()
    backups = list((box["home"] / "pi").glob("agents.pre-render-*/legacy-coder.md"))
    assert [p.read_text() for p in backups] == ["hand written"]


def test_write_all_writes_nothing_when_an_agents_md_fragment_is_missing(
    tmp_path, monkeypatch
):
    box = _sandbox(tmp_path, monkeypatch)
    stale = box["targets"]["pi"] / "legacy-coder.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("hand written")
    roster = render.load_roster(STACK / "roster.yaml")
    profile = render.load_profile(FIXTURE)
    profile["agents_md_extra"] = ["_no_such_fragment.md"]

    with pytest.raises(render.ConfigError) as exc:
        render.write_all(roster, profile)

    assert "_no_such_fragment.md" in str(exc.value)
    assert [p.name for p in box["targets"]["pi"].iterdir()] == ["legacy-coder.md"]
    assert stale.read_text() == "hand written", "nothing may move before validation"
    for harness in ("opencode", "vibe", "claude"):
        assert not box["targets"][harness].exists()
    assert not (box["home"] / "pi" / "AGENTS.md").exists()
    assert not (box["stack"] / "profile.env").exists()


def test_write_all_writes_nothing_when_a_slot_binding_is_broken(tmp_path, monkeypatch):
    box = _sandbox(tmp_path, monkeypatch)
    roster = render.load_roster(STACK / "roster.yaml")
    profile = deepcopy(render.load_profile(FIXTURE))
    del profile["provider_names"]["opencode"]["anthropic"]

    with pytest.raises(render.ConfigError):
        render.write_all(roster, profile)

    for directory in box["targets"].values():
        assert not directory.exists()
    assert not (box["stack"] / "profile.env").exists()


# --- thinking: each harness expresses a reasoning level differently ---------


def _reviewer(slot: str):
    agents, profile = _resolved(ALL_SLOTS_FIXTURE)
    return next(a for a in agents if a.name == f"reviewer-{slot}"), profile


def _strip_identity(agent, content: str) -> str:
    """Blank out everything that differs between two agents purely by name.

    What is left is the substantive configuration, so an assertion on it cannot
    pass just because the two files spell a different agent name.
    """
    for token, placeholder in (
        (agent.name.replace("-", " ").title(), "TITLE"),
        (agent.name, "AGENT"),
        (agent.slot, "SLOT"),
    ):
        content = content.replace(token, placeholder)
    return content


def test_alt_and_alt_xhigh_render_differently_in_every_harness():
    """The two reviewer slots share a model id and differ only in `thinking`.

    All four harnesses can express a reasoning level, each in its own way, so
    every one of them must produce a substantively different file. If a harness
    ever loses that ability this test is where it shows up, instead of the two
    agents silently collapsing into byte-identical copies.
    """
    high, profile = _reviewer("alt")
    xhigh, _ = _reviewer("alt-xhigh")
    assert high.model == xhigh.model, "fixture must isolate thinking as the variable"

    emitters = {
        "pi": lambda a: render.emit_pi(a, profile)[1],
        "opencode": lambda a: render.emit_opencode(a, profile)[1],
        "vibe": lambda a: render.emit_vibe(a)[1],
        "claude": lambda a: render.emit_claude(a)[1],
    }
    for harness, emit in emitters.items():
        assert _strip_identity(high, emit(high)) != _strip_identity(xhigh, emit(xhigh)), (
            f"{harness} renders alt and alt-xhigh identically: thinking is dropped"
        )


def test_emit_pi_appends_thinking_as_a_model_ref_suffix():
    high, profile = _reviewer("alt")
    xhigh, _ = _reviewer("alt-xhigh")
    assert "model: prov-openai/model-mid:high\n" in render.emit_pi(high, profile)[1]
    assert "model: prov-openai/model-mid:xhigh\n" in render.emit_pi(xhigh, profile)[1]


def test_emit_opencode_sets_the_model_variant():
    high, profile = _reviewer("alt")
    xhigh, _ = _reviewer("alt-xhigh")
    assert "variant: high\n" in render.emit_opencode(high, profile)[1]
    assert "variant: xhigh\n" in render.emit_opencode(xhigh, profile)[1]


def test_emit_claude_sets_the_effort_level():
    high, _ = _reviewer("alt")
    xhigh, _ = _reviewer("alt-xhigh")
    assert "effort: high\n" in render.emit_claude(high)[1]
    assert "effort: xhigh\n" in render.emit_claude(xhigh)[1]


def test_emit_vibe_selects_the_thinking_bearing_model_alias():
    """Vibe holds `thinking` on the [[models]] alias, not on the agent.

    So the agent expresses a reasoning level only by pointing active_model at an
    alias that carries one; the optional profile key `vibe_model` names it.
    """
    high, _ = _reviewer("alt")
    xhigh, _ = _reviewer("alt-xhigh")
    assert 'active_model = "model-mid-high-alias"' in render.emit_vibe(high)[1]
    assert 'active_model = "model-mid-xhigh-alias"' in render.emit_vibe(xhigh)[1]


def test_emit_vibe_falls_back_to_model_when_vibe_model_is_absent():
    primary, _ = _reviewer("primary")
    assert primary.vibe_model is None
    assert 'active_model = "model-big"' in render.emit_vibe(primary)[1]


def test_a_slot_without_thinking_emits_no_reasoning_field():
    fast, profile = _reviewer("fast")
    assert fast.thinking is None
    assert "model: prov-openai/model-small\n" in render.emit_pi(fast, profile)[1]
    assert "variant:" not in render.emit_opencode(fast, profile)[1]
    assert "effort:" not in render.emit_claude(fast)[1]


# --- AGENTS.md: aliased targets and pre-overwrite backups ------------------


def test_distinct_agents_md_targets_collapses_a_symlink_alias(tmp_path):
    """~/.pi/agent/AGENTS.md is a symlink to ~/.vibe/AGENTS.md on the live box."""
    real = tmp_path / "vibe" / "AGENTS.md"
    real.parent.mkdir(parents=True)
    real.write_text("shared")
    alias_dir = tmp_path / "pi"
    alias_dir.mkdir()
    alias = alias_dir / "AGENTS.md"
    alias.symlink_to(real)
    other = tmp_path / "opencode" / "AGENTS.md"
    other.parent.mkdir()

    distinct = render.distinct_agents_md_targets([alias, real, other])

    assert distinct == [real.resolve(), other.resolve()]


def test_backup_agents_md_preserves_content_it_is_about_to_clobber(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "BACKUP_ROOT", tmp_path / "backups")
    target = tmp_path / "claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.write_text("hand written by the user")

    saved = render.backup_agents_md([target], "rendered")

    assert len(saved) == 1
    assert Path(saved[0]).read_text() == "hand written by the user"
    assert target.read_text() == "hand written by the user", "backup must not move it"


def test_backup_agents_md_is_a_noop_when_content_already_matches(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "BACKUP_ROOT", tmp_path / "backups")
    target = tmp_path / "vibe" / "AGENTS.md"
    target.parent.mkdir()
    target.write_text("rendered")

    assert render.backup_agents_md([target], "rendered") == []
    assert not (tmp_path / "backups").exists(), "an unchanged render must not litter"


def test_backup_agents_md_uses_one_directory_per_render(tmp_path, monkeypatch):
    """Two targets share the basename AGENTS.md, so names must stay distinct."""
    monkeypatch.setattr(render, "BACKUP_ROOT", tmp_path / "backups")
    first = tmp_path / "vibe" / "AGENTS.md"
    second = tmp_path / "opencode" / "AGENTS.md"
    for path, text in ((first, "vibe copy"), (second, "opencode copy")):
        path.parent.mkdir()
        path.write_text(text)

    saved = [Path(p) for p in render.backup_agents_md([first, second], "rendered")]

    assert len({p.parent for p in saved}) == 1, "one backup directory per render"
    assert len({p.name for p in saved}) == 2, "same-basename targets must not collide"
    assert sorted(p.read_text() for p in saved) == ["opencode copy", "vibe copy"]


def test_backup_agents_md_back_to_back_keeps_both_generations(tmp_path, monkeypatch):
    monkeypatch.setattr(render, "BACKUP_ROOT", tmp_path / "backups")
    target = tmp_path / "claude" / "CLAUDE.md"
    target.parent.mkdir()

    target.write_text("first generation")
    assert render.backup_agents_md([target], "rendered")
    target.write_text("second generation")
    assert render.backup_agents_md([target], "rendered")

    backups = sorted((tmp_path / "backups").glob("agents-md.pre-render-*/*"))
    assert sorted(p.read_text() for p in backups) == [
        "first generation",
        "second generation",
    ]


def test_write_all_backs_up_and_deduplicates_agents_md(tmp_path, monkeypatch):
    box = _sandbox(tmp_path, monkeypatch)
    real = box["home"] / "vibe" / "AGENTS.md"
    real.parent.mkdir(parents=True)
    real.write_text("hand written, untracked, irreplaceable")
    alias_dir = box["home"] / "pi"
    alias_dir.mkdir(parents=True)
    alias = alias_dir / "AGENTS.md"
    alias.symlink_to(real)
    monkeypatch.setattr(render, "AGENTS_MD_TARGETS", [alias, real])

    render.write_all(render.load_roster(STACK / "roster.yaml"),
                     render.load_profile(FIXTURE))

    backups = list((tmp_path / "backups").glob("agents-md.pre-render-*/*"))
    assert [p.read_text() for p in backups] == ["hand written, untracked, irreplaceable"], (
        "the alias pair is one file and must be backed up exactly once"
    )
    assert "Superpowers Skill Use" in real.read_text()
    assert alias.is_symlink(), "writing must not replace the alias with a real file"


# --- CLI: profile errors must not surface as tracebacks --------------------


def test_external_skill_collisions_detect_duplicate_names(tmp_path):
    stack_skills = tmp_path / "stack" / "skills"
    external = tmp_path / ".agents" / "skills"
    for name in ("owned-skill", "other-owned-skill"):
        (stack_skills / name).mkdir(parents=True)
    for name in ("owned-skill", "third-party-only"):
        (external / name).mkdir(parents=True)

    assert render.external_skill_collisions(
        render.skill_names(stack_skills), [external]
    ) == {external: {"owned-skill"}}


def test_external_skill_collisions_ignore_missing_external_dirs(tmp_path):
    stack_skills = tmp_path / "stack" / "skills"
    (stack_skills / "owned-skill").mkdir(parents=True)

    assert render.external_skill_collisions(
        render.skill_names(stack_skills), [tmp_path / "missing" / "skills"]
    ) == {}


def test_doctor_rejects_external_skills_that_shadow_stack_skills(tmp_path):
    stack = tmp_path / "stack"
    external = tmp_path / ".agents" / "skills"
    (stack / "skills" / "owned-skill").mkdir(parents=True)
    (external / "owned-skill").mkdir(parents=True)

    with pytest.raises(render.ConfigError) as exc:
        render.doctor(stack=stack, external_skill_dirs=[external])

    msg = str(exc.value)
    assert "External skill name collision" in msg
    assert "owned-skill" in msg
    assert str(external) in msg


def test_doctor_allows_non_overlapping_external_skills(tmp_path):
    stack = tmp_path / "stack"
    external = tmp_path / ".agents" / "skills"
    (stack / "skills" / "owned-skill").mkdir(parents=True)
    (external / "third-party-only").mkdir(parents=True)

    assert render.doctor(stack=stack, external_skill_dirs=[external]) == []


def _methodology_stack(tmp_path, *, methodology: str, ce_skills=("ce-plan",)):
    """A stack whose profile and manifest select `methodology`."""
    home = tmp_path / "home"
    stack = home / ".config/agent-stack"
    (stack / "skills" / "owned-skill").mkdir(parents=True)
    checkout = home / ".local/share/agent-stack/compound-engineering-plugin"
    for name in ce_skills:
        (checkout / "skills" / name).mkdir(parents=True)
    (stack / "methodologies.yaml").write_text(
        "version: 1\n"
        "methodologies:\n"
        "  superpowers:\n"
        "    skills_path: skills\n"
        "  compound-engineering:\n"
        "    repository: https://example.invalid/ce.git\n"
        f"    revision: {'a' * 40}\n"
        "    checkout: ~/.local/share/agent-stack/compound-engineering-plugin\n"
        f"    expected_skill_count: {len(ce_skills)}\n"
        "    pi_companions: []\n"
    )
    profile = stack / "profile.yaml"
    profile.write_text(f"methodology: {methodology}\n")
    return home, stack, profile


def test_active_skill_names_follow_the_selected_methodology(tmp_path):
    home, stack, profile = _methodology_stack(
        tmp_path, methodology="compound-engineering"
    )

    assert render.active_skill_names(stack=stack, profile=profile, home=home) == {
        "ce-plan"
    }

    profile.write_text("methodology: superpowers\n")
    assert render.active_skill_names(stack=stack, profile=profile, home=home) == {
        "owned-skill"
    }


def test_doctor_rejects_an_external_skill_shadowing_an_active_ce_skill(tmp_path):
    home, stack, profile = _methodology_stack(
        tmp_path, methodology="compound-engineering"
    )
    external = home / ".agents/skills"
    (external / "ce-plan").mkdir(parents=True)
    (external / "owned-skill").mkdir(parents=True)

    with pytest.raises(render.ConfigError) as exc:
        render.doctor(
            stack=stack,
            external_skill_dirs=[external],
            canonical_skill_names=render.active_skill_names(
                stack=stack, profile=profile, home=home
            ),
        )

    message = str(exc.value)
    assert "ce-plan" in message
    # superpowers is inactive, so its names are not canonical right now
    assert "owned-skill" not in message


def test_main_doctor_checks_the_active_methodology_skill_names(
    tmp_path, monkeypatch, capsys
):
    home, stack, profile = _methodology_stack(
        tmp_path, methodology="compound-engineering"
    )
    external = home / ".agents/skills"
    (external / "ce-plan").mkdir(parents=True)
    monkeypatch.setattr(render, "STACK", stack)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render.py",
            "doctor",
            "--profile",
            str(profile),
            "--home",
            str(home),
            "--external-skill-dir",
            str(external),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        render.main()

    assert "ce-plan" in str(exc.value)
    assert "Traceback" not in capsys.readouterr().err


def test_main_doctor_turns_collisions_into_a_plain_message(tmp_path, monkeypatch, capsys):
    home, stack, profile = _methodology_stack(tmp_path, methodology="superpowers")
    external = home / ".agents/skills"
    (external / "owned-skill").mkdir(parents=True)
    monkeypatch.setattr(render, "STACK", stack)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "render.py",
            "doctor",
            "--profile",
            str(profile),
            "--home",
            str(home),
            "--external-skill-dir",
            str(external),
        ],
    )

    with pytest.raises(SystemExit) as exc:
        render.main()

    assert isinstance(exc.value.__cause__, render.ConfigError)
    assert "owned-skill" in str(exc.value)
    assert "Traceback" not in capsys.readouterr().err


def test_main_turns_a_config_error_into_a_plain_message(tmp_path, monkeypatch, capsys):
    missing = tmp_path / "nope" / "profile.yaml"
    monkeypatch.setattr(sys, "argv", ["render.py", "--profile", str(missing)])

    with pytest.raises(SystemExit) as exc:
        render.main()

    assert isinstance(exc.value.__cause__, render.ConfigError)
    assert f"No profile at {missing}" in str(exc.value)
    assert "Traceback" not in capsys.readouterr().err
