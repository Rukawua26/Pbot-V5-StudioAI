import sys

print("Iniciando fix...")
with open("main.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "# [V118-PRO FIX] Filtrado estricto y validación pesimista" in line and not line.startswith("                "):
        print("Found target block at line", i+1)
        # Indent everything until "intruso_count += 1"
        for j in range(i, i+60):
            if lines[j].strip() == "":
                lines[j] = "                \n"
            else:
                lines[j] = "    " + lines[j]
            if "intruso_count += 1" in lines[j]:
                break
        
        with open("main.py", "w") as f2:
            f2.writelines(lines)
        print("Fixed indentation!")
        sys.exit(0)

print("Target not found")
