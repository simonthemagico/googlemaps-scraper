import ast

with open('element.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# Convert the string representation of the Python literal into an actual Python object
data = ast.literal_eval(content)

z=0
for d in data:
    if type(d) == list:
        if "4-star tourist hotel" in d:
            print(z)
            print(data[z])
    elif d == None or str(d).isnumeric():
        pass
    elif "4-star tourist hotel" in d:
        print(d)
        print(z)
        raise
    z+=1
