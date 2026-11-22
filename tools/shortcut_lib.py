"""Helpers to write Apple Shortcuts (.shortcut, WFWorkflow plist) from Python.

The format is undocumented. Everything built with this must be checked on a
Mac with read-only probes before it is allowed to delete anything (see
tools/make_shortcut.py).
"""
import plistlib
import uuid
from pathlib import Path

NS = uuid.UUID("6f1c2a52-6a40-4c8e-9a51-0c7d1f3e2b11")


def uid(name: str) -> str:
    return str(uuid.uuid5(NS, name)).upper()


def attachment(value: dict) -> dict:
    return {"Value": value, "WFSerializationType": "WFTextTokenAttachment"}


def shortcut_input() -> dict:
    return attachment({"Type": "ExtensionInput"})


def output_of(action_uuid: str, name: str) -> dict:
    return attachment({"Type": "ActionOutput", "OutputUUID": action_uuid, "OutputName": name})


def variable(name: str) -> dict:
    return attachment({"Type": "Variable", "VariableName": name})


def repeat_item() -> dict:
    return variable("Repeat Item")


def text(*parts) -> dict:
    """Text field mixing literal strings and variables."""
    s, attachments = "", {}
    for p in parts:
        if isinstance(p, str):
            s += p
        else:
            loc = len(s.encode("utf-16-le")) // 2
            attachments[f"{{{loc}, 1}}"] = p["Value"]
            s += "￼"
    return {"Value": {"string": s, "attachmentsByRange": attachments}, "WFSerializationType": "WFTextTokenString"}


def action(identifier: str, **params) -> dict:
    return {"WFWorkflowActionIdentifier": f"is.workflow.actions.{identifier}", "WFWorkflowActionParameters": params}


def filter_template(prop: str, operator: int, values: dict, prefix: int = 1) -> dict:
    return {
        "Value": {
            "WFActionParameterFilterPrefix": prefix,
            "WFContentPredicateBoundedDate": False,
            "WFActionParameterFilterTemplates": [
                {"Property": prop, "Operator": operator, "Removable": True, "Values": values},
            ],
        },
        "WFSerializationType": "WFContentPredicateTableTemplate",
    }


def if_start(group: str, var: dict, condition: int, string: str | None = None, number: float | None = None) -> dict:
    params = {"GroupingIdentifier": group, "WFControlFlowMode": 0,
              "WFInput": {"Type": "Variable", "Variable": var}, "WFCondition": condition}
    if string is not None:
        params["WFConditionalActionString"] = string
    if number is not None:
        params["WFNumberValue"] = number
    return action("conditional", **params)


def if_end(group: str) -> dict:
    return action("conditional", GroupingIdentifier=group, WFControlFlowMode=2)


def workflow(actions: list) -> dict:
    return {
        "WFWorkflowActions": actions,
        "WFWorkflowClientVersion": "2605.0.5",
        "WFWorkflowMinimumClientVersion": 900,
        "WFWorkflowMinimumClientVersionString": "900",
        "WFWorkflowHasShortcutInputVariables": True,
        "WFWorkflowIcon": {"WFWorkflowIconStartColor": 3980825855, "WFWorkflowIconGlyphNumber": 59511},
        "WFWorkflowImportQuestions": [],
        "WFWorkflowInputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowOutputContentItemClasses": ["WFStringContentItem"],
        "WFWorkflowTypes": [],
        "WFQuickActionSurfaces": [],
    }


def write(wf: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        plistlib.dump(wf, f, fmt=plistlib.FMT_BINARY)
