import mlflow
import mlflow.pyfunc
import random
import time

mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("rag-training")

with mlflow.start_run():
    # Log params
    mlflow.log_param("embedding_model", "sentence-transformers/all-MiniLM-L6-v2")
    mlflow.log_param("epochs", 3)

    # Fake metrics for example
    for epoch in range(3):
        acc = random.random()
        mlflow.log_metric("accuracy", acc, step=epoch)
        time.sleep(1)

    # Save an artifact
    with open("example.txt", "w") as f:
        f.write("This is an artifact")
    mlflow.log_artifact("example.txt")
