# AgentDesk Architecture

AgentDesk is implemented as a multi-agent AI system.

It contains:

- Agent Orchestrator (manager agent) that coordinates all agents.
- Planner Agent that decides which agent should handle a query.
- Knowledge Agent that performs Retrieval-Augmented Generation (RAG).
- Future agents such as CodeAgent, SearchAgent, MemoryAgent.

The orchestrator receives user input, asks the planner to select the best agent, then forwards the task to that agent.

This design allows modular expansion and scalable reasoning.

Therefore, AgentDesk is a true multi-agent AI system.
