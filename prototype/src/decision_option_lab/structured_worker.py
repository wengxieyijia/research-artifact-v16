# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Execute an official compiled Boba universe with file/process/network auditing. Not an OS sandbox."""
import json
import math
import os
from pathlib import Path
import runpy
import sys
import traceback
import structured_boba_runtime as runtime

def main():
    job = Path(sys.argv[1]).resolve()
    config = json.loads((job / 'job.json').read_text('utf-8'))
    inputs = Path(config['data_dir']).resolve()
    allowed = [job, inputs, Path(sys.prefix).resolve(), Path(sys.base_prefix).resolve()]
    allowed.extend((Path(p).resolve() for p in sys.path if p and ('site-packages' in p or 'python' in p.lower()) and Path(p).is_dir()))
    runtime.configure(config, job)

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
                raise PermissionError('Write outside execution job')
            if not writing and (not under(path, allowed)):
                raise PermissionError('Read outside frozen input/runtime: ' + str(path))
    sys.addaudithook(audit)
    try:
        runpy.run_path(str(job / 'universe.py'), run_name='__main__')
        if len(runtime.RESULTS) != 1:
            raise ValueError('One frozen specification expected per job')
        result = runtime.RESULTS[0]['result']

        def safe(x):
            if isinstance(x, float) and (not math.isfinite(x)):
                return None
            if isinstance(x, dict):
                return {k: safe(v) for k, v in x.items()}
            if isinstance(x, (list, tuple)):
                return [safe(v) for v in x]
            return x
        payload = {'status': 'ok', 'result': safe(result)}
    except Exception as exc:
        payload = {'status': 'error', 'error': str(exc), 'traceback': traceback.format_exc()}
    (job / 'result.json').write_text(json.dumps(payload, ensure_ascii=False, allow_nan=False, indent=2), encoding='utf-8')
if __name__ == '__main__':
    main()
