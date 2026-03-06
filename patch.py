with open("tests/test_demo.py", "r") as f:
    lines = f.readlines()

new_lines = []
skip = False
for line in lines:
    if line.startswith("<<<<<<< Updated upstream"):
        skip = True
        continue
    if line.startswith("======="):
        skip = False
        continue
    if line.startswith(">>>>>>> Stashed changes"):
        continue
    if not skip:
        new_lines.append(line)

with open("tests/test_demo.py", "w") as f:
    f.writelines(new_lines)
