# services/agents/orchestrator.py

from services.agents.planner_agent import PlannerAgent
from services.tools.ticket_tool import create_ticket
from services.rag.rag_runner import answer_query

class AgentOrchestrator:
    """
    Central brain that coordinates all agents.
    """

    def __init__(self):
        self.planner = PlannerAgent()

    def run(self, query: str, top_k: int = 5):

        # 1) Decide intent
        decision = self.planner.run({"query": query})
        intent = decision["intent"]

        # 2) Route to correct agent
        if intent == "tool":
            result = create_ticket({
                "title": query,
                "description": query,
                "priority": "medium"
            })
            return {
                "agent": "ToolAgent",
                "result": result
            }

        # 3) Knowledge Agent (RAG)
        expanded_query = f"{query} related to machine learning and artificial intelligence"
        rag_result = answer_query(expanded_query, top_k)


        return {
            "agent": "KnowledgeAgent",
            "result": rag_result
        }
