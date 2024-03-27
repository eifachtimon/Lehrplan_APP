import json
import chromadb
import torch
from transformers import AutoTokenizer, AutoModel
import os

# Laden des Tokenizers und des Modells von Hugging Face
def load_model_and_tokenizer():
    
    print("Current Directory:", os.getcwd())
    global model, tokenizer
    model_name = "danielheinz/e5-base-sts-en-de"
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModel.from_pretrained(model_name)

    #--- Get Lehrplan.json ---------------------------------

    # Get the directory of the current script
    current_directory = os.path.dirname(os.path.abspath(__file__))

    # Define the filename
    filename = "Lehrplan21.json"

    # Construct the full path to the JSON file
    json_file_path = os.path.join(current_directory, filename)

    with open(json_file_path, 'r', encoding='utf-8') as json_file:
        json_data = json.load(json_file)

    #--- Load Data from Lehrplan.json ---------------------------------
    documents = [
        {
            "text": item["text"],
            "metadata": {
                k: (','.join(v) if isinstance(v, list) else str(v) if not isinstance(v, (str, int, float, bool)) else v)
                for k, v in item.items() if k != "text"
            },
            "id": item["uid"],
        }
        for item in json_data
    ]

    # Create the collection.
    collection = chromadb.PersistentClient().create_collection(name="Lehrplan_Basel_Stadt3")
    
    # Add docs to the collection. Can also update and delete. Row-based API coming soon!
    for doc in documents:
        text = doc['text']
        metadata = doc['metadata']
        id = doc['id']

        # Do something with the page_content and metadata
        #print(text)
        #print(metadata)
        #print()  # Adding a newline for better separation between documents
        print("done")

        # Add the document to the collection with an incremented ID
        collection.upsert(
            documents=[text],  # we embed for you, or bring your own
            metadatas=[metadata],  # filter on arbitrary metadata!
            ids=[id],  # must be unique for each doc
        )

        def embed_text_with_huggingface(texts):
            embeddings = []
            for text in texts:
                inputs = tokenizer(text, return_tensors="pt", padding=True, truncation=True, max_length=512)
                with torch.no_grad():
                    outputs = model(**inputs)
                embeddings.append(outputs.last_hidden_state.mean(dim=1).squeeze().tolist())
            return embeddings

    return collection