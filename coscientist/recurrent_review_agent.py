import asyncio
import os
import re
import json
from typing import Optional, TypedDict

from gpt_researcher import GPTResearcher
from gpt_researcher.utils.enum import Tone
from langchain_core.language_models.chat_models import BaseChatModel
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, StateGraph

from coscientist.common import load_prompt
from coscientist.custom_types import ParsedHypothesis, ReviewedHypothesis

from coscientist.ranking_agent import RankingMatchResult   # adapt to your actual type

from coscientist.reflection_agent_steps import (
    initial_filter_node,
    assumption_refinement_node,
    assumption_research_node,
)
from typing import List, Dict, Any
from enum import Enum
from functools import partial






DATA_DIR = "reflection_data"
REVIEWS_PATH = os.path.join(DATA_DIR, "reviews.jsonl")
TOURNAMENT_PATH = os.path.join(DATA_DIR, "tournament_results.jsonl")


# ---------------------------------------------------------
# Ensure storage directory exists
# ---------------------------------------------------------
def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


# ---------------------------------------------------------
# Save and load reviewed hypotheses
# ---------------------------------------------------------
def save_review_result(reviewed: ReviewedHypothesis) -> None:
    """Append a reviewed hypothesis to storage."""
    _ensure_data_dir()
    with open(REVIEWS_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(reviewed, default=lambda o: o.value if isinstance(o, Enum) else o.__dict__) + "\n")


def load_all_reviews() -> List[ReviewedHypothesis]:
    """Load all past reviewed hypotheses."""
    if not os.path.exists(REVIEWS_PATH):
        return []

    reviews: List[ReviewedHypothesis] = []
    with open(REVIEWS_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            data = json.loads(line)
            reviews.append(ReviewedHypothesis(**data))
    return reviews


# ---------------------------------------------------------
# Save and load tournament results
# ---------------------------------------------------------
def save_tournament_result(result: RankingMatchResult) -> None:
    """Append a tournament result from the Ranking agent."""
    _ensure_data_dir()
    with open(TOURNAMENT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(result, default=lambda o: o.value if isinstance(o, Enum) else o.__dict__) + "\n")


def load_all_tournament_results() -> List[RankingMatchResult]:
    """Load all tournament results."""
    if not os.path.exists(TOURNAMENT_PATH):
        return []

    results: List[RankingMatchResult] = []
    with open(TOURNAMENT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            results.append(RankingMatchResult(**json.loads(line)))
    return results


# ---------------------------------------------------------
# Summaries for LLM prompts
# ---------------------------------------------------------
def summarize_reviews_for_llm(reviews: List[ReviewedHypothesis]) -> List[Dict[str, Any]]:
    """Convert ReviewedHypothesis objects into compact LLM-friendly summaries."""
    return [
        {
            "uid": r.uid,
            "hypothesis": r.hypothesis,
            "verification_result": r.verification_result,
            "assumptions": r.assumptions,
        }
        for r in reviews
    ]


def summarize_tournaments_for_llm(results: List[RankingMatchResult]) -> List[Dict[str, Any]]:
    """Convert RankingMatchResult objects into compact LLM-friendly summaries."""
    return [
        {
            "hypothesis_uid": t.hypothesis_uid,
            "score": t.score,
            "issues": t.issues,
            "strengths": t.strengths,
        }
        for t in results
    ]

class ReflectionState(TypedDict):
    """
    Represents the state of the reflection process.

    Parameters
    ----------
    hypothesis_to_review: ParsedHypothesis
        The parsed hypothesis being evaluated
    passed_initial_filter: bool
        Whether the hypothesis passed the initial desk rejection filter
    initial_filter_assessment: str
        The assessment from the desk rejection filter
    _causal_reasoning: str
        The causal trace from hypothesis simulation (private)
    _refined_assumptions: str
        The refined assumptions output (private)
    _parsed_assumptions: dict[str, list[str]]
        Dictionary of parsed assumptions and sub-assumptions (private)
    _assumption_research_results: dict[str, str]
        Research results for each assumption (private)
    reviewed_hypothesis: Optional[ReviewedHypothesis]
        The final reviewed hypothesis with all verification results
    _review_improvement_rules: Optional[str]

    """

    hypothesis_to_review: ParsedHypothesis
    initial_filter_assessment: str
    passed_initial_filter: bool
    _causal_reasoning: str
    _refined_assumptions: str
    _parsed_assumptions: dict[str, list[str]]
    _assumption_research_results: dict[str, str]
    reviewed_hypothesis: Optional[ReviewedHypothesis]
    _review_improvement_rules: Optional[str]


def safe_truncate_json(obj, limit=6000):
    s = json.dumps(obj)
    if len(s) <= limit:
        return s
    # truncate at a comma boundary
    cut = s.rfind("},", 0, limit)
    if cut == -1:
        return "[]"
    return s[:cut+1] + "]"

def recurrent_review_node(state: ReflectionState, llm: BaseChatModel) -> ReflectionState:
    """
    Learn improvement rules from past reviews and tournament results.
    """

    # 1. Load historical artifacts
    past_reviews = load_all_reviews()
    tournament_results = load_all_tournament_results()

    # 2. Summaries for the LLM
    past_reviews_summary = summarize_reviews_for_llm(past_reviews)
    tournament_summary = summarize_tournaments_for_llm(tournament_results)

    # 3. Build recurrent review prompt
    prompt = load_prompt(
        "recurrent_review",
        past_reviews=safe_truncate_json(past_reviews_summary)[:6000],
        tournament_results=safe_truncate_json(tournament_summary)[:6000],
    )

    # 4. Call LLM to infer improvement rules
    response = llm.invoke([{"role": "user", "content": prompt}])

    # 5. Merge into state as persistent “knowledge”
    return {
        **state,
        "_review_improvement_rules": response.content,
    }




