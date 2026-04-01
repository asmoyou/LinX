"""Tests for read_skill tool workspace path rendering."""

from types import SimpleNamespace
from uuid import uuid4

from agent_framework.tools.file_tools import clear_workspace_root, set_workspace_root
from agent_framework.tools.read_skill_tool import ReadSkillTool
from skill_library.skill_loader import get_skill_loader


def test_read_skill_tool_outputs_hidden_skills_workspace_paths(monkeypatch) -> None:
    """read_skill output should point to .skills-scoped workspace paths."""
    skill_ref = SimpleNamespace(
        skill_id=uuid4(),
        name="Weather Skill",
        description="Weather workflow",
        skill_md_content="Run {baseDir}/scripts/weather_helper.py",
        manifest=None,
        has_scripts=True,
        package_files={
            "weather/SKILL.md": "# Weather",
            "weather/scripts/weather_helper.py": "print('ok')",
            "weather/requirements.txt": "requests",
        },
    )
    skill_manager = SimpleNamespace(get_agent_skill_docs=lambda: [skill_ref])
    skill_loader = get_skill_loader()
    monkeypatch.setattr(
        skill_loader,
        "load_skill",
        lambda **_kwargs: SimpleNamespace(code_blocks=[]),
    )

    tool = ReadSkillTool(
        agent_id=uuid4(),
        user_id=uuid4(),
        skill_manager=skill_manager,
        skill_loader=skill_loader,
    )

    output = tool._run("Weather Skill")

    assert ".skills/Weather_Skill/scripts/weather_helper.py" in output
    assert ".skills/Weather_Skill/requirements.txt" in output
    assert "Skill base directory: `.skills/Weather_Skill`" in output


def test_read_skill_tool_materializes_selected_skill_into_workspace(monkeypatch, tmp_path) -> None:
    """Calling read_skill should lazily copy selected skill package files into workspace."""
    skill_ref = SimpleNamespace(
        skill_id=uuid4(),
        name="Weather Skill",
        description="Weather workflow",
        skill_md_content="Run {baseDir}/scripts/weather_helper.py",
        manifest=None,
        has_scripts=True,
        package_files={
            "weather/SKILL.md": "# Weather",
            "weather/scripts/weather_helper.py": "print('ok')",
            "weather/requirements.txt": "requests",
        },
    )
    skill_manager = SimpleNamespace(get_agent_skill_docs=lambda: [skill_ref])
    skill_loader = get_skill_loader()
    monkeypatch.setattr(
        skill_loader,
        "load_skill",
        lambda **_kwargs: SimpleNamespace(code_blocks=[]),
    )

    tool = ReadSkillTool(
        agent_id=uuid4(),
        user_id=uuid4(),
        skill_manager=skill_manager,
        skill_loader=skill_loader,
    )

    set_workspace_root(tmp_path)
    try:
        tool._run("Weather Skill")
    finally:
        clear_workspace_root()

    assert (tmp_path / ".skills" / "Weather_Skill" / "scripts" / "weather_helper.py").exists()
    assert (tmp_path / ".skills" / "Weather_Skill" / "requirements.txt").exists()


def test_read_skill_tool_strips_duplicate_skill_root_from_workspace_paths(monkeypatch) -> None:
    """Workspace paths should not repeat skill root when package root matches skill name."""
    skill_ref = SimpleNamespace(
        skill_id=uuid4(),
        name="weather-forcast",
        description="Weather workflow",
        skill_md_content="Run {baseDir}/scripts/weather_helper.py",
        manifest=None,
        has_scripts=True,
        package_files={
            "weather-forcast/SKILL.md": "# Weather",
            "weather-forcast/scripts/weather_helper.py": "print('ok')",
            "weather-forcast/requirements.txt": "requests",
        },
    )
    skill_manager = SimpleNamespace(get_agent_skill_docs=lambda: [skill_ref])
    skill_loader = get_skill_loader()
    monkeypatch.setattr(
        skill_loader,
        "load_skill",
        lambda **_kwargs: SimpleNamespace(code_blocks=[]),
    )

    tool = ReadSkillTool(
        agent_id=uuid4(),
        user_id=uuid4(),
        skill_manager=skill_manager,
        skill_loader=skill_loader,
    )

    output = tool._run("weather-forcast")

    assert ".skills/weather-forcast/scripts/weather_helper.py" in output
    assert ".skills/weather-forcast/requirements.txt" in output
    assert "Skill base directory: `.skills/weather-forcast`" in output
    assert ".skills/weather-forcast/weather-forcast/scripts/weather_helper.py" not in output


def test_read_skill_tool_materialization_strips_duplicate_skill_root(monkeypatch, tmp_path) -> None:
    """Materialization should avoid nested duplicate skill directory names."""
    skill_ref = SimpleNamespace(
        skill_id=uuid4(),
        name="weather-forcast",
        description="Weather workflow",
        skill_md_content="Run {baseDir}/scripts/weather_helper.py",
        manifest=None,
        has_scripts=True,
        package_files={
            "weather-forcast/SKILL.md": "# Weather",
            "weather-forcast/scripts/weather_helper.py": "print('ok')",
            "weather-forcast/requirements.txt": "requests",
        },
    )
    skill_manager = SimpleNamespace(get_agent_skill_docs=lambda: [skill_ref])
    skill_loader = get_skill_loader()
    monkeypatch.setattr(
        skill_loader,
        "load_skill",
        lambda **_kwargs: SimpleNamespace(code_blocks=[]),
    )

    tool = ReadSkillTool(
        agent_id=uuid4(),
        user_id=uuid4(),
        skill_manager=skill_manager,
        skill_loader=skill_loader,
    )

    set_workspace_root(tmp_path)
    try:
        tool._run("weather-forcast")
    finally:
        clear_workspace_root()

    assert (tmp_path / ".skills" / "weather-forcast" / "scripts" / "weather_helper.py").exists()
    assert (tmp_path / ".skills" / "weather-forcast" / "requirements.txt").exists()
    assert not (
        tmp_path
        / ".skills"
        / "weather-forcast"
        / "weather-forcast"
        / "scripts"
        / "weather_helper.py"
    ).exists()


def test_read_skill_tool_accepts_display_name_and_materializes_shell_script(
    monkeypatch, tmp_path
) -> None:
    """read_skill should accept display names and materialize packaged shell scripts."""
    skill_ref = SimpleNamespace(
        skill_id=uuid4(),
        skill_slug="document-artifact-rendering-installed-d4d838b4",
        display_name="Document Artifact Rendering",
        description="Render documents to PDF",
        skill_md_content="Run {baseDir}/scripts/render_document.sh",
        manifest=None,
        has_scripts=True,
        package_files={
            "document-artifact-rendering/SKILL.md": "# Document Artifact Rendering",
            "document-artifact-rendering/scripts/render_document.sh": "#!/bin/sh\necho render\n",
            "document-artifact-rendering/scripts/verify_artifact.py": "print('verify')\n",
        },
    )
    skill_manager = SimpleNamespace(get_agent_skill_docs=lambda: [skill_ref])
    skill_loader = get_skill_loader()
    monkeypatch.setattr(
        skill_loader,
        "load_skill",
        lambda **_kwargs: SimpleNamespace(code_blocks=[]),
    )

    tool = ReadSkillTool(
        agent_id=uuid4(),
        user_id=uuid4(),
        skill_manager=skill_manager,
        skill_loader=skill_loader,
    )

    set_workspace_root(tmp_path)
    try:
        output = tool._run("Document Artifact Rendering")
    finally:
        clear_workspace_root()

    script_path = (
        tmp_path
        / ".skills"
        / "document-artifact-rendering-installed-d4d838b4"
        / "scripts"
        / "render_document.sh"
    )
    assert script_path.exists()
    assert ".skills/document-artifact-rendering-installed-d4d838b4/scripts/render_document.sh" in output
    assert "bash .skills/document-artifact-rendering-installed-d4d838b4/scripts/render_document.sh --help" in output
