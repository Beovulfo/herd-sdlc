"""Arms as data: arms/NAME.json says when the challenger asks, what it is shown and what it is told.

A file holds {name, when, sees, instruction} and optionally tools ("Agent,Skill") and skills (SKILL.md paths).
"""
import os
import re
from pathlib import Path

import judge

ARMS_DIR = Path(__file__).resolve().parent / "arms"
CONTROL = "control"
WHEN = ("none", "after-red", "before-attacks")
SEES = ("request", "inputs_program", "known_limits", "criteria")
TOOLS = ("Agent", "Skill")  # the challenger is not sandboxed: no tool that reads files, runs commands or the network
KEYS = {"name", "when", "sees", "instruction", "tools", "skills"}


def _check(path, arm):
    def refuse(why):
        raise judge.Refused(f"{path}: {why}")

    def texts(v):
        return isinstance(v, list) and all(isinstance(x, str) and x.strip() for x in v)

    if set(arm) - KEYS:
        refuse(f"unknown key {', '.join(sorted(set(arm) - KEYS))}")
    name, when, sees = arm.get("name"), arm.get("when"), arm.get("sees")
    if not (isinstance(name, str) and re.fullmatch(r"[a-z0-9][a-z0-9-]*", name)) or name != path.stem:
        refuse("name must be lower-case letters, digits and dashes, and match the file name")
    if when not in WHEN:
        refuse(f"when must be one of {', '.join(WHEN)}")
    if not (texts(sees) and all(x in SEES for x in sees)):
        refuse(f"sees must be a list from {', '.join(SEES)}")
    if not isinstance(arm.get("instruction"), str):
        refuse("instruction must be text")
    if when != "none" and not (sees and arm["instruction"].strip()):
        refuse("an arm that asks needs sees and an instruction")
    _check_tools(arm, refuse, texts)


def _check_tools(arm, refuse, texts):
    tools = arm.get("tools", "")
    if not (isinstance(tools, str) and all(x in TOOLS for x in tools.split(",") if tools)):
        refuse(f"tools must be a comma-separated text from {', '.join(TOOLS)}")
    skills = arm.get("skills", [])
    if not (texts(skills) and all(Path(x).name == "SKILL.md" and Path(x).parent.name for x in skills)):
        refuse("skills must be a list of paths to SKILL.md files")
    if len({Path(x).parent.name for x in skills}) != len(skills):
        refuse("two skills have the same folder name")
    if skills and "Skill" not in tools.split(","):
        refuse("an arm with skills needs the Skill tool")


def load_arms(folder=ARMS_DIR, only=None):
    """{name: arm}, control first. One bad file refuses the whole folder."""
    arms = {}
    for path in sorted(Path(folder).glob("*.json")):
        arm = judge.read_json(path)
        if arm.get("name") in arms:
            raise judge.Refused(f"{path}: a second arm file named {arm['name']!r}")
        _check(path, arm)
        arms[arm["name"]] = arm
    if not arms:
        raise judge.Refused(f"no arm files in {folder}")
    unknown = sorted(set(only or []) - set(arms))
    if unknown:
        raise judge.Refused(f"unknown arm {', '.join(unknown)}; known arms: {', '.join(arms)}")
    order = sorted(arms, key=lambda n: (n != CONTROL, WHEN.index(arms[n]["when"]), n))
    return {n: arms[n] for n in order if not only or n in only}


def skill_files(arm, env):
    """([(skill name, file)], [missing paths]); ~ is the HOME of env."""
    found, missing = [], []
    for text in arm.get("skills", []):
        path = Path(env.get("HOME", os.path.expanduser("~")) + text[1:] if text.startswith("~/") else text)
        if path.is_file():
            found.append((path.parent.name, path))
        else:
            missing.append(text)
    return found, missing
