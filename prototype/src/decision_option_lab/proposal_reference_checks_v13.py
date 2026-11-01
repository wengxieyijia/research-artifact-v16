# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Fail closed on ambiguous author-reference scope. Never changes an effect or P."""
import copy
from collections import Counter

def checked_evaluation(evaluation, rows, author):
    result = copy.deepcopy(evaluation)
    counts = Counter((r.get('family_id') for r in author.get('references', [])))
    ambiguous = {k: v for k, v in counts.items() if v > 1}
    audit = []
    for group in result.get('groups', []):
        families = {r['family_id'] for r in rows if r['plot_group'] == group['plot_group']}
        if not families.intersection(ambiguous):
            continue
        old = {}
        for kind in ['raw_paths', 'structural_configurations']:
            stats = group[kind]
            old[kind] = {k: copy.deepcopy(stats.get(k)) for k in ['author_direction_comparison', 'author_significance_comparison']}
            for key in old[kind]:
                stats[key] = {'eligible_paths': 0, 'agreement_fraction': None, 'status': 'scope_matching_pending', 'reason': 'Multiple author references share a Family ID but concern different wave/contrast/test scopes; do not overwrite them or apply the last reference to every path.'}
        audit.append({'plot_group': group['plot_group'], 'duplicate_family_reference_counts': {k: v for k, v in ambiguous.items() if k in families}, 'superseded_legacy_comparisons': old, 'effect_sizes_p_values_and_own_direction_significance_counts_changed': False})
    return (result, {'ambiguous_groups': audit, 'policy': 'Author comparisons are NA until uniquely scoped; original references remain visible. Own effect/P/counts unchanged.'})
