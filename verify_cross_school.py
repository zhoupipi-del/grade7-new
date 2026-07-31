"""Task #1254: Cross-School Access Rejection Tests"""
import requests
import json

BASE = 'http://127.0.0.1:8000/api/v1'


def login(username, password):
    r = requests.post(f'{BASE}/auth/login', json={'username': username, 'password': password})
    if r.status_code == 200:
        return r.json()['access_token']
    return None


def get(url, token, params=None):
    headers = {'Authorization': f'Bearer {token}'}
    r = requests.get(url, headers=headers, params=params or {})
    return r.status_code, r.json() if r.headers.get('content-type', '').startswith('application/json') else r.text


def extract_list(data):
    """Handle both list and paginated dict responses."""
    if isinstance(data, list):
        return data
    if isinstance(data, dict) and 'items' in data:
        return data['items']
    return []


print('=' * 60)
print('TASK #1254: CROSS-SCHOOL ACCESS REJECTION TESTS')
print('=' * 60)

# Step 1: Login as school_id=1 admin
t1 = login('admin', 'admin123')
print(f'\n[1] Login school_id=1 admin: {"OK" if t1 else "FAIL"}')

if not t1:
    print('FATAL: Cannot login as school_id=1 admin')
    exit(1)

# Step 2: Get school_id=1 context
print(f'\n[2] School 1 Context:')
code, data = get(f'{BASE}/grades', t1)
items = extract_list(data)
print(f'  Grades: {len(items)} items, status={code}')

code, data = get(f'{BASE}/classes', t1)
items = extract_list(data)
print(f'  Classes: {len(items)} items, status={code}')

code, data = get(f'{BASE}/students', t1)
items = extract_list(data)
print(f'  Students: {len(items)} items, status={code}')

# Step 3: Quick isolation check - school_id=1 token should NOT see school_id=2 data
print(f'\n[3] Quick isolation check (school_id=1 token):')
code, data = get(f'{BASE}/grades', t1)
items = extract_list(data)
s2_entries = [g for g in items if g.get('school_id') == 2]
print(f'  grades with school_id=2: {len(s2_entries)} (should be 0)')
all_schools = set(g.get('school_id') for g in items if g.get('school_id'))
print(f'  grades school_ids seen: {all_schools}')

code, data = get(f'{BASE}/classes', t1)
items = extract_list(data)
s2_entries = [c for c in items if c.get('school_id') == 2]
print(f'  classes with school_id=2: {len(s2_entries)} (should be 0)')

code, data = get(f'{BASE}/students', t1)
items = extract_list(data)
s2_entries = [s for s in items if s.get('school_id') == 2]
print(f'  students with school_id=2: {len(s2_entries)} (should be 0)')

# Step 4: Get school_id=2 resource IDs for targeted tests
t2 = login('sandbox_admin', 'admin123')
print(f'\n[4] Login school_id=2 sandbox_admin: {"OK" if t2 else "FAIL"}')

g2_ids = []
c2_ids = []
s2_ids = []

if t2:
    code, data = get(f'{BASE}/grades', t2)
    g2_ids = [g['id'] for g in extract_list(data)]
    print(f'  School 2 grade IDs: {g2_ids}')

    code, data = get(f'{BASE}/classes', t2)
    c2_ids = [c['id'] for c in extract_list(data)]
    print(f'  School 2 class IDs: {c2_ids}')

    code, data = get(f'{BASE}/students', t2)
    s2_ids = [s['id'] for s in extract_list(data)]
    print(f'  School 2 student IDs: {s2_ids}')

# Step 5: Targeted cross-school access tests
# CRITICAL: Must use a non-MS_ADMIN user from school 1.
# MS_ADMIN bypasses verify_entity_ownership by design.
t1_teacher = login('ct_2501', 'admin123')
print(f'\n[5] Login school_id=1 class_teacher ct_2501: {"OK" if t1_teacher else "FAIL"}')
if not t1_teacher:
    print('WARNING: Cannot login as ct_2501, falling back to admin (will show false negatives)')
    t1_teacher = t1

print(f'\n[6] TARGETED CROSS-SCHOOL ACCESS TESTS:')
print(f'  Using school_id=1 class_teacher token to access school_id=2 resources...\n')

results = {}

# 6a: Grade detail endpoints
if g2_ids:
    for gid in g2_ids[:2]:
        code, resp = get(f'{BASE}/grades/{gid}', t1_teacher)
        if code in (403, 404):
            result = 'BLOCKED'
        elif code == 200:
            result = f'LEAKED - returned data'
        else:
            result = f'LEAKED({code})'
        results[f'GET /grades/{gid}'] = result
        print(f'  GET /grades/{gid}: status={code} -> {result}')
        if code == 200:
            print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

# 6b: Class detail endpoints
if c2_ids:
    for cid in c2_ids[:2]:
        code, resp = get(f'{BASE}/classes/{cid}', t1_teacher)
        if code in (403, 404):
            result = 'BLOCKED'
        elif code == 200:
            result = f'LEAKED - returned data'
        else:
            result = f'LEAKED({code})'
        results[f'GET /classes/{cid}'] = result
        print(f'  GET /classes/{cid}: status={code} -> {result}')
        if code == 200:
            print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

# 6c: Student detail endpoints
if s2_ids:
    for sid in s2_ids[:3]:
        code, resp = get(f'{BASE}/students/{sid}', t1_teacher)
        if code in (403, 404):
            result = 'BLOCKED'
        elif code == 200:
            result = f'LEAKED - returned data'
        else:
            result = f'LEAKED({code})'
        results[f'GET /students/{sid}'] = result
        print(f'  GET /students/{sid}: status={code} -> {result}')
        if code == 200:
            print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

        # Growth timeline for student
        code, resp = get(f'{BASE}/growth/timeline/{sid}', t1_teacher)
        if code in (403, 404):
            result = 'BLOCKED'
        elif code == 200:
            result = f'LEAKED - returned data'
        else:
            result = f'LEAKED({code})'
        results[f'GET /growth/timeline/{sid}'] = result
        print(f'  GET /growth/timeline/{sid}: status={code} -> {result}')

# 6d: Attendance dashboard with school 2 class
if c2_ids:
    code, resp = get(f'{BASE}/attendance/dashboard', t1_teacher, {'class_id': c2_ids[0]})
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'attendance/dashboard?class_id={c2_ids[0]}'] = result
    print(f'  GET /attendance/dashboard?class_id={c2_ids[0]}: status={code} -> {result}')

# 6e: Behavior records with school 2 class
if c2_ids:
    code, resp = get(f'{BASE}/behavior/records', t1_teacher, {'class_id': c2_ids[0]})
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'behavior/records?class_id={c2_ids[0]}'] = result
    print(f'  GET /behavior/records?class_id={c2_ids[0]}: status={code} -> {result}')

# 6f: Evaluation scores is a POST endpoint (not GET). Skip this test.
#     The actual student-level endpoint GET /evaluation/students/{id}/scores is tested in 6h.

# 6g: Risk models warnings with school 2 grade
if c2_ids and g2_ids:
    code, resp = get(f'{BASE}/risk_models/warnings', t1_teacher, {'grade_id': g2_ids[0]})
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'risk_models/warnings?grade_id={g2_ids[0]}'] = result
    print(f'  GET /risk_models/warnings?grade_id={g2_ids[0]}: status={code} -> {result}')

# 6h: P0 -- Evaluation student scores (school 2 student via school 1 token)
if s2_ids:
    code, resp = get(f'{BASE}/evaluation/students/{s2_ids[0]}/scores', t1_teacher)
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'evaluation/students/{s2_ids[0]}/scores'] = result
    print(f'  GET /evaluation/students/{s2_ids[0]}/scores: status={code} -> {result}')
    if code == 200:
        print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

# 6i: P0 -- Evaluation class ranking (school 2 class via school 1 token)
if c2_ids:
    code, resp = get(f'{BASE}/evaluation/classes/{c2_ids[0]}/ranking', t1_teacher)
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'evaluation/classes/{c2_ids[0]}/ranking'] = result
    print(f'  GET /evaluation/classes/{c2_ids[0]}/ranking: status={code} -> {result}')
    if code == 200:
        print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

# 6j: P0 -- Evaluation student score logs (school 2 student via school 1 token)
if s2_ids:
    code, resp = get(f'{BASE}/evaluation/students/{s2_ids[0]}/logs', t1_teacher)
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'evaluation/students/{s2_ids[0]}/logs'] = result
    print(f'  GET /evaluation/students/{s2_ids[0]}/logs: status={code} -> {result}')
    if code == 200:
        print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

# 6k: P1 -- Risk models dashboard with school 2 class
if c2_ids:
    code, resp = get(f'{BASE}/risk_models/dashboard', t1_teacher, {'class_id': c2_ids[0]})
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'risk_models/dashboard?class_id={c2_ids[0]}'] = result
    print(f'  GET /risk_models/dashboard?class_id={c2_ids[0]}: status={code} -> {result}')
    if code == 200:
        print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

# 6l: P1 -- Risk models monitor-panel with school 2 class
if c2_ids:
    code, resp = get(f'{BASE}/risk_models/monitor-panel', t1_teacher, {'class_id': c2_ids[0]})
    if code in (403, 404):
        result = 'BLOCKED'
    elif code == 200:
        result = f'LEAKED - returned data'
    else:
        result = f'LEAKED({code})'
    results[f'risk_models/monitor-panel?class_id={c2_ids[0]}'] = result
    print(f'  GET /risk_models/monitor-panel?class_id={c2_ids[0]}: status={code} -> {result}')
    if code == 200:
        print(f'    RESPONSE: {json.dumps(resp, ensure_ascii=False)[:200]}')

# Step 7: MS_ADMIN cross-school access (should see both)
print(f'\n[7] MS_ADMIN CROSS-SCHOOL ACCESS (should be allowed):')
code, data = get(f'{BASE}/grades', t1)
items = extract_list(data)
school_ids = set(g.get('school_id') for g in items if g.get('school_id'))
print(f'  MS_ADMIN sees grades from schools: {school_ids}')
has_both = len(school_ids) > 1
print(f'  MS_ADMIN cross-school: {"OK (sees both)" if has_both else "RESTRICTED (only sees one)"}')

# Also test MS_ADMIN can access school 2 evaluation endpoints
if s2_ids:
    code, _ = get(f'{BASE}/evaluation/students/{s2_ids[0]}/scores', t1)
    print(f'  MS_ADMIN evaluation/students/{s2_ids[0]}/scores: status={code} ("OK" if code == 200 else "WARN")')

# Summary
print(f'\n{"=" * 60}')
print('CROSS-SCHOOL ACCESS RESULTS SUMMARY:')
leaks = [k for k, v in results.items() if 'LEAKED' in v]
blocked = [k for k, v in results.items() if 'BLOCKED' in v]
print(f'  Total tests: {len(results)}')
print(f'  Blocked: {len(blocked)}')
print(f'  Leaked:  {len(leaks)}')
if leaks:
    print(f'  LEAK DETAILS:')
    for k in leaks:
        print(f'    - {k}: {results[k]}')
print(f'  Cross-school isolation: {"PASS" if len(leaks) == 0 else "FAIL"}')
print('=' * 60)
