"""Wizard JSON registry directory.

Each JSON file in this directory is one wizard, loaded by
``apps.setup_studio.wizard_engine.load_wizard_registry`` at module import.
File names matching ``_*.json`` are ignored (drafts).

The schema is documented at ``docs/WIZARD_BRANCHING_SCHEMA.md``.
"""
