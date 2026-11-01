# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Offline audit of generated records; no manual scientific labels or graph edits."""
import argparse
import copy
import hashlib
from pathlib import Path
import subprocess
import sys
import scale_trial as s

def check(out, replay=True):
    selection = s.read(out / 'selection.json')
    data = s.read(out / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json')
    base = s.baseline(out)
    c = data['classification']
    o = data['original_options']
    profiles = s.read(out / '\u6570\u636e\u5143\u7279\u5f81.json')
    count = len(selection['papers'])
    assert count == len({p['paper_id'] for p in selection['papers']})
    assert len(data['papers']) == count and sum((p['baseline'] for p in selection['papers'])) == 3
    if (out / 'inputs/seed.json').exists():
        seed = s.read(out / 'inputs/seed.json')
        final_rows = {r['source_ref']: r for r in c['rows']}
        assert s.sha(out / 'inputs/seed.json') == selection['seed_snapshot_sha256']
        for key in ['families', 'methods']:
            final = {x['id']: x for x in c[key]}
            for x in seed['classification'][key]:
                assert final[x['id']] == x
        for row in seed['classification']['rows']:
            assert final_rows[row['source_ref']] == row
        for ref, x in seed['original_options'].items():
            assert o[ref] == x
        for k, x in seed['enriched_components'].items():
            assert data['enriched_components'][k] == x
        for p in seed['papers']:
            shown = next((x for x in data['papers'] if x['alias'] == p['alias']))
            for key in ['paper_id', 'title', 'space', 'research_context', 'data_profile', 'enrichment_limits', 'source_coverage']:
                assert shown[key] == p[key]
        assert s.method_coverage(selection, c, o, out) == data['method_coverage']
    assert not s.standard_pipeline.classification_errors(c, list(o))
    assert all((x['option']['origin'] == 'reported' for x in o.values()))
    for ref, x in base['original_options'].items():
        assert o[ref]['option'] == x['option']
    for key in ['families', 'methods']:
        final = {x['id']: x for x in c[key]}
        for x in base['classification'][key]:
            assert final[x['id']] == x
    rows = {r['source_ref']: r for r in c['rows']}
    for r in base['classification']['rows']:
        assert rows[r['source_ref']] == r
    methods = {m['id']: m for m in c['methods']}
    evidence_counts = {}
    feature_bindings = 0
    legacy_issues = {}
    for paper in selection['papers']:
        alias = paper['alias']
        source = s.read(out / 'inputs' / paper['paper_id'] / 'sources.json')
        sources = source['sources']
        h = s.read(out / 'records' / alias / 'h1.json')
        space = s.read(out / 'records' / alias / 'options.json')
        assert not s.triad.h1_validate(h, {'paper_id': paper['paper_id'], 'sources': sources})
        target = space['hypothesis_text'] if paper['baseline'] else h['h1']['text']
        if paper['baseline']:
            projection = copy.deepcopy(space)
            projection.setdefault('excluded_choices', [])
            structure = [e for e in s.lab.validate_space(projection, target) if 'fewer than two options' not in e]
            assert not structure
            audit = s.lab.evidence_audit(space, sources)
            legacy_issues[alias] = [x for x in audit['checks'] if not x['matched']]
        else:
            assert not s.reported_extract.errors(space, target, sources)
        assert not [x for x in source.get('coverage', []) if x.get('included_chars', 0) < x.get('original_chars', 0)]
        t = s.read(out / 'records' / alias / 'triads.json')
        expected = {}
        for row in c['rows']:
            if o[row['source_ref']]['paper'] != alias:
                continue
            assert not s.triad.quote_errors(row, sources)
            for comp in row['components']:
                slots = list(dict.fromkeys(methods[comp['method_id']]['parameter_slots'] + [p['name'] for p in comp['parameters']]))
                expected[row['source_ref'], comp['id']] = {'required_parameter_slots': slots}
        assert not s.enrichment_errors(t, {'paper_id': paper['paper_id'], 'sources': sources}, expected, profiles[alias])
        for comp in t['components']:
            shown = data['enriched_components'][comp['source_ref'] + '/' + comp['component_id']]
            for col in shown['data_columns']:
                if col['measured_features'] is not None:
                    ds = next((d for d in profiles[alias]['datasets'] if d['dataset_id'] == col['dataset_id']))
                    assert col['measured_features'] == next((f for f in ds['columns'] if f['name'] == col['name']))
                    feature_bindings += 1
        evidence_counts[alias] = {key: s.lab.evidence_audit(obj, sources)['total'] for key, obj in [('h1', h), ('options', space), ('triads', t)]}
    assert feature_bindings == data['stats']['measured_column_bindings']
    conv = s.convergence(selection, c, o)
    assert conv == data['convergence']
    assert conv['growth'][-1]['cumulative_methods'] == len(c['methods'])
    assert conv['growth'][-1]['cumulative_families'] == len(c['families'])
    before = s.sha(out / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json')
    if replay:
        subprocess.run([sys.executable, str(s.ROOT / 'scale_trial.py'), '--output', str(out), '--count', str(count), '--replay'], check=True)
    after = s.sha(out / '\u5c55\u793a\u6570\u636e\u5feb\u7167.json')
    assert before == after
    report = {'all_checks_passed': True, 'papers': count, 'old_three_options_and_catalog_unchanged': True, 'literal_evidence_counts': evidence_counts, 'source_budget_truncations_remaining': 0, 'machine_feature_bindings_equal': feature_bindings, 'network_required': False, 'replay_exercised': replay, 'legacy_unmatched_option_quotes': legacy_issues, 'legacy_unmatched_option_quote_count': sum((len(x) for x in legacy_issues.values())), 'new_seven_option_quotes_all_literal': True, 'snapshot_sha256_before': before, 'snapshot_sha256_after': after, 'byte_identical': before == after, 'seed_papers_unchanged': selection.get('seed_count', 3), 'scientific_accuracy_certified': False}
    if count != 10:
        report.pop('new_seven_option_quotes_all_literal', None)
        report.update(new_reported_papers_count=count - 3, new_reported_paper_option_quotes_all_literal=True, added_papers_option_quotes_all_literal=True, seed_snapshot_unchanged=True)
    s.save(out / 'verification.json', report)
    print(s.lab.dumps(report), flush=True)
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--output', type=Path, default=s.ROOT.parent / 'DAG_10papers_20261023')
    p.add_argument('--skip-replay', action='store_true')
    a = p.parse_args()
    check(a.output.resolve(), not a.skip_replay)
