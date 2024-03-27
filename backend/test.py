#------------------------------------------------------------Imports------------------------------------------------------------
from flask import Flask, jsonify, request
from chroma_lehrplan import load_model_and_tokenizer
import chromadb
from flask_cors import CORS  # CORS import

#------------------------------------------------------------ChromaDB------------------------------------------------------------

client = chromadb.PersistentClient()
client.heartbeat()

def init_collection():
    try:
        collection = client.get_or_create_collection(name="Lehrplan_BS")
        collection_size = collection.count()
        print(collection_size)
        return collection
    except Exception as e:  # Revised exception handling
        print("Error:", e)
        collection = load_model_and_tokenizer()
        return collection

#------------------------------------------------------------App------------------------------------------------------------

# App
app = Flask(__name__, static_folder='frontend')
CORS(app, resources={r"/*": {"origins": "*"}})  # Adjust origins as needed
    

@app.route('/search', methods=['POST', 'OPTIONS'])
def search():
    print('search')
    
    # Load or Initiate Collection:
    collection = init_collection()
    print("collection: " + collection.name)
    test = collection.query(
            query_texts="hallo",
        )
    print(test)
    
    data = request.json
    query_texts = data.get('query_texts'),
    query_schlagwort = data.get('querySchlagwort'),
    n_results = data.get('n_results')
    filters = data.get('filters', {})
    where_conditions = []

    #--- Filter ---
    
    # Handle 'fach' filter
    fach_filters = filters.get('fach', [])
    if fach_filters:
        if len(fach_filters) == 1:
            where_conditions.append({"fach": {"$eq": fach_filters[0]}})
        else:
            where_conditions.append({
                "$or": [{"fach": {"$eq": fach}} for fach in fach_filters]
            })

    # Handle 'zyklus' filter, treated as a string
    zyklus_filters = filters.get('zyklus', [])
    if zyklus_filters:
        if len(zyklus_filters) == 1:
            where_conditions.append({"zyklus": {"$eq": str(zyklus_filters[0])}})  # Cast zyklus to str
        else:
            where_conditions.append({
                "$or": [{"zyklus": {"$eq": str(zyklus)}} for zyklus in zyklus_filters]  # Cast zyklus to str
            })

    where_clause = {}
    if len(where_conditions) == 1:
        where_clause = where_conditions[0]  # If only one condition, no need for $and
    elif len(where_conditions) > 1:
        where_clause["$and"] = where_conditions
       
    # Ensure n_results is 5 if nothing specified 
    if n_results is None or n_results == 0:
         n_results = 5
    
    #--- Perform Search ---

    # Perform the search query with the dynamically constructed where_clause
    if query_schlagwort[0] == '':
        results = collection.query(
            query_texts=query_texts,
            n_results=n_results,
            where=where_clause
        ),
        
    else:
        print(query_schlagwort[0])  # Print Schlagwort
        results = collection.query(
            query_texts=query_texts,
            where_document={"$contains": query_schlagwort[0]},  # Suche mit Schlagwort
            n_results=n_results,
            where=where_clause
        )
    
    
    # Return Results to JavaScript
    return jsonify(results)

if __name__ == '__main__':
    app.run(debug=True)
#------------------------------------------------------------End------------------------------------------------------------