# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Import the frozen 20-paper snapshot into a dedicated local Neo4j instance.

Pure structural mapping, standard library only. No extraction/scientific changes/API.
"""
import argparse
import base64
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import time
import urllib.error
import urllib.request
ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / 'outputs/DAG_20papers_20261023'
RUNTIME = ROOT / 'work/neo4j20_runtime'
SHA = '4064f0fe3dbf4bd6ae539d9033963f196b7c8e448d8edc92ff6b25b6e2197b0d'
SCOPE = 'dag20-' + SHA[:16]
DEFAULT_OUT = Path('external_workspace/2026-10-25/dag20-restart/outputs/Neo4j_20papers_20261025')

def dump(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def protect():
    files = list(BASE.rglob('*'))
    for folder in ['outputs/decision_option_lab', 'outputs/DAG_reported_20261023']:
        files += list((ROOT / folder).rglob('*.py'))
    return {str(p.relative_to(ROOT)): digest(p) for p in files if p.is_file() and p.resolve() != Path(__file__).resolve()}

def credentials():
    return json.loads((RUNTIME / 'connection.local.json').read_text(encoding='utf-8'))

def query(statement, parameters=None):
    c = credentials()
    auth = base64.b64encode((c['username'] + ':' + c['password']).encode()).decode()
    payload = dump({'statements': [{'statement': statement, 'parameters': parameters or {}, 'resultDataContents': ['row']}]}).encode('utf-8')
    req = urllib.request.Request(c['http_uri'] + '/db/' + c['database'] + '/tx/commit', data=payload, headers={'Authorization': 'Basic ' + auth, 'Content-Type': 'application/json'})
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(req, timeout=120) as r:
        response = json.load(r)
    if response.get('errors'):
        raise RuntimeError(dump(response['errors']))
    result = response['results'][0]
    return [dict(zip(result['columns'], r['row'])) for r in result['data']]

def runtime_env():
    meta = json.loads((RUNTIME / 'runtime.json').read_text(encoding='utf-8'))
    drive = Path('N:/')
    if drive.exists():
        if not (drive / 'runtime.json').exists() or (drive / 'runtime.json').read_bytes() != (RUNTIME / 'runtime.json').read_bytes():
            raise RuntimeError('N: is occupied by another location; refusing to replace it')
    else:
        result = subprocess.run(['subst.exe', 'N:', str(RUNTIME)], capture_output=True)
        if result.returncode:
            raise RuntimeError('Could not create the dedicated local runtime drive mapping')
    home = drive / Path(meta['neo4j']['folder']).name
    java = drive / Path(meta['java']['folder']).name
    env = dict(os.environ, NEO4J_HOME=str(home), JAVA_HOME=str(java), NEO4J_CONF=str(home / 'conf'))
    env['PATH'] = str(java / 'bin') + os.pathsep + env.get('PATH', '')
    return (home, java / 'bin/java.exe', env)

def java_command(admin=False):
    home, java, _ = runtime_env()
    return [str(java), '-cp', str(home / 'lib/*'), '-Dbasedir=' + str(home), 'org.neo4j.server.startup.Neo4jAdminCommand' if admin else 'org.neo4j.server.startup.Neo4jCommand']

def start():
    home, java, env = runtime_env()
    if (RUNTIME / 'connection.local.json').exists():
        try:
            if query('RETURN 1 AS ready')[0]['ready'] == 1:
                print('Existing dedicated local Neo4j instance is ready.', flush=True)
                return
        except Exception:
            pass
    for port in [7474, 7687]:
        with socket.socket() as s:
            s.settimeout(0.3)
            if s.connect_ex(('127.0.0.1', port)) == 0:
                raise RuntimeError(f'Port {port} is occupied; refusing to change another instance')
    conf = '# Dedicated portable instance for frozen 20-paper import.\ninitial.dbms.default_database=neo4j\nserver.default_listen_address=127.0.0.1\nserver.default_advertised_address=127.0.0.1\nserver.bolt.enabled=true\nserver.bolt.listen_address=127.0.0.1:7687\nserver.bolt.advertised_address=127.0.0.1:7687\nserver.http.enabled=true\nserver.http.listen_address=127.0.0.1:7474\nserver.http.advertised_address=127.0.0.1:7474\nserver.https.enabled=false\ndbms.security.auth_enabled=true\ndbms.usage_report.enabled=false\nserver.memory.heap.initial_size=256m\nserver.memory.heap.max_size=768m\nserver.memory.pagecache.size=256m\n'
    (home / 'conf/neo4j.conf').write_text(conf, encoding='utf-8')
    secretfile = RUNTIME / 'connection.local.json'
    if not secretfile.exists() or (not (home / 'data/dbms/auth.ini').exists() and (not (home / 'data/databases/system').exists())):
        c = credentials() if secretfile.exists() else {'http_uri': 'http://127.0.0.1:7474', 'bolt_uri': 'bolt://127.0.0.1:7687', 'database': 'neo4j', 'username': 'neo4j', 'password': 'Dag20-' + secrets.token_urlsafe(22)}
        result = subprocess.run(java_command(True) + ['dbms', 'set-initial-password', c['password'], '--require-password-change=false'], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode:
            raise RuntimeError((result.stdout + result.stderr).replace(c['password'], '[REDACTED]'))
        secretfile.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding='utf-8')
    with (RUNTIME / 'console.log').open('ab') as log:
        proc = subprocess.Popen(java_command() + ['console'], cwd=ROOT, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW | subprocess.CREATE_NEW_PROCESS_GROUP)
    (RUNTIME / 'launcher.json').write_text(json.dumps({'pid': proc.pid, 'home': str(home)}, indent=2), encoding='utf-8')
    print('Starting isolated Neo4j on 127.0.0.1:7474 / 7687...', flush=True)
    for attempt in range(90):
        try:
            if query('RETURN 1 AS ready')[0]['ready'] == 1:
                print('Neo4j ready; authentication enabled.', flush=True)
                return
        except Exception:
            pass
        if proc.poll() is not None:
            raise RuntimeError('Neo4j launcher exited. Inspect work/neo4j20_runtime/console.log')
        time.sleep(1)
    raise RuntimeError('Neo4j did not become ready in 90 seconds; inspect local console log')

def stop():
    _, _, env = runtime_env()
    result = subprocess.run(java_command() + ['stop'], cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
    print(result.stdout)
    if result.returncode:
        raise RuntimeError(result.stderr)

def compile_graph():
    raw = (BASE / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json').read_bytes()
    if hashlib.sha256(raw).hexdigest() != SHA:
        raise RuntimeError('Frozen snapshot SHA256 differs from handoff')
    text = raw.decode('utf-8')
    data = json.loads(text)
    nodes, edges = ([], [])
    method_map = {m['id']: m for m in data['classification']['methods']}
    row_map = {r['source_ref']: r for r in data['classification']['rows']}

    def uid(label, logical):
        return SCOPE + ':' + label + ':' + logical

    def scalars(record):
        props = {}
        for k, v in record.items():
            if v is None:
                continue
            if isinstance(v, (str, bool, int, float)):
                props[k] = v
            elif isinstance(v, list) and all((isinstance(x, str) for x in v)):
                props[k] = v
        return props

    def node(label, logical, record, path, extra=None):
        props = {'logical_id': logical, 'import_scope': SCOPE, 'snapshot_sha256': SHA, 'source_path': path, 'record_json': dump(record), **scalars(record), **(extra or {})}
        nodes.append({'label': label, 'uid': uid(label, logical), 'props': props})
        return uid(label, logical)

    def edge(kind, a, b, record=None, extra=None):
        props = {'import_scope': SCOPE, 'snapshot_sha256': SHA, **(extra or {})}
        if record is not None:
            props.update(scalars(record), record_json=dump(record))
        eid = hashlib.sha256((kind + '|' + a + '|' + b).encode()).hexdigest()
        edges.append({'type': kind, 'uid': SCOPE + ':' + eid, 'from': a, 'to': b, 'props': props})
    snapshot = node('Snapshot', 'baseline', {'version': data['version']}, '/', {'raw_json': text, 'status': 'frozen', 'byte_length': len(raw)})
    for i, family in enumerate(data['classification']['families']):
        f = node('Family', family['id'], family, f'/classification/families/{i}')
        edge('CONTAINS_FAMILY', snapshot, f)
    for i, method in enumerate(data['classification']['methods']):
        m = node('Method', method['id'], method, f'/classification/methods/{i}')
        edge('HAS_METHOD', uid('Family', method['family_id']), m)
    for pi, paper in enumerate(data['papers']):
        alias = paper['alias']
        p = node('Paper', alias, paper, f'/papers/{pi}', {'name': paper['title']})
        edge('CONTAINS_PAPER', snapshot, p)
        h1 = node('H1', alias + ':H1', paper['research_context']['h1'], f'/papers/{pi}/research_context/h1', {'paper_alias': alias})
        edge('HAS_H1', p, h1)
        for di, decision in enumerate(paper['space']['decisions']):
            dref = alias + ':' + decision['id']
            methods_text, parameters_text, semantics_text = ([], [], [])
            for option in decision['options']:
                ref = dref + ':' + option['id']
                row = row_map[ref]
                prefix = ref + ' ' + option['label']
                if not row['components']:
                    methods_text.append(prefix + '：\u539f\u8bb0\u5f55\u6ca1\u6709\u72ec\u7acb\u65b9\u6cd5\u7ec4\u4ef6')
                    semantics_text.append(prefix + '：\u539f\u8bb0\u5f55\u6ca1\u6709\u7ec4\u4ef6\u7ea7\u6570\u636e\u5217\u8bed\u4e49')
                for setting in row.get('option_parameters', []):
                    parameters_text.append(prefix + '/Option\u8bbe\u7f6e · ' + setting['name'] + ' = ' + dump(setting.get('value')))
                for comp in row['components']:
                    cref = ref + '/' + comp['id']
                    enrichment = data['enriched_components'][cref]
                    methods_text.append(cref + ' ' + method_map[comp['method_id']]['name'])
                    for setting in enrichment['parameters']:
                        parameters_text.append(cref + ' · ' + setting['name'] + ' = ' + dump(setting.get('value')) + (' 〔' + setting['scope'] + '〕' if setting.get('scope') else ''))
                    for col in enrichment['data_columns']:
                        semantics_text.append(cref + ' · ' + col['name'] + '：' + (col.get('meaning') or '\u539f\u8bb0\u5f55\u672a\u8bf4\u660e\u8bed\u4e49') + ('；\u89d2\u8272：' + col['role'] if col.get('role') else '') + ('；\u5355\u4f4d：' + col['unit'] if col.get('unit') else '') + ('；\u4e0eH1\u5173\u7cfb：' + col['h1_relation'] if col.get('h1_relation') else ''))
            display = {'paper_alias': alias, 'name': decision['label'], 'method': '\n'.join(methods_text) or '\u539f\u8bb0\u5f55\u6ca1\u6709\u72ec\u7acb\u65b9\u6cd5\u7ec4\u4ef6', 'parameters': '\n'.join(parameters_text) or '\u539f\u8bb0\u5f55\u672a\u5217\u51fa\u53c2\u6570', 'column_semantics': '\n'.join(semantics_text) or '\u539f\u8bb0\u5f55\u6ca1\u6709\u6570\u636e\u5217\u8bed\u4e49', 'h1': paper['research_context']['h1']['text'], 'display_fields_are_projection': True}
            d = node('Decision', dref, decision, f'/papers/{pi}/space/decisions/{di}', display)
            edge('HAS_DECISION', p, d)
            edge('IN_CONTEXT_OF', d, h1)
            for option in decision['options']:
                ref = dref + ':' + option['id']
                record = data['original_options'][ref]
                row = row_map[ref]
                o = node('Option', ref, record, '/original_options/' + ref, {**scalars(option), 'name': option['label'], 'classification_row_json': dump(row), 'paper_alias': alias})
                edge('HAS_OPTION', d, o)
                for si, setting in enumerate(row.get('option_parameters', [])):
                    par = node('Parameter', ref + '/option_parameter/' + str(si), setting, '/classification/rows/' + str(data['classification']['rows'].index(row)) + '/option_parameters/' + str(si), {'owner_level': 'Option', 'value_json': dump(setting.get('value')), 'value_type': type(setting.get('value')).__name__})
                    edge('HAS_PARAMETER', o, par)
                for comp in row['components']:
                    cref = ref + '/' + comp['id']
                    enrichment = data['enriched_components'][cref]
                    ep = '/enriched_components/' + cref.replace('~', '~0').replace('/', '~1')
                    c = node('Component', cref, comp, '/classification/rows/' + str(data['classification']['rows'].index(row)) + '/components/' + str(row['components'].index(comp)), {'enrichment_json': dump(enrichment), 'name': comp['id'] + ' · ' + method_map[comp['method_id']]['name'], 'paper_alias': alias})
                    edge('HAS_COMPONENT', o, c)
                    edge('USES_METHOD', c, uid('Method', comp['method_id']))
                    for ci, col in enumerate(enrichment['data_columns']):
                        extra = {'paper_alias': alias}
                        if col.get('measured_features'):
                            extra.update({'measured_' + k: v for k, v in scalars(col['measured_features']).items()})
                        column = node('ColumnBinding', cref + '/column/' + str(ci), col, ep + '/data_columns/' + str(ci), extra)
                        edge('HAS_COLUMN', c, column)
                    for si, setting in enumerate(enrichment['parameters']):
                        par = node('Parameter', cref + '/parameter/' + str(si), setting, ep + '/parameters/' + str(si), {'owner_level': 'Component', 'value_json': dump(setting.get('value')), 'value_type': type(setting.get('value')).__name__})
                        edge('HAS_PARAMETER', c, par)
        for dep in paper['space']['dependency_edges']:
            edge('DECISION_DEPENDENCY', uid('Decision', alias + ':' + dep['from']), uid('Decision', alias + ':' + dep['to']), dep, {'paper_alias': alias, 'meaning': '\u539f\u8bba\u6587\u7684\u524d\u7f6eDecision\u6307\u5411\u4f9d\u8d56\u5b83\u7684\u540e\u7eedDecision'})
    ids = {n['uid'] for n in nodes}
    if len(ids) != len(nodes) or len({e['uid'] for e in edges}) != len(edges):
        raise RuntimeError('Duplicate import identities')
    assert all((e['from'] in ids and e['to'] in ids for e in edges))
    return (data, nodes, edges)

def import_graph(out):
    before = protect()
    data, nodes, edges = compile_graph()
    existing = query('MATCH (n:DAG20) RETURN DISTINCT n.import_scope AS scope')
    if any((r['scope'] != SCOPE for r in existing)):
        raise RuntimeError('Unexpected DAG20 scope in target instance; import stopped')
    query('CREATE CONSTRAINT dag20_uid IF NOT EXISTS FOR (n:DAG20) REQUIRE n.uid IS UNIQUE')
    query('CREATE INDEX dag20_scope IF NOT EXISTS FOR (n:DAG20) ON (n.import_scope)')
    by_label, by_type = (defaultdict(list), defaultdict(list))
    for n in nodes:
        by_label[n['label']].append(n)
    for e in edges:
        by_type[e['type']].append(e)
    for label, records in by_label.items():
        for i in range(0, len(records), 200):
            r = query(f'UNWIND $rows AS row MERGE (n:DAG20:{label} {{uid:row.uid}}) SET n += row.props RETURN count(n) AS count', {'rows': records[i:i + 200]})
            assert r[0]['count'] == len(records[i:i + 200])
        print('Imported', label, len(records), flush=True)
    for kind, records in by_type.items():
        for i in range(0, len(records), 400):
            r = query(f'UNWIND $rows AS row MATCH (a:DAG20 {{uid:row.from}}), (b:DAG20 {{uid:row.to}}) MERGE (a)-[r:{kind} {{uid:row.uid}}]->(b) SET r += row.props RETURN count(r) AS count', {'rows': records[i:i + 400]})
            assert r[0]['count'] == len(records[i:i + 400])
        print('Imported relationship', kind, len(records), flush=True)
    if before != protect():
        raise RuntimeError('Protected source files changed')
    out.mkdir(parents=True, exist_ok=True)
    export = {'scope': SCOPE, 'snapshot_sha256': SHA, 'nodes': nodes, 'relationships': edges}
    (out / '\u7ed3\u6784\u5316\u5bfc\u5165\u5305.json').write_text(dump(export), encoding='utf-8')
    (out / '\u539f\u6587\u4ef6\u4fdd\u62a4\u6838\u9a8c.json').write_text(json.dumps({'protected_count': len(before), 'all_unchanged': True, 'snapshot_sha256': SHA}, ensure_ascii=False, indent=2), encoding='utf-8')
    return verify(out)

def verify(out):
    data, nodes, edges = compile_graph()
    expected_nodes = dict(Counter((n['label'] for n in nodes)))
    expected_edges = dict(Counter((e['type'] for e in edges)))
    actual_nodes = {r['label']: r['count'] for r in query('MATCH (n:DAG20 {import_scope:$scope}) UNWIND labels(n) AS label WITH label WHERE label <> "DAG20" RETURN label, count(*) AS count', {'scope': SCOPE})}
    actual_edges = {r['type']: r['count'] for r in query('MATCH (:DAG20 {import_scope:$scope})-[r]->(:DAG20 {import_scope:$scope}) RETURN type(r) AS type, count(*) AS count', {'scope': SCOPE})}
    assert expected_nodes == actual_nodes, (expected_nodes, actual_nodes)
    assert expected_edges == actual_edges, (expected_edges, actual_edges)
    loaded_nodes = {r['uid']: r['props'] for r in query('MATCH (n:DAG20 {import_scope:$scope}) RETURN n.uid AS uid, properties(n) AS props', {'scope': SCOPE})}
    for n in nodes:
        assert loaded_nodes[n['uid']] == {'uid': n['uid'], **n['props']}, n['uid']
    loaded_edges = {r['uid']: r for r in query('MATCH (a:DAG20 {import_scope:$scope})-[r]->(b:DAG20 {import_scope:$scope}) RETURN r.uid AS uid, a.uid AS start, b.uid AS end, type(r) AS type, properties(r) AS props', {'scope': SCOPE})}
    for e in edges:
        r = loaded_edges[e['uid']]
        assert (r['start'], r['end'], r['type'], r['props']) == (e['from'], e['to'], e['type'], {'uid': e['uid'], **e['props']}), e['uid']
    raw = query('MATCH (s:DAG20:Snapshot {import_scope:$scope}) RETURN s.raw_json AS raw', {'scope': SCOPE})[0]['raw']
    assert hashlib.sha256(raw.encode('utf-8')).hexdigest() == SHA
    graph = query('MATCH (a:DAG20:Decision {import_scope:$scope})-[r:DECISION_DEPENDENCY]->(b:DAG20:Decision) RETURN a.logical_id AS start, b.logical_id AS end, r.reason AS reason', {'scope': SCOPE})
    expected = {(p['alias'] + ':' + e['from'], p['alias'] + ':' + e['to'], e['reason']) for p in data['papers'] for e in p['space']['dependency_edges']}
    assert {(r['start'], r['end'], r['reason']) for r in graph} == expected
    two_hops = query('MATCH p=(a:DAG20:Decision {logical_id:"P1:D1",import_scope:$scope})-[:DECISION_DEPENDENCY*1..2]->(b) RETURN [n IN nodes(p)|n.logical_id] AS path ORDER BY length(p)', {'scope': SCOPE})
    ideal = query('MATCH (d:DAG20:Decision {import_scope:$scope}) RETURN d.logical_id AS id, d.method AS method, d.parameters AS parameters, d.column_semantics AS column_semantics, d.h1 AS h1 ORDER BY id', {'scope': SCOPE})
    assert len(ideal) == 185 and all((all((r[k] for k in ['method', 'parameters', 'column_semantics', 'h1'])) for r in ideal))
    assert query('MATCH (:DAG20:Method {import_scope:$scope})-[r:DECISION_DEPENDENCY]->(:DAG20:Method) RETURN count(r) AS count', {'scope': SCOPE})[0]['count'] == 0
    version = query('CALL dbms.components() YIELD name, versions, edition RETURN name, versions, edition')
    report = {'status': 'imported_and_readback_verified', 'scope': SCOPE, 'neo4j': version, 'http_uri': 'http://127.0.0.1:7474', 'bolt_uri': 'bolt://127.0.0.1:7687', 'database': 'neo4j', 'snapshot_sha256': SHA, 'nodes': actual_nodes, 'relationships': actual_edges, 'total_nodes': len(nodes), 'total_relationships': len(edges), 'all_node_properties_readback_equal': True, 'all_relationship_properties_and_endpoints_equal': True, 'snapshot_roundtrip_sha256_equal': True, 'ideal_nodes_with_all_four_fields': len(ideal), 'method_dependency_edges_created': 0, 'deepseek_calls': 0, 'example_two_hop_paths': two_hops}
    out.mkdir(parents=True, exist_ok=True)
    (out / '\u5bfc\u5165\u6838\u9a8c.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (out / '\u6570\u636e\u5e93\u8bfb\u56de_\u7406\u60f3\u56fe\u8282\u70b9.json').write_text(json.dumps(ideal, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2), flush=True)
    return report

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['start', 'stop', 'import', 'verify', 'status'])
    parser.add_argument('--out', type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()
    if args.action == 'start':
        start()
    elif args.action == 'stop':
        stop()
    elif args.action == 'import':
        import_graph(args.out)
    elif args.action == 'verify':
        verify(args.out)
    else:
        print(json.dumps(query('CALL dbms.components() YIELD name, versions, edition RETURN name,versions,edition'), ensure_ascii=False, indent=2))
if __name__ == '__main__':
    main()
