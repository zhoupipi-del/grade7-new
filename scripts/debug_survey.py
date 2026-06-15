import json

with open(r"C:\Users\Administrator\AppData\Local\Temp\survey_26930973_answers_p1.json", "r", encoding="utf-8") as f:
    data = json.load(f)

ans = data["list"][0]
print(f"Answer ID: {ans['answer_id']}")
print(f"Total questions across all pages:")

all_qs = []
for p in ans["answer"]:
    for q in p["questions"]:
        all_qs.append(q)

print(f"Total: {len(all_qs)} questions")

# Print first 6
for i, q in enumerate(all_qs[:6]):
    title = q.get("title", "")[:40]
    qtype = q.get("type", "")
    text = q.get("text", "")
    opts = q.get("options")
    print(f"\n  Q{i+1}. [{qtype}] {title}")
    if text:
        print(f"     text: {repr(text[:30])}")
    # Check options - print raw first option to understand structure
    if opts:
        print(f"     Options count: {len(opts)}")
        first_opt = opts[0]
        print(f"     First option keys: {list(first_opt.keys())}")
        print(f"     First option: {json.dumps(first_opt, ensure_ascii=False)}")
        # Check selected
        for opt in opts:
            selected = opt.get("selected", opt.get("checked", False))
            mark = "V" if selected else " "
            txt = opt.get("text", "")[:20]
            print(f"     [{mark}] {txt}")

# Find first option that's selected
print("\n\n=== Searching for selected options ===")
found = False
for q in all_qs:
    opts = q.get("options")
    if opts:
        for opt in opts:
            if opt.get("selected"):
                print(f"\n  Q: {q.get('title','')[:50]}")
                print(f"  Selected option: {json.dumps(opt, ensure_ascii=False)}")
                found = True
                break
    if found:
        break

if not found:
    print("WARNING: No options with 'selected'=True found!")
    print("Checking if options use a different key...")
    for q in all_qs[:5]:
        opts = q.get("options")
        if opts:
            print(f"\n  Q: {q.get('title','')[:40]}")
            for opt in opts[:2]:
                print(f"    {json.dumps(opt, ensure_ascii=False)}")
