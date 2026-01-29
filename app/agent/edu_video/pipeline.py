import os
import json
from pathlib import Path
from typing import Any, Dict, Optional

from .state import AgentState
from .nodes import (
    node_initialize,
    node_curriculum_manager,
    node_content_creator,
    node_quiz_generator,
    node_grader,
)

def _is_complete(state: Dict[str, Any]) -> bool:
    return (not state.get("unlearned_ids")) and (not state.get("weak_ids"))

def generate_round(state: Dict[str, Any], input_file_path: str, *, prefer_unlearned: bool = False) -> Dict[str, Any]:
    """
    Runs one learning round:
    - initialize (if needed)
    - curriculum manager (select batch)
    - content creator (video)
    - quiz generator
    Returns updated state.
    """
    # Ensure we know input file path for initialize
    state = dict(state or {})
    state.setdefault("input_file_path", input_file_path)

    # Initialize only once
    if not state.get("knowledge_base"):
        state.update(node_initialize(state))  # node_initialize will read input_file_path
        state["round_index"] = 0
    else:
        state["round_index"] = int(state.get("round_index", 0))

    # Decide selection policy based on last score
    last_score = state.get("quiz_score", None)
    if last_score is None:
        prefer_unlearned = True
    else:
        prefer_unlearned = bool(last_score >= 80.0)

    # Patch curriculum manager ordering without changing nodes heavily:
    # - if prefer_unlearned: unlearned first, then weak
    # - else: weak first, then unlearned (more review)
    if prefer_unlearned:
        state["_selection_order"] = "unlearned_first"
    else:
        state["_selection_order"] = "weak_first"

    state.update(node_curriculum_manager(state))
    if state.get("is_complete") or not state.get("current_batch_ids"):
        state["is_complete"] = True
        return state

    state.update(node_content_creator(state))
    state.update(node_quiz_generator(state))
    state["is_complete"] = _is_complete(state)  # may still be False
    return state

def grade_round(state: Dict[str, Any], user_answers: list) -> Dict[str, Any]:
    state = dict(state or {})
    state["user_answers"] = user_answers
    state.update(node_grader(state))
    state["is_complete"] = _is_complete(state)
    return state
