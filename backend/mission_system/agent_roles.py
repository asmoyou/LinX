"""Agent role configurations for mission execution.

Provides system prompts and AgentConfig factories for the three
specialised roles used during a mission: Leader, Supervisor, and QA.
"""

from uuid import UUID, uuid4

from agent_framework.base_agent import AgentConfig

# ---------------------------------------------------------------------------
# System prompts
# ---------------------------------------------------------------------------

LEADER_SYSTEM_PROMPT = """\
You are the Mission Leader. Your job is to:
1. Analyse the mission instructions and any attached reference materials.
2. Gather requirements by asking clarifying questions when the instructions are ambiguous.
3. Produce a structured requirements document.
4. Decompose the requirements into an ordered list of tasks with acceptance criteria.
5. Assign each task to the most suitable agent based on their capabilities.
6. Monitor execution progress and unblock agents when they are stuck.

Communicate clearly and concisely. When generating tasks, include:
- A short descriptive title
- Detailed instructions
- Acceptance criteria (testable conditions)
- Dependencies on other tasks (by title)
"""

SUPERVISOR_SYSTEM_PROMPT = """\
You are the Mission Supervisor. Your job is to review completed work \
against the acceptance criteria defined in each task.

For every task you review:
1. Read the acceptance criteria.
2. Examine the deliverables and outputs produced by the worker agent.
3. Decide PASS or FAIL.
4. If FAIL, provide specific, actionable feedback explaining what needs to change.

Be thorough but fair. Only fail a task when the acceptance criteria are clearly not met.
"""

QA_SYSTEM_PROMPT = """\
You are the QA Auditor. Your job is to perform a final quality and \
security audit of the mission deliverables.

Check for:
1. Correctness: Does the output satisfy the original mission instructions?
2. Completeness: Are all required deliverables present?
3. Quality: Is the work clean, well-structured, and production-ready?
4. Security: Are there hardcoded secrets, injection vulnerabilities, or unsafe patterns?

Produce a structured audit report with a PASS / FAIL verdict and itemised findings.
"""


# ---------------------------------------------------------------------------
# Config factories
# ---------------------------------------------------------------------------


def get_leader_config(
    owner_user_id: UUID,
    temperature: float = 0.3,
    max_iterations: int = 30,
) -> AgentConfig:
    """Return an AgentConfig for the mission leader role."""
    return AgentConfig(
        agent_id=uuid4(),
        name="mission-leader",
        agent_type="leader",
        owner_user_id=owner_user_id,
        capabilities=["planning", "decomposition", "coordination"],
        system_prompt=LEADER_SYSTEM_PROMPT,
        temperature=temperature,
        max_iterations=max_iterations,
    )


def get_supervisor_config(
    owner_user_id: UUID,
    temperature: float = 0.2,
    max_iterations: int = 20,
) -> AgentConfig:
    """Return an AgentConfig for the mission supervisor role."""
    return AgentConfig(
        agent_id=uuid4(),
        name="mission-supervisor",
        agent_type="supervisor",
        owner_user_id=owner_user_id,
        capabilities=["review", "evaluation"],
        system_prompt=SUPERVISOR_SYSTEM_PROMPT,
        temperature=temperature,
        max_iterations=max_iterations,
    )


def get_qa_config(
    owner_user_id: UUID,
    temperature: float = 0.1,
    max_iterations: int = 15,
) -> AgentConfig:
    """Return an AgentConfig for the mission QA auditor role."""
    return AgentConfig(
        agent_id=uuid4(),
        name="mission-qa",
        agent_type="qa",
        owner_user_id=owner_user_id,
        capabilities=["audit", "security_review", "quality_check"],
        system_prompt=QA_SYSTEM_PROMPT,
        temperature=temperature,
        max_iterations=max_iterations,
    )
