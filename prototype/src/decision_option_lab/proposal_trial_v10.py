# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Small case adapters copied from the v7 implementation loop, around the v9 workflow.

Original engines are not edited. Resumption repairs the last rejected source instead
of starting from an empty draft. Unsupported inference is explicit NA, never another
test with the old name. All statistical code is still generated/reviewed by DeepSeek.
"""
import argparse, json, re, shutil
from pathlib import Path
from auto_trial_v9 import AutoRunV9
from auto_trial_v8 import legacy, read, save, sha, now, KEYS
IMPLEMENT = "\u4fee\u590d\u5f53\u524d\u51bb\u7ed3\u65b9\u6848\u7684\u5b8c\u6574Python\u6a21\u5757analyze(data,spec)，\u4f18\u5148\u4f9d\u636e\u4e0a\u6b21\u771f\u5b9e\u6e90\u4ee3\u7801\u548c\u5ba1\u6838\u610f\u89c1\u4fee\u5b9e\u73b0，\u4e0d\u91cd\u65b0\u8bbe\u8ba1\u79d1\u7814\u65b9\u6848。data\u4e3a\u5b8c\u6574DataFrame；spec\u4e3a\u5355\u6761expanded spec，\u542bgroup_id/choices/selected_options/steps/comparison_definition/output_contract，\u4e0d\u662ffamilies\u5217\u8868。\n\u53ea\u4f9d\u4e94\u9879\u5141\u8bb8\u8f93\u5165\u53ca\u672c\u8f6e\u6d3e\u751f\u8d44\u6599，\u4e0d\u80fd\u8bbf\u95ee\u4f5c\u8005\u6587\u4ef6/\u4ee3\u7801/\u7ed3\u679c、\u65e7\u8bd5\u9a8c\u7ed3\u679c\u6216\u73af\u5883\u53d8\u91cf。\u53ea\u5141\u8bb8numpy/pandas/scipy/statsmodels/sklearn/math/warnings/collections/itertools/functools/typing/hashlib/json。\u65e0\u6587\u4ef6/\u7f51\u7edc/\u5b50\u8fdb\u7a0b/\u53cd\u5c04。\n\u8fd4\u56deeffect_size,p_value,ci_lower,ci_upper,n,effect_scale,estimand,diagnostics,inference；effect_scale\u548cestimand\u9010\u5b57\u7b49\u4e8espec\u5bf9\u5e94\u5b57\u6bb5。n\u4e3a\u6b63\u6807\u91cf\u6216count/n_obs\u7b49\u673a\u5668\u53ef\u8bfb\u8ba1\u6570。\u6240\u6709\u6570\u636e\u5904\u7406、\u70b9\u4f30\u8ba1\u53ca\u80fd\u5b9e\u73b0\u7684\u68c0\u9a8c\u4e25\u683c\u6309\u51bb\u7ed3\u53c2\u6570。\u4e0d\u5f97\u7528Wald/Satterthwaite\u4ee3\u66ffKenward-Roger\u5e76\u5192\u79f0KR。\n\u672c\u6b21\u5141\u8bb8\u8bda\u5b9e\u7684\u90e8\u5206\u6267\u884c：\u67d0\u4e2a\u51bb\u7ed3\u68c0\u9a8c\u7f3a\u5c11\u53ef\u7528\u5b9e\u73b0\u65f6，\u82e5\u76f8\u5e94\u51bb\u7ed3\u6a21\u578b\u786e\u5df2\u6536\u655b\u4e14\u70b9\u4f30\u8ba1\u53ef\u8bc6\u522b，\u53ef\u8fd4\u56de\u8be5\u6a21\u578b\u771f\u5b9e\u70b9\u4f30\u8ba1，p_value/CI=null，inference.status='unavailable'，reason\u5177\u4f53\u8bf4\u660e\u5b9e\u73b0\u7f3a\u5931；diagnostics\u5fc5\u987b\u660e\u786e\u70b9\u4f30\u8ba1\u5df2\u8ba1\u7b97、\u51bb\u7ed3\u68c0\u9a8c\u672a\u5b9e\u73b0。\u4e0d\u80fd\u628a\u5b9e\u73b0\u7f3a\u5931\u79f0\u4e3a\u7edf\u8ba1\u4e0d\u53ef\u8bc6\u522b，\u4e0d\u80fd\u6807NS，\u4e5f\u4e0d\u80fd\u586b\u865a\u67840。\u82e5\u8fde\u6709\u6548\u70b9\u4f30\u8ba1\u90fd\u7b97\u4e0d\u51fa，\u5219\u629b\u51fa\u660e\u786e\u9519\u8bef，\u7531\u6267\u884c\u5668\u4fdd\u7559\u5931\u8d25\u56de\u6267。\u5176\u4ed6\u53ef\u5b9e\u73b0\u68c0\u9a8c\u4ecd\u987b\u5b8c\u6574\u5b9e\u65bd，\u4e0d\u5f97\u5168\u6539NA\u9003\u907f\u4fee\u590d。\n\u6709P\u65f6inference.status\u987b\u4e0e\u51bb\u7ed3policy（\u5305\u62ecOption\u8986\u76d6）\u4e00\u81f4，alternative/alpha/null_value\u9075\u5b88\u51bb\u7ed3\u503c。\u6ca1\u6709P\u5fc5\u987b\u6709\u5177\u4f53reason。\u8f6f\u4ef6\u5141\u8bb8\u7684NA\u4e0d\u7b49\u4e8e\u539f\u51bb\u7ed3\u65b9\u6cd5\u5df2\u5b8c\u5168\u5b9e\u73b0。\u4ee3\u7801\u4e0d\u5f97\u8865\u672a\u51bb\u7ed3\u79d1\u5b66\u53c2\u6570；\u4ecd\u7f3a\u5b9a\u4e49\u5c31\u660e\u786e\u963b\u65ad，\u7edd\u4e0d\u81ea\u9009。\n\u4f7f\u7528\u77e2\u91cf\u5316\u5e76\u7f13\u5b58\u6bcf\u6761spec\u5185\u91cd\u590d\u8ba1\u7b97，\u4e0d\u80fd\u589e\u52a0\u79d1\u5b66\u8fd1\u4f3c。\u4fdd\u7559\u771f\u5b9e\u7b5b\u6837、\u62df\u5408\u6536\u655b、\u5947\u5f02\u6027、\u5bf9\u6bd4\u6c34\u5e73、\u6837\u672c\u6570\u4e0e\u7f3a\u5931\u63a8\u65ad\u8bca\u65ad。\u5b8c\u6574JSON，source_code\u4e3a\u5168\u90e8\u6a21\u5757。"
REVIEW = '\u72ec\u7acb\u5bf9\u7167\u51bb\u7ed3\u65b9\u6848、\u771f\u5b9e\u6e90\u7801\u548c\u5355\u6761expanded spec\u63a5\u53e3\u5ba1\u6838\u79d1\u5b66\u5b9e\u73b0\u4e0e\u9694\u79bb。\u53ea\u4f9d\u4e94\u9879\u5141\u8bb8\u8f93\u5165\u53ca\u672c\u8f6e\u6d3e\u751f\u8d44\u6599，\u65e0\u4f5c\u8005\u7ed3\u679c。\u6838\u67e5\u5904\u7406/\u516c\u5f0f/\u6743\u91cd/\u70b9\u4f30\u8ba1、P\u4e0e\u5f53\u524d\u6807\u91cf\u6548\u5e94\u662f\u5426\u4e00\u81f4、\u6536\u655b\u548c\u7f3a\u7ec4\u5b88\u536b，\u4ee5\u53ca\u6587\u4ef6/\u7f51\u7edc\u8bbf\u95ee。\u4e0d\u80fd\u4e3a\u5f97\u5230\u7ed3\u679c\u66ff\u6362\u51bb\u7ed3\u65b9\u6cd5。\n\u8fd0\u884c\u5951\u7ea6\u5141\u8bb8“\u6709\u6548\u70b9\u4f30\u8ba1+\u63a8\u65ad\u5b9e\u73b0\u4e0d\u53ef\u7528”：\u82e5\u51bb\u7ed3\u6a21\u578b\u786e\u5df2\u5b9e\u73b0\u5e76\u6536\u655b、\u70b9\u4f30\u8ba1\u53ef\u8bc6\u522b，\u4f46\u6240\u9700KR\u7b49\u68c0\u9a8c\u5f53\u524d\u672a\u5b9e\u73b0，\u5e94\u4ee5inference.status=unavailable、p\u548cCI=null、\u5177\u4f53reason\u8bda\u5b9e\u8fd4\u56de，\u4e0d\u8ba1\u5165P\u5206\u6bcd。\u8fd9\u4e0d\u662fNS，\u4e5f\u4e0d\u662fKR\u5df2\u6267\u884c。\u8be5\u7f3a\u5931\u4f5c\u4e3a\u660e\u786e\u7684partial_execution\u9650\u5236，\u4e0d\u56e0\u4e00\u4e2a\u63a8\u65ad\u540e\u7aef\u7f3a\u5931\u963b\u65ad\u5176\u4f59\u53ef\u8ba1\u7b97\u8def\u5f84；\u4e0d\u5f97\u5c06\u4e0d\u652f\u6301\u63a8\u65ad\u6084\u6084\u6362\u6210Wald\u6216\u4f2a\u9020\u81ea\u7531\u5ea6。\u82e5\u70b9\u4f30\u8ba1\u672c\u8eab\u9519\u8bef、\u4f2a\u9020、\u53c2\u6570\u672a\u51bb\u7ed3，\u4ecd\u5fc5\u987bblocking。\n\u65e0\u6cd5\u83b7\u5f97\u70b9\u4f30\u8ba1\u7684\u8def\u5f84\u53ef\u4ee5\u663e\u5f0f\u629b\u9519\u5e76\u7531\u6267\u884c\u5668\u4fdd\u7559\u5931\u8d25\u56de\u6267，\u4e0d\u5141\u8bb8\u865a\u6784effect=0/\u6837\u672c\u6570。\u7a0b\u5e8f\u80fd\u8fd0\u884c\u4e0d\u8bc1\u660e\u63a8\u65ad\u6821\u51c6\u53ef\u9760；\u4fdd\u7559\u5168\u90e8\u6761\u4ef6\u6027\u5047\u8bbe。\u6309\u5df2\u58f0\u660e\u53cc\u4fa7alpha\u5206\u522b\u63cf\u8ff0\u7b26\u53f7\u4e0e\u663e\u8457\u6bd4\u4f8b，\u4e0d\u4e34\u65f6\u6539\u5355\u4fa7\u9608\u503c。\u4e0d\u8981\u628a\u63a5\u53e3status\u5b57\u6bb5\u4e0e\u51bb\u7ed3policy\u7684\u540d\u5b57\u533a\u522b\u5f53\u79d1\u5b66\u9519\u8bef。\u8f93\u51faready、blocking_issues、checks、nonblocking_limitations、partial_execution\u6e05\u5355。'

class ProposalRun(AutoRunV9):

    def __init__(self, path):
        super().__init__(path)
        self.state['version'] = 'auto-option-coverage-v9-proposal-adapter-v10'
        self.state['invocations'][-1]['case_adapter_source_sha256'] = sha(__file__)
        self.persist()

    def implementation(self):
        if (self.out / 'blind_code_lock.json').exists():
            return
        if (self.out / 'author_extraction_receipt.json').exists() or (self.out / 'author_reference.json').exists():
            raise RuntimeError('No scientific implementation repair after author references opened')
        capability_path = self.out / 'execution_capability_contract.json'
        if capability_path.exists():
            if read(capability_path)['frozen_plan_sha256'] != sha(self.out / 'specification_plan.json'):
                raise RuntimeError('Execution capability contract belongs to another frozen plan')
        else:
            self.assert_preexecution_revision_safe()
        plan = read(self.out / 'specification_plan.json')
        specs = read(self.out / 'specifications.json')['specifications']
        backup = self.out / 'case_adapter_v10/original_implementation'
        backup.mkdir(parents=True, exist_ok=True)
        if not (backup / 'source_manifest.json').exists():
            hashes = {}
            for p in self.out.iterdir():
                if p.is_file() and (re.fullmatch('analysis_revision_\\d+\\.py', p.name) or p.name.startswith(('scientific_code_review_revision_', 'scientific_implementation_revision_'))):
                    shutil.copy2(p, backup / p.name)
                    hashes[p.name] = sha(p)
            save(backup / 'source_manifest.json', {'utc': now(), 'original_hashes': hashes, 'no_execution_receipts_or_author_reference': True})
        if not capability_path.exists():
            save(capability_path, {'utc': now(), 'scope': 'Software execution capability, declared before any outcomes', 'frozen_plan_sha256': sha(self.out / 'specification_plan.json'), 'choices_changed': False, 'point_estimates_only_allowed_if_model_correctly_implemented_and_converged': True, 'unsupported_frozen_test': 'P/CI null and inference.status unavailable; never mislabeled as a different test or NS', 'no_effect_or_author_results_seen': True})
        previous = sorted(self.out.glob('analysis_revision_*.py'), key=lambda p: int(p.stem.rsplit('_', 1)[1]))
        start = int(previous[-1].stem.rsplit('_', 1)[1]) + 1 if previous else 0
        feedback = {}
        if previous:
            r = int(previous[-1].stem.rsplit('_', 1)[1])
            rp = self.out / f'scientific_code_review_revision_{r}.json'
            feedback = {'previous_source': previous[-1].read_text(encoding='utf-8'), 'scientific_review': read(rp) if rp.exists() else {}, 'instruction': '\u4fee\u590d\u4e0a\u6b21\u5b9e\u9645\u963b\u65ad；\u4e0d\u4ece\u7a7a\u8349\u6848\u91cd\u542f，\u4e0d\u8986\u76d6\u65e7\u6e90\u7801。'}
        if self.runtime_feedback:
            feedback['runtime_feedback'] = self.runtime_feedback
        for revision in range(start, start + 4):
            contract = {'source_code': 'Full Python module analyze(data,spec)', 'implementation_notes': [], 'dependencies': []}
            result = self.call(f'scientific_implementation_revision_{revision}', IMPLEMENT, contract, legacy.packet({'frozen_plan': plan, 'example_specs': specs[:2], 'data_conditions': self.data_conditions(), 'implementation_feedback': feedback, 'execution_capability_contract': read(self.out / 'execution_capability_contract.json')}), lambda o: legacy.code_errors(o.get('source_code', '')))
            source = result['source_code']
            (self.out / f'analysis_revision_{revision}.py').write_text(source, encoding='utf-8')
            review = self.call(f'scientific_code_review_revision_{revision}', REVIEW, {'ready': True, 'blocking_issues': [], 'checks': {}, 'nonblocking_limitations': [], 'partial_execution': []}, legacy.packet({'frozen_plan': plan, 'source_code': source, 'example_spec': specs[0], 'data_conditions': self.data_conditions(), 'execution_capability_contract': read(self.out / 'execution_capability_contract.json')}), lambda o: [] if isinstance(o.get('ready'), bool) and isinstance(o.get('blocking_issues'), list) else ['ready boolean and blocking_issues list required'])
            if review['ready'] and (not review['blocking_issues']):
                (self.out / 'analysis_round_0.py').write_text(source, encoding='utf-8')
                save(self.out / 'implementation_round_0.json', result)
                save(self.out / 'blind_code_lock.json', {'utc': now(), 'revision': revision, 'source_sha256': sha(self.out / 'analysis_round_0.py'), 'plan_sha256': sha(self.out / 'specification_plan.json'), 'review_stage': f'scientific_code_review_revision_{revision}', 'partial_execution': review.get('partial_execution', []), 'case_adapter_v10': True})
                self.log('scientific_code_frozen', revision=revision, partial_execution=review.get('partial_execution', []))
                return
            feedback = {'previous_source': source, 'scientific_review': review}
            self.log('code_revision_requested', revision=revision, blocking_issues=review['blocking_issues'])
        raise RuntimeError('Bounded case-code repair remains blocked; sources/reviews preserved, no author results opened')

def cli():
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['run', 'amend', 'replay'])
    p.add_argument('--manifest', required=True)
    a = p.parse_args()
    if a.action == 'replay':
        from auto_report_v8 import build_report
        c = read(a.manifest)
        build_report(Path(c['output']), Path(c['report']), Path(c['quarantine']))
        return
    r = ProposalRun(a.manifest)
    if a.action == 'amend':
        r.amend_preexecution_contract()
    r.run()
if __name__ == '__main__':
    cli()
