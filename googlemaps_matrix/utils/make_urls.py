from os import sep
import urllib.parse
import pandas as pd

locations = open('locations.txt','r').readlines()
latlngs = open('latlng.txt','r').readlines()

d = {"URL": []}


for location in locations:
    location = urllib.parse.quote_plus(location.replace("\n", ""))
    for latlng in latlngs:
        lat, lng = latlng.split()
        url = f"https://www.google.com/maps/search/{location}/@{lat},{lng},17z"
        d["URL"].append(url)

df = pd.DataFrame(d)
df.to_csv("urls.tsv", sep="\t", index=False)

# with open("urls.txt", "w") as file_object:
#     for location in locations:
#         location = urllib.parse.quote_plus(location.replace("\n", ""))
#         for latlng in latlngs:
#             lat, lng = latlng.split()
#             url = f"https://www.google.com/maps/search/{location}/@{lat},{lng},17z"
#             file_object.write(url)
#             file_object.write("\n")
#             #print(location, latlng)
