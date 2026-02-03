# services/agents/planner_agent.py

from services.agents.base import BaseAgent

class PlannerAgent(BaseAgent):
    """
    Decides what kind of task the user wants.
    """

    def __init__(self):
        super().__init__("PlannerAgent")

    def run(self, input_data: dict):
        query = input_data["query"].lower()

        if "ticket" in query or "issue" in query:
            return {"intent": "tool"}

        if "image" in query:
            return {"intent": "vision"}

        return {"intent": "rag"}
