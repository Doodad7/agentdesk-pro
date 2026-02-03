from transformers import AutoTokenizer, AutoModelForCausalLM
import torch

# ✅ Load your fine-tuned model
model = AutoModelForCausalLM.from_pretrained("outputs")  # CPU version
tokenizer = AutoTokenizer.from_pretrained("outputs")

# ✅ Example input
question = "What is RAG?"

# Tokenize input (send to CPU since you don’t have CUDA)
inputs = tokenizer(question, return_tensors="pt")

# Generate response
outputs = model.generate(**inputs, max_new_tokens=50)

# Decode and print
print("Input:", question)
print("Output:", tokenizer.decode(outputs[0], skip_special_tokens=True))