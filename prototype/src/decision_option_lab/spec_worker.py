# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Constrained child process for generated statistical code. Not an OS security sandbox."""
import importlib.util
import json
import math
import os
from pathlib import Path
import sys
import traceback

def main():
    job = Path(sys.argv[1]).resolve()
    config = json.loads((job / 'job.json').read_text(encoding='utf-8'))
    inputs = Path(config['data_dir']).resolve()
    allowed = [job, inputs, Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]
    allowed.extend((Path(p).resolve() for p in sys.path if p and ('site-packages' in p or 'python' in p.lower()) and Path(p).is_dir()))

    def under(path, roots):
        try:
            p = Path(path).resolve()
        except (TypeError, ValueError):
            return isinstance(path, int)
        return any((p.is_relative_to(root) for root in roots))

    def audit(event, args):
        if event.startswith(('socket.', 'subprocess.')) or event in ('os.system', 'os.remove', 'os.rename', 'os.rmdir', 'os.mkdir', 'os.link', 'os.symlink'):
            raise PermissionError('Blocked action: ' + event)
        if event == 'open':
            path, mode, flags = args
            writing = isinstance(mode, str) and any((x in mode for x in 'wax+')) or (isinstance(flags, int) and bool(flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC)))
            if writing and (not under(path, [job])):
                raise PermissionError('Write outside job blocked')
            if not writing and (not under(path, allowed)):
                raise PermissionError('Read outside data/runtime blocked: ' + str(path))
    sys.addaudithook(audit)
    try:
        module_spec = importlib.util.spec_from_file_location('generated_analysis', job / 'analysis.py')
        module = importlib.util.module_from_spec(module_spec)
        module_spec.loader.exec_module(module)
        result = module.analyze(str(inputs), config['spec'], config['contract'])

        def json_safe(value):
            if isinstance(value, float) and (not math.isfinite(value)):
                return None
            if isinstance(value, dict):
                return {k: json_safe(v) for k, v in value.items()}
            if isinstance(value, (list, tuple)):
                return [json_safe(v) for v in value]
            return value
        result = json_safe(result)
        payload = {'status': 'ok', 'result': result}
    except Exception as exc:
        payload = {'status': 'error', 'error': str(exc), 'traceback': traceback.format_exc()}
    (job / 'result.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
if __name__ == '__main__':
    main()
