from datasets import load_dataset
from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments, Trainer
from peft import get_peft_model, LoraConfig, TaskType
import mlflow
mlflow.set_tracking_uri("http://127.0.0.1:5000")
mlflow.set_experiment("rag-finetune")

model_name = "facebook/opt-350m"
dataset = load_dataset("json", data_files="data.jsonl")

tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

lora_config = LoraConfig(
    task_type=TaskType.CAUSAL_LM, inference_mode=False,
    r=8, lora_alpha=32, lora_dropout=0.1
)
model = get_peft_model(model, lora_config)

def tokenize(batch):
    return tokenizer(
        batch["instruction"],
        text_target=batch["output"],
        truncation=True,
        padding="max_length",   # ✅ ensures all sequences are same length
        max_length=128          # ✅ you can adjust (128 is enough for short Q&A)
    )


dataset = dataset.map(tokenize, batched=True)

training_args = TrainingArguments(
    output_dir="outputs",
    per_device_train_batch_size=2,
    num_train_epochs=1,
    logging_dir="./logs",
    logging_steps=10
)

trainer = Trainer(model=model, args=training_args, train_dataset=dataset["train"])
trainer.train()

# ✅ Save outputs locally
trainer.save_model("outputs")
tokenizer.save_pretrained("outputs")

# ✅ Log to MLflow
import mlflow
with mlflow.start_run():
    mlflow.log_artifacts("outputs", artifact_path="finetuned_model")