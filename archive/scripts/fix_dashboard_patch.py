"""fix_dashboard_patch.py — 修复 dashboard 补丁位置错误"""
import os

BASE = "/root/backend"
f = os.path.join(BASE, "modules/dashboard/routers.py")

with open(f, 'r', encoding='utf-8') as fh:
    content = fh.read()

# Step 1: Remove wrongly placed check (outside function, before @router decorator)
bad_block = "# P0 多租户隔离：校验 class_id 是否属于当前用户学校\nawait verify_entity_ownership(db, SchoolClass, class_id, current_user, '\u7430\u7ea7\u4e0d\u5b58\u5b8d')\n\n@router.get"
good_block = "@router.get"
if bad_block in content:
    content = content.replace(bad_block, good_block, 1)
    print("Step 1: Removed misplaced check outside function")
else:
    print("Step 1 SKIP: misplaced block not found")

# Step 2: Insert check inside function body (after docstring, before import)
# The docstring uses triple quotes with em dash
# We search for the docstring line + the next import line
lines = content.split('\n')
for i, line in enumerate(lines):
    if '\u7430\u7ea7\u4e0b\u94b7\u660e\u7ec6' in line and 'class-drilldown' not in line:
        # This is the docstring inside the function
        indent = len(line) - len(line.lstrip())
        indent_str = ' ' * indent
        check1 = indent_str + "# P0 \u591a\u79c1\u6237\u9694\u79bb\uff1a\u6821\u9a8c class_id \u662f\u5426\u5c5e\u4e8e\u5f53\u524d\u7528\u6237\u5b66\u6821"
        check2 = indent_str + "await verify_entity_ownership(db, SchoolClass, class_id, current_user, '\u7430\u7ea7\u4e0d\u5b58\u5b8d')"
        # Check if the import line is next
        next_line = lines[i + 1] if i + 1 < len(lines) else ''
        if 'from modules.behavior' in next_line or next_line.strip().startswith('from modules'):
            # Insert between docstring and import
            new_lines = lines[:i+1] + [check1, check2, '', next_line] + lines[i+2:]
            content = '\n'.join(new_lines)
            print("Step 2: Inserted check in correct position (inside function)")
            break
        else:
            print(f"Step 2: Unexpected next line: {next_line[:60]}")

with open(f, 'w', encoding='utf-8') as fh:
    fh.write(content)
print("Written dashboard/routers.py")
