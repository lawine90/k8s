from fastapi import FastAPI, Query
from gensim.models import KeyedVectors
import os

app = FastAPI()
model = KeyedVectors.load_word2vec_format("/models/w2v.bin", binary=True)

@app.get("/similar")
def similar(word: str = Query(...), topn: int = Query(5)):
    if word not in model:
        return {"word": word, "related": []}
    sims = model.most_similar(word, topn=topn)
    return {"word": word, "related": [[w, float(s)] for w,s in sims]}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
