import pandas as pd
import sys

total = 20623021
i = 1

sys.stdout.write("Loading: File\r")
df = pd.read_csv("urls.tsv", sep="\t")
sys.stdout.write("Loaded: File    \r")

for n in range(0, total, 10000):
    df[n:n+10000].to_csv("chunks/chunks-%s.tsv" % (i), sep="\t", index=False)
    sys.stdout.write("Chunk: %d       \r" % (i))
    i += 1