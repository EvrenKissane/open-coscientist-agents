from coscientist.ranking_agent import EloTournament
from coscientist.custom_types import ReviewedHypothesis
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(model="gpt-4o-mini")

tournament = EloTournament(goal="Test scientific hypotheses")

# Fake hypotheses
h1 = ReviewedHypothesis(uid="h1", hypothesis="A causes B", verification_result="Seems plausible")
h2 = ReviewedHypothesis(uid="h2", hypothesis="B causes C", verification_result="Weak evidence")
h3 = ReviewedHypothesis(uid="h3", hypothesis="C causes D", verification_result="Strong evidence")

tournament.add_hypothesis(h1)
tournament.add_hypothesis(h2)
tournament.add_hypothesis(h3)

for i in range(3):
    print(f"\n--- ROUND {i+1} ---")
    tournament.run_tournament(llm, k_bracket=2)
    print("Current rankings:", tournament.get_sorted_hypotheses())

print(tournament.get_sorted_hypotheses())
print(tournament.summarize_tournament_trajectory())