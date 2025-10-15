from gensim.models import Word2Vec

sentences=[]

with open("/mnt/data/corpus.txt","r") as f:
    for line in f:
        sentences.append(line.strip().split())

model = Word2Vec(sentences, vector_size=100, window=5, min_count=1, workers=2)
model.wv.save_word2vec_format("/mnt/data/w2v.bin", binary=True)

print("Saved /mnt/data/w2v.bin")