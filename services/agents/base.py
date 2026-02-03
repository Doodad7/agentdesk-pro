# services/agents/base.py

class BaseAgent:
    def __init__(self, name: str):
        self.name = name

    def run(self, input_data: dict):
        raise NotImplementedError("Agent must implement run()")
