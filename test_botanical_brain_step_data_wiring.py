"""Source-level regression for the Streamlit call site.

The CI/runtime used for core unit tests may not install Streamlit, so this test
parses the Step source rather than importing the UI module. It protects the
specific integration regression that previously existed: the engine class
accepted plant_compounds_df, but the real Step instantiated it without that
argument and silently fell back to the hard-coded occurrence map.
"""
import ast
from pathlib import Path


def test_real_step_passes_plant_compounds_df_to_botanical_brain_engine():
    path = Path(__file__).with_name("step_botanical_brain.py")
    tree = ast.parse(path.read_text(encoding="utf-8"))
    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "UniversalBotanicalBrainEngine"
    ]
    assert calls, "No UniversalBotanicalBrainEngine call found in the real Step"
    assert any(
        any(keyword.arg == "plant_compounds_df" for keyword in call.keywords)
        for call in calls
    ), "Real Step must inject plant_compounds_df into UniversalBotanicalBrainEngine"
