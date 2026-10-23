import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import render


STACK = Path(__file__).resolve().parents[1]
SKILLS = STACK / "skills"
LOCAL_SKILLS = STACK / "local-skills"
GATE_SKILL = LOCAL_SKILLS / "auditing-final-tests"


def _skill(name: str) -> str:
    return (LOCAL_SKILLS / name / "SKILL.md").read_text()


def _markdown_h2_section(text: str, heading: str) -> str:
    match = re.search(
        rf"^## {re.escape(heading)}\s*$\n(?P<body>.*?)(?=^#{{1,2}} |\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    assert match is not None, f"missing Markdown section: ## {heading}"
    return match.group("body")


def _normalized_section(skill: str, heading: str) -> str:
    return " ".join(_markdown_h2_section(_skill(skill), heading).split())


def test_auditing_final_tests_is_a_four_outcome_completion_gate():
    text = _skill("auditing-final-tests")

    assert "durable product documentation, not a transcript of implementation" in text
    assert "This test should still matter in six months because it protects" in text
    for outcome in ("NOT_APPLICABLE", "PASS", "ACTION_REQUIRED", "BLOCKED"):
        assert f"`{outcome}`" in text
    assert "PASS` and `NOT_APPLICABLE" in text
    assert "only completion-permitting outcomes" in text


def test_auditing_final_tests_requires_one_record_per_changed_test():
    record_section = _normalized_section("auditing-final-tests", "Required Record")

    for field in (
        "File and test name",
        "Durability statement",
        "Classification",
        "Reason",
        "Action",
    ):
        assert field in record_section, (
            f"the record contract must fix the field {field!r}"
        )
    for decision in ("Keep", "Rework", "Delete"):
        assert decision in record_section, (
            f"the record contract must fix the decision {decision!r}"
        )
    assert "every added or changed test" in record_section

    for status in (
        "**Keep**: no action pending",
        "read-only: required — not applied",
        "writable: applied as retained, rewritten, moved, or removed",
    ):
        assert status in record_section, (
            f"the Action column must fix the status vocabulary: {status!r}"
        )


def test_keep_records_are_compact_without_losing_per_test_identity():
    section = _normalized_section("auditing-final-tests", "Compact Keep records")

    assert "one row per definition" in section
    assert "Reason: durable contract named in Protects" in section
    assert "Action: Keep: no action pending" in section
    assert "Use the full five fields for every Rework or Delete decision" in section
    assert "Never compress away the reason an action is needed." in section

    report = _normalized_section("auditing-final-tests", "Report")
    assert "one linked durable artifact" in report
    assert "show detailed rows only for Rework, Delete" in report
    assert "Do not repeat unchanged command transcripts" in report


def test_gate_outcomes_define_the_read_only_all_keep_case():
    section = _normalized_section("auditing-final-tests", "Gate Outcomes")

    assert (
        "A read-only audit whose every changed test is **Keep** has no pending action, "
        "so it never returns `ACTION_REQUIRED`." in section
    )
    assert (
        "Return `PASS` only when the required final verification evidence is already "
        "established and the record names who ran the exact commands and their "
        "results; otherwise return `BLOCKED`." in section
    )
    assert (
        "the parent workflow still verifies it independently before completion."
        in section
    )


def test_gate_workflow_separates_writable_and_read_only_duties():
    section = _normalized_section("auditing-final-tests", "Gate Workflow")

    assert "In a writable context, apply every Rework and Delete action." in section
    assert (
        "In a read-only context, return any Rework/Delete findings as "
        "`ACTION_REQUIRED` to the owning writer." in section
    )
    assert (
        "**Reinspect** the final diff because curation can change the test set."
        in section
    )
    assert (
        "Repeat until the audit reaches a **fixed point** with no unresolved action."
        in section
    )
    assert (
        "Run focused verification plus relevant lint, type, or compile checks when test "
        "files or imports changed." in section
    )


def test_gate_workflow_blocks_when_current_test_identity_is_unresolved():
    section = _normalized_section("auditing-final-tests", "Gate Workflow")

    assert (
        "Never fabricate exact existing or proposed future destination paths or test "
        "names." in section
    )
    assert (
        "**Unresolvable current identity:** when the exact path or test name of a "
        "changed test cannot be established, mark the identity unresolved and return "
        "`BLOCKED`." in section
    )


def test_gate_workflow_describes_an_unknown_future_destination_without_blocking():
    section = _normalized_section("auditing-final-tests", "Gate Workflow")

    assert (
        "**Unknown proposed destination:** describe it by ownership or domain and mark "
        "it unverified." in section
    )
    assert "An unverified destination does not block." in section


def test_classification_uses_only_supplied_evidence_for_exact_contracts():
    section = _normalized_section("auditing-final-tests", "Classification")

    assert "Classify only from supplied evidence." in section
    assert "Never infer an unseen implementation or body from a test name." in section
    assert (
        "A stated exact documented flag or string is **Keep** absent concrete evidence "
        "of non-contract coupling." in section
    )


def test_gate_workflow_labels_read_only_actions_as_unapplied():
    section = _normalized_section("auditing-final-tests", "Gate Workflow")

    assert (
        "In read-only reports, action status must say required and not applied."
        in section
    )
    assert (
        "Never claim retained, rewritten, moved, or removed as completed until a "
        "writer applied it." in section
    )


def test_gate_report_does_not_offer_bypass_completion_paths():
    section = _normalized_section("auditing-final-tests", "Report")

    assert (
        "Do not propose or present merge, ship, deploy, or human override as an "
        "alternate completion path." in section
    )
    assert "A bypass decision is outside the gate" in section
    assert "report only the non-passing outcome and required actions." in section


LOCALLY_OWNED_ORIGINS = frozenset({"local", "local-adapted"})


def _gate_hooks_outside_local_ownership(
    gated: set[str], origins: dict[str, str]
) -> list[tuple[str, str]]:
    return sorted(
        (name, origins.get(name, "undeclared"))
        for name in gated
        if origins.get(name, "undeclared") not in LOCALLY_OWNED_ORIGINS
    )


def test_only_locally_owned_skills_carry_the_final_test_gate_hook():
    """Adding the hook edits a skill, so provenance decides who may carry one."""
    provenance = render.yaml.safe_load((SKILLS / "provenance.yaml").read_text())
    origins = {
        name: record["origin"] for name, record in provenance["skills"].items()
    }
    gated = {
        path.parent.name
        for root in (SKILLS, LOCAL_SKILLS)
        for path in root.glob("*/SKILL.md")
        if "**Final-test gate:**" in path.read_text()
    }

    assert gated, "at least one caller must carry the gate hook"
    assert _gate_hooks_outside_local_ownership(gated, origins) == [], (
        "an inherited or external skill is immutable and may never carry the "
        "**Final-test gate:** hook; fork it into a locally owned skill instead"
    )


def test_review_engine_defers_to_the_canonical_gate_skill():
    """A restated rubric drifts from the gate the parent actually runs."""
    dispatch = _normalized_section("review-branch", "3. Dispatch Read-Only Reviewers")
    assert (
        "The final-test audit reviewer must receive the full canonical "
        "`auditing-final-tests` skill content, and must not restate or summarize its "
        "rubric." in dispatch
    )

    reviewers = (LOCAL_SKILLS / "review-branch" / "REVIEWERS.md").read_text()
    section = " ".join(_markdown_h2_section(reviewers, "Final-Test Audit").split())
    assert "Use `auditing-final-tests` as the canonical procedure" in section
    assert "does not restate its rubric" in section
    for outcome in ("NOT_APPLICABLE", "PASS", "ACTION_REQUIRED", "BLOCKED"):
        assert f"`{outcome}`" in section, (
            f"the reviewer contract must compose the {outcome} outcome"
        )
    assert "complete per-test records" in section


SCENARIO_FILES = (
    "test-micro-passing-is-not-curation.md",
    "test-pressure-stabilization-artifacts.md",
    "test-pressure-exact-contracts-and-policy-placement.md",
    "test-pressure-post-audit-mutation.md",
    "test-pressure-read-only-all-keep.md",
)


@pytest.mark.parametrize("filename", SCENARIO_FILES)
def test_gate_pressure_scenarios_are_scored_and_ship_with_the_skill(filename: str):
    """A prompt with no recorded baseline and no expected outcome cannot fail.

    Scenarios live beside the skill they exercise, one per file, and each one has
    to say which skill the subagent may load, what an unguided run does, and which
    gate outcome a guided run must reach.
    """
    path = GATE_SKILL / filename
    assert path.is_file(), f"missing pressure scenario: {path}"
    text = path.read_text()

    for heading in (
        "## Skill Access",
        "## Prompt",
        "## RED Baseline",
        "## Expected Outcome",
    ):
        assert heading in text, f"{filename} is missing the {heading} section"
    assert "auditing-final-tests" in text, (
        f"{filename} must name the skill under test"
    )
    expected_outcome = _markdown_h2_section(text, "Expected Outcome")
    assert re.search(
        r"`(?:PASS|NOT_APPLICABLE|ACTION_REQUIRED|BLOCKED)`", expected_outcome
    ), f"{filename} must record an expected gate outcome in ## Expected Outcome"


@pytest.mark.parametrize("methodology", sorted(render.METHODOLOGY_FRAGMENTS))
def test_composed_agents_md_requires_the_final_test_gate(methodology: str):
    """Every methodology receives the always-on local completion gate."""
    section = _markdown_h2_section(
        render.compose_agents_md({"methodology": methodology}),
        "Final-Test Curation Gate",
    )
    normalized_section = " ".join(section.split())

    assert (
        "Any workflow that adds or changes tests MUST use `auditing-final-tests` "
        "before completion, including features, bug fixes, refactors, CI repairs, "
        "review fixes, and test-only changes." in normalized_section
    )
    assert (
        "`PASS` and `NOT_APPLICABLE` are the only completion-permitting outcomes."
        in normalized_section
    )
    assert "Resolve `ACTION_REQUIRED`; report `BLOCKED` honestly." in normalized_section


def _assert_final_test_gate_contract(section: str) -> tuple[str, int]:
    """Assert one caller's final-test gate step and locate it in the section.

    Returns the whitespace-normalized section plus the offset of the gate step so
    each caller can assert where that step sits among its own steps. Only the
    placement contract is checked: the gate covers the full change scope, and the
    continuation rule that follows it names the two permitting outcomes.
    """
    normalized_section = " ".join(section.split())
    marker = "**Final-test gate:**"
    gate_position = normalized_section.find(marker)
    assert gate_position != -1, f"section has no {marker} step"

    tail = normalized_section[gate_position + len(marker) :]
    next_step = re.search(r"\s\d+\.\s+(?:\*\*)?\S", tail)
    gate_block = tail[: next_step.start()] if next_step else tail

    scope = re.search(
        r"invoke `auditing-final-tests`[^.]*full change scope", gate_block
    )
    assert scope is not None, (
        "gate step must invoke `auditing-final-tests` over the full change scope, "
        f"got: {gate_block!r}"
    )

    outcomes = "`PASS` or `NOT_APPLICABLE`"
    continuations = [s for s in gate_block.split(".") if outcomes in s]
    assert len(continuations) == 1, (
        f"gate step must state {outcomes} exactly once, got {len(continuations)} "
        f"sentence(s) in {gate_block!r}"
    )
    continuation = continuations[0]
    assert re.search(r"\bonly\b", continuation, flags=re.IGNORECASE), (
        f"continuation must be restricted to those outcomes: {continuation!r}"
    )
    assert re.search(
        r"\b(?:continue|proceed|completion|permit)", continuation, flags=re.IGNORECASE
    ), f"continuation must say what those outcomes allow: {continuation!r}"
    assert gate_block.find(continuation) > scope.end(), (
        "the gate must be scoped to the full change before the continuation rule: "
        f"{gate_block!r}"
    )

    for clause in ("Resolve `ACTION_REQUIRED`", "report `BLOCKED` honestly"):
        assert clause in gate_block, (
            f"gate step must keep the clause {clause!r}: {gate_block!r}"
        )
    return normalized_section, gate_position


def test_ci_red_triage_gates_after_focused_verification():
    section = _markdown_h2_section(_skill("ci-red-triage"), "Workflow")
    normalized_section, gate_position = _assert_final_test_gate_contract(section)

    focused = normalized_section.find("focused verification")
    assert -1 < focused < gate_position, (
        "triage must verify its fix before auditing the resulting test set"
    )


def test_pr_feedback_watch_loop_gates_before_push_and_loop_state_update():
    section = _markdown_h2_section(_skill("pr-feedback-watch-loop"), "Wake Workflow")
    normalized_section, gate_position = _assert_final_test_gate_contract(section)

    push = re.search(r"(?:\*\*)?Push\b", normalized_section)
    loop_state = re.search(r"(?:\*\*)?Update (?:the )?loop state\b", normalized_section)
    assert push is not None, "the wake workflow must keep a push step"
    assert loop_state is not None, "the wake workflow must keep a loop-state step"

    focused = normalized_section.find("focused verification")
    assert -1 < focused < gate_position, (
        "the wake must verify before auditing the resulting test set"
    )
    assert gate_position < push.start() < loop_state.start(), (
        "an unaudited test set must never be pushed or recorded as loop progress"
    )


def test_full_review_and_fix_gates_after_fix_cycles_and_before_reporting():
    text = _skill("full-review-and-fix")
    section = _markdown_h2_section(text, "4. Verify and Stop")
    normalized_section, gate_position = _assert_final_test_gate_contract(section)

    cycle_limit = normalized_section.find("Apply at most")
    assert -1 < cycle_limit < gate_position, (
        "the gate runs after the bounded fix cycles, not between them"
    )

    report_heading = text.find("\n## 5. Report")
    gate_in_file = text.find("**Final-test gate:**")
    assert report_heading != -1, "full-review-and-fix must keep its Report step"
    assert -1 < gate_in_file < report_heading, (
        "the gate must close the mutation phase before the Report step begins"
    )
