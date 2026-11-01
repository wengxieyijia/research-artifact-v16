# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Small technical wrapper; sources copied before edits, scientific workflow unchanged."""
import argparse
from pathlib import Path
from proposal_trial_v10 import ProposalRun
from proposal_executor_v11 import execute_guarded
from auto_trial_v8 import read, sha

class FastProposalRun(ProposalRun):

    def __init__(self, path):
        super().__init__(path)
        self.original_execute = execute_guarded
        self.state['invocations'][-1]['executor_adapter_sha256'] = sha(Path(__file__).with_name('proposal_executor_v11.py'))
        self.persist()

    def call(self, stage, instruction, contract, material, validator, zone='blind'):
        if stage.startswith(('scientific_implementation_revision_', 'scientific_code_review_revision_')):
            instruction += '\n\u6280\u672f\u9002\u914d\u8981\u6c42：\u5728FRANCHISE_ONLY\u7b49\u6837\u672c\u9650\u5236\u540e，CO_OWNED\u7b49\u534f\u53d8\u91cf\u53ef\u80fd\u6052\u5b9a\u6216\u4e0e\u622a\u8ddd\u5197\u4f59。\u5224\u65ad\u6240\u9009\u5904\u7406\u5bf9\u6bd4\u662f\u5426\u53ef\u4f30，\u800c\u975e\u628a\u6240\u6709\u5e72\u6270\u5217\u4e0d\u6ee1\u79e9\u76f4\u63a5\u7b49\u540c\u4e8e\u5904\u7406\u6548\u5e94\u4e0d\u53ef\u8bc6\u522b。\u53ef\u7528\u7b49\u4ef7\u7684\u7ebf\u6027\u7a7a\u95f4/\u57fa\u8868\u793a\u4e0e\u6b63\u786e\u79e9、\u81ea\u7531\u5ea6\u6765\u5b9e\u73b0\u540c\u4e00\u51bb\u7ed3\u6a21\u578b；\u4e0d\u5f97\u65b0\u589e\u6b63\u5219\u9879、\u6539\u53d8\u4f30\u8ba1\u76ee\u6807\u6216\u9057\u6f0f\u975e\u5197\u4f59\u534f\u53d8\u91cf。PMM\u9884\u6d4b\u56de\u5f52\u540c\u7406，\u5197\u4f59\u7f16\u7801\u4e0d\u5e94\u5bfc\u81f4\u5168\u90e8\u63d2\u8865\u865a\u6784\u5931\u8d25。\u82e5\u5904\u7406\u53d8\u91cf\u672c\u8eab\u4e0e\u5e72\u6270\u7a7a\u95f4\u5171\u7ebf\u4ecd\u987b\u660e\u786e\u4e0d\u53ef\u8bc6\u522b。\u4fee\u590d\u5931\u8d25\u8def\u5f84\u4ec5\u636e\u51bb\u7ed3\u65b9\u6848\u548c\u9519\u8bef/\u975e\u7ed3\u5c40\u6570\u636e\u7ed3\u6784，\u4e0d\u89c2\u5bdf\u6210\u529f\u6548\u5e94\u6216\u4f5c\u8005\u7ed3\u679c\u9009\u65b9\u6cd5。'
        return super().call(stage, instruction, contract, material, validator, zone)
if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('action', choices=['run', 'amend', 'replay'])
    p.add_argument('--manifest', required=True)
    a = p.parse_args()
    if a.action == 'replay':
        from auto_report_v8 import build_report
        c = read(a.manifest)
        print(build_report(Path(c['output']), Path(c['report']), Path(c['quarantine'])))
    else:
        runner = FastProposalRun(a.manifest)
        if a.action == 'amend':
            runner.amend_preexecution_contract()
        runner.run()
