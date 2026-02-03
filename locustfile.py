# locustfile.py
from locust import HttpUser, task, between

class ApiUser(HttpUser):
    wait_time = between(1, 3)
    @task(2)
    def ping(self):
        self.client.get("/ping")

    @task(5)
    def retrieve(self):
        self.client.post("/retrieve", json={"q":"hello world","top_k":1})

    @task(1)
    def execute_tool(self):
        headers = {"Authorization":"Bearer admin123"}
        self.client.post("/execute_tool", json={"name":"create_ticket","args":{"title":"load test"}}, headers=headers)