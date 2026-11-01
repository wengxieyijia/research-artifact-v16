# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Versioned JSON tasks: scientific standard, execution instructions and format are separate."""
import datetime as dt
import json
from pathlib import Path
import time
import urllib.request
import lab

def json_error_context(content, exc):
    """Explain syntax failures to the model; never repair or rewrite scientific values locally."""
    if isinstance(exc, json.JSONDecodeError):
        start = max(0, exc.pos - 180)
        end = min(len(content), exc.pos + 180)
        return 'JSON syntax error: ' + str(exc) + '; nearby raw JSON at offset ' + str(start) + ': ' + repr(content[start:end]) + '\n\u53ea\u4fee\u590dJSON\u5b57\u7b26\u4e32\u4e2d\u7684\u5f15\u53f7、\u53cd\u659c\u6760、\u63a7\u5236\u5b57\u7b26\u6216\u5206\u9694\u7b26\u7f16\u7801，\u4fdd\u6301\u539f\u6709\u79d1\u7814\u5185\u5bb9\u548c\u5f15\u6587，\u4e0d\u5220\u9664\u6216\u6539\u5199\u79d1\u5b66\u503c。'
    return 'Malformed output: ' + str(exc)

def make_body(instruction, standard, contract, material, cfg):
    body = {'model': cfg['model'], 'messages': [{'role': 'system', 'content': instruction}, {'role': 'user', 'content': lab.dumps({'normative_standard': standard, 'output_contract': contract, 'source_material': material})}], 'thinking': cfg['thinking'], 'reasoning_effort': cfg['reasoning_effort'], 'response_format': {'type': 'json_object'}, 'max_tokens': cfg['max_tokens']}
    return body

def run_json(stage, instruction, standard, contract, material, cfg, out, validator, replay=False):
    body = make_body(instruction, standard, contract, material, cfg)
    key = lab.sha(lab.dumps({'body': body, 'endpoint': cfg['base_url'], 'runner_version': 1}).encode('utf-8'))
    cache = out / 'cache' / key
    if (cache / 'accepted.json').exists():
        obj = lab.read(cache / 'accepted.json')
        errs = validator(obj)
        if not errs:
            lab.save(out / f'{stage}.json', obj)
            lab.save(out / f'{stage}_provenance.json', {'cache_key': key, 'mode': 'replay'})
            print(stage + ': replay ' + key[:12], flush=True)
            return obj
        if replay:
            raise ValueError('Cached output fails current validator; offline mode cannot repair: ' + str(errs))
        digest = lab.sha((cache / 'accepted.json').read_bytes())[:16]
        archived = cache / ('rejected_cached_' + digest + '.json')
        suffix = 1
        while archived.exists():
            archived = cache / ('rejected_cached_' + digest + '_' + str(suffix) + '.json')
            suffix += 1
        (cache / 'accepted.json').rename(archived)
        lab.save(cache / ('cache_revalidation_' + digest + '.json'), {'previous_accepted_file': archived.name, 'errors': errs, 'original_content_preserved': True, 'action': 'resume model repair; no local scientific edits'})
    if replay:
        raise RuntimeError('No matching offline cache for ' + stage)
    cache.mkdir(parents=True, exist_ok=True)
    previous_attempts = sorted(cache.glob('request_*.json'), key=lambda p: int(p.stem.split('_')[-1]))
    offset = 0
    if previous_attempts:
        offset = int(previous_attempts[-1].stem.split('_')[-1]) + 1
        last = offset - 1
        if (cache / f'response_{last}.json').exists():
            prior = lab.read(cache / f'response_{last}.json')
            prior_content = prior['choices'][0]['message'].get('content') or ''
            try:
                prior_obj = json.loads(prior_content)
                prior_errors = validator(prior_obj)
            except (ValueError, KeyError, TypeError, AttributeError) as exc:
                prior_errors = [json_error_context(prior_content, exc)]
            if prior['choices'][0].get('finish_reason') != 'stop':
                prior_errors.append('Incomplete previous output')
            if not prior_errors:
                lab.save(cache / 'accepted.json', prior_obj)
                lab.save(out / f'{stage}.json', prior_obj)
                lab.save(out / f'{stage}_provenance.json', {'cache_key': key, 'mode': 'revalidated_raw', 'accepted_attempt': last})
                return prior_obj
            if any((str(e).startswith('JSON syntax error:') for e in prior_errors)):
                body = make_body(instruction, standard, contract, material, cfg)
                body['messages'].append({'role': 'user', 'content': '\u4e0a\u4e00\u8f6eJSON\u683c\u5f0f\u65e0\u6548。\u8bf7\u4f9d\u636e\u539f\u59cb\u5951\u7ea6\u548c\u6750\u6599\u91cd\u65b0\u751f\u6210\u5b8c\u6574JSON，\u4e0d\u590d\u5236\u635f\u574f\u8f93\u51fa。components\u4e2d\u7684\u6bcf\u4e2a\u5bf9\u8c61\u53ca\u5176\u5d4c\u5957\u5bf9\u8c61\u987b\u5206\u522b\u95ed\u5408。\u79d1\u7814\u5224\u65ad\u4ecd\u53ea\u4f9d\u636e\u539f\u59cb\u6750\u6599。\u683c\u5f0f\u8bca\u65ad：\n' + lab.dumps(prior_errors)})
            else:
                body = lab.read(previous_attempts[-1])
                body['messages'] += [{'role': 'assistant', 'content': prior_content}, {'role': 'user', 'content': '\u4ec5\u4fee\u590d\u4ee5\u4e0b\u6821\u9a8c\u9519\u8bef；\u4f9d\u636e\u771f\u5b9e\u6765\u6e90\u4fee\u6b63\u5f15\u6587，\u4e0d\u80fd\u7be1\u6539\u6765\u6e90\u6216\u624b\u5de5\u8865\u9020\u79d1\u7814\u4f9d\u636e。\u8f93\u51fa\u5b8c\u6574JSON：\n' + lab.dumps(prior_errors)}]
    for attempt in range(cfg['max_structural_repairs'] + 1):
        record_index = offset + attempt
        lab.save(cache / f'request_{record_index}.json', body)
        print(stage + f': High request {attempt + 1}', flush=True)
        start = time.monotonic()
        raw = lab.request_api(body, cfg)
        lab.save(cache / f'response_{record_index}.json', raw)
        lab.save(cache / f'run_{record_index}.json', {'utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'seconds': round(time.monotonic() - start, 2), 'requested_model': cfg['model'], 'thinking': cfg['thinking'], 'reasoning_effort': cfg['reasoning_effort'], 'response_model': raw.get('model'), 'usage': raw.get('usage')})
        choice = raw['choices'][0]
        content = choice['message'].get('content') or ''
        try:
            obj = json.loads(content)
            errs = validator(obj)
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            errs = [json_error_context(content, exc)]
        if choice.get('finish_reason') != 'stop':
            errs.append('Incomplete output: ' + str(choice.get('finish_reason')))
        lab.save(cache / f'validation_{record_index}.json', {'errors': errs, 'diagnostic_version': 2})
        if not errs:
            lab.save(cache / 'accepted.json', obj)
            lab.save(out / f'{stage}.json', obj)
            lab.save(out / f'{stage}_provenance.json', {'cache_key': key, 'mode': 'api', 'accepted_attempt': record_index})
            return obj
        if attempt < cfg['max_structural_repairs']:
            if any((str(e).startswith('JSON syntax error:') for e in errs)):
                body = make_body(instruction, standard, contract, material, cfg)
                body['messages'].append({'role': 'user', 'content': 'JSON\u683c\u5f0f\u65e0\u6548。\u8bf7\u91cd\u65b0\u4f9d\u636e\u539f\u59cb\u5951\u7ea6\u548c\u6750\u6599\u8f93\u51fa\u5b8c\u6574JSON，\u52ff\u590d\u5236\u635f\u574f\u8f93\u51fa；\u6bcf\u5c42\u5bf9\u8c61\u4e0e\u6570\u7ec4\u5206\u522b\u95ed\u5408。\u8bca\u65ad：\n' + lab.dumps(errs)})
            else:
                body['messages'] += [{'role': 'assistant', 'content': content}, {'role': 'user', 'content': '\u4ec5\u4fee\u590d\u4ee5\u4e0b\u683c\u5f0f/\u8986\u76d6\u9519\u8bef，\u4ecd\u9075\u5b88\u72ec\u7acb\u89c4\u8303\u5e76\u8f93\u51fa\u5b8c\u6574JSON。\u4e0d\u8981\u4fee\u6539\u539f\u59cb\u8bba\u6587\u5b9e\u4f8b：\n' + lab.dumps(errs)}]
    raise ValueError(stage + ' structural checks failed: ' + str(errs))

def verify_provider(cfg, out, replay=False):
    path = out / 'model_metadata.json'
    if path.exists():
        return lab.read(path)
    if replay:
        raise RuntimeError('Provider metadata missing in offline results')
    req = urllib.request.Request(cfg['base_url'].rstrip('/') + '/models', headers={'Authorization': 'Bearer ' + lab.api_key()})
    with urllib.request.urlopen(req, timeout=60) as response:
        raw = json.loads(response.read())
    selected = next((x for x in raw.get('data', []) if x.get('id') == cfg['model']), None)
    if selected is None:
        raise ValueError('Configured model absent from provider model list')
    levels = selected.get('effort', {}).get('supported_levels')
    if levels is not None and cfg['reasoning_effort'] not in levels:
        raise ValueError('Provider does not list requested effort')
    lab.save(path, {'selected': selected, 'requested_profile': cfg, 'checked_utc': dt.datetime.now(dt.timezone.utc).isoformat(), 'docs': ['https://api-docs.deepseek.com/api/list-models/', 'https://api-docs.deepseek.com/guides/thinking_mode/']})
    return lab.read(path)
