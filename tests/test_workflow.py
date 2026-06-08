"""Workflow structure tests (no LLM calls)."""

from google.adk import Workflow

from clintrace_agent.agent import root_agent
from clintrace_agent.config import MERGE_TRIAGE_LLM_STEPS
from clintrace_agent.sub_agents.feedback import DeterministicFeedbackAgent


def test_root_agent_is_workflow():
    assert isinstance(root_agent, Workflow)
    assert root_agent.name == "triage_pipeline"


def test_workflow_has_expected_stages():
    """Pipeline nodes match merged vs legacy layout."""
    assert root_agent.graph is not None
    names = {node.name for node in root_agent.graph.nodes}
    common = {
        "symptom_parser",
        "specialist_router",
        "enforce_routing",
        "feedback_agent",
    }
    assert common.issubset(names)
    if MERGE_TRIAGE_LLM_STEPS:
        assert {
            "clinical_assessor",
            "expand_clinical",
            "deterministic_audit",
        }.issubset(names)
        assert "severity_scorer" not in names
        assert "audit_reporter" not in names
    else:
        assert {
            "severity_scorer",
            "red_flag_detector",
            "clinical_join",
            "audit_reporter",
        }.issubset(names)


def test_fast_path_uses_deterministic_feedback():
    import clintrace_agent as agent_module
    from clintrace_agent.config import USE_LLM_FEEDBACK

    if not USE_LLM_FEEDBACK:
        feedback_nodes = [
            n
            for n in root_agent.graph.nodes
            if n.name == "feedback_agent"
        ]
        assert len(feedback_nodes) == 1
        assert isinstance(feedback_nodes[0], DeterministicFeedbackAgent)


def test_symptom_parser_skill_integration():
    """INLINE_SKILLS inlines SKILL.md; otherwise SkillToolset loads on demand."""
    from clintrace_agent.config import INLINE_SKILLS
    from clintrace_agent.skills_loader import read_skill_body
    from clintrace_agent.sub_agents.symptom_parser import symptom_parser

    skill_snippet = read_skill_body("clinical-intake-parser")[:120]
    if INLINE_SKILLS:
        assert skill_snippet in symptom_parser.instruction
        assert symptom_parser.tools == []
    else:
        from google.adk.tools.skill_toolset import SkillToolset

        assert any(isinstance(t, SkillToolset) for t in symptom_parser.tools)


def test_scorers_expose_medical_lookup_tools():
    """ESI / red-flag lookups on legacy or merged clinical assessor."""
    from google.adk.tools import FunctionTool

    if MERGE_TRIAGE_LLM_STEPS:
        from clintrace_agent.sub_agents.clinical_assessor import clinical_assessor

        agent = clinical_assessor
    else:
        from clintrace_agent.sub_agents.red_flag_detector import red_flag_detector
        from clintrace_agent.sub_agents.severity_scorer import severity_scorer

        def tool_names(agent):
            out = []
            for t in agent.tools:
                if isinstance(t, FunctionTool):
                    out.append(t.name)
            return out

        assert "lookup_esi_criteria" in tool_names(severity_scorer)
        assert "lookup_red_flag_criteria" in tool_names(red_flag_detector)
        return

    def tool_names(agent):
        out = []
        for t in agent.tools:
            if isinstance(t, FunctionTool):
                out.append(t.name)
        return out

    assert "lookup_esi_criteria" in tool_names(agent)
    assert "lookup_red_flag_criteria" in tool_names(agent)
