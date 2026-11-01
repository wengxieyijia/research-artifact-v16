# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Offline source/metadata check. Does not run the scientific pipeline or access the network."""
import ast, hashlib, runpy, sys, unittest
from pathlib import Path
root = Path(__file__).resolve().parent
for p in root.rglob('*.py'):
    ast.parse(p.read_text(encoding='utf-8-sig'), filename=str(p.relative_to(root)))
for case in sorted((root / 'cases').iterdir()):
    protocol = runpy.run_path(str(case / 'frozen_protocol.py'))
    specs = runpy.run_path(str(case / 'frozen_specifications.py'))['SPECIFICATIONS']
    assert len({s['spec_id'] for s in specs}) == len(specs)
    assert protocol['CASE_ID'] == case.name
    print(case.name, 'frozen paths', len(specs))
sys.path.insert(0, str(root / 'src/decision_option_lab'))
import test_author_evaluate_v16
suite = unittest.defaultTestLoader.loadTestsFromModule(test_author_evaluate_v16)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if not result.wasSuccessful():
    raise SystemExit(1)
print('PASS: syntax, frozen configuration inventory, and evaluation core checks; no empirical analyses executed')
