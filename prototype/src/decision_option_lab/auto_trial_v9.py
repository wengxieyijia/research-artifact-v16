# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""A small, pre-freeze Option coverage extension around the unchanged v8 pipeline.

All scientific Options and their parameter grids are authored/reviewed by DeepSeek.
This layer verifies coverage receipts, preserves the allowed-input boundary, and
lets the existing preflight/freeze/Boba machinery enumerate accepted combinations.
Run each paper in a separate process: the inherited v7 runtime uses module globals.
"""
import argparse, copy, math, os, time, shutil
from contextlib import contextmanager
from pathlib import Path
import auto_trial_v8 as base
from auto_trial_v8 import legacy, KEYS, read, save, sha, now, digest
VERSION = 'auto-option-coverage-v9-20261029'
INITIAL_COVERAGE = '\n\u672c\u8f6e\u5148\u5f62\u6210\u7ed3\u6784\u6e05\u695a、\u53ef\u6269\u5c55\u7684\u521d\u7a3f，\u968f\u540e\u4f1a\u5728\u4e0d\u8bfb\u4f5c\u8005\u7ed3\u679c\u7684\u72ec\u7acb\u8986\u76d6\u5ba1\u67e5\u4e2d\u68c0\u67e5\u662f\u5426\u9057\u6f0f\u6709\u4f9d\u636e\u7684Option。\u4f18\u5148\u628a\u5b9e\u9645\u5206\u6790\u81ea\u7531\u5ea6\u8868\u8fbe\u4e3a\u5c11\u91cf\u660e\u786eDecision\u53ca\u5176\u53ef\u66ff\u6362Option，\u4e0d\u80fd\u4e3a\u591a\u8def\u5f84\u6570\u589e\u52a0\u65e0\u5b9e\u8d28\u5dee\u5f02\u7684Decision。\u65e2\u6709\u5386\u53f2Method\u6838\u5fc3\u4f18\u5148\u590d\u7528，\u5fc5\u8981\u65b0\u8bbe\u8ba1\u5982\u5b9e\u6807proposed。\u4e0d\u8981\u6545\u610f\u4fdd\u7559\u4e0d\u5b8c\u6574\u53c2\u6570\u6216\u9057\u6f0f\u660e\u663e\u5408\u7406\u5206\u652f\u6765\u7b49\u5f85\u4e0b\u4e00\u6b65\u8865\u5168。\u6bcf\u4e2aOption\u5c3d\u91cf\u660e\u786e\u54ea\u4e9b\u6539\u53d8\u70b9\u4f30\u8ba1、\u54ea\u4e9b\u53ea\u6539\u53d8\u5408\u6cd5\u63a8\u65ad；\u968f\u673a\u79cd\u5b50、\u76f8\u540c\u7b97\u6cd5\u6362\u540d、\u663e\u793a\u683c\u5f0f\u4e0d\u80fd\u5145\u5f53\u5206\u6790\u81ea\u7531\u5ea6。\n\u6df7\u5408\u6709P/\u65e0P\u6216\u4e0d\u540c\u6b63\u5f0f\u68c0\u9a8c\u65f6，\u5728\u76f8\u5e94Option.parameters\u91cc\u4f7f\u7528\u673a\u5668\u53ef\u8bfbinference_policy=formal_test/conditional_formal_test/not_identifiable，test_name/alternative/alpha\u8981\u4e0e\u51bb\u7ed3\u68c0\u9a8c\u4e00\u81f4；\u4e0d\u80fd\u7531\u6267\u884c\u5668\u731c\u6d4b\u5176\u63a8\u65ad\u7c7b\u522b。\u4ee5\u540c\u4e00H1\u7684\u6548\u5e94\u65b9\u5411\u548c\u7edf\u8ba1\u654f\u611f\u6027\u4e3a\u76ee\u7684，\u4e0d\u8ffd\u6c42\u4f5c\u8005\u6570\u503c\u6216\u663e\u8457\u6027。\u8f93\u51faquestion\u548clabel\u4f7f\u7528\u82f1\u6587。\n'
EXPANSION_PROMPT = '\u4f60\u662f\u72ec\u7acb\u7684\u5206\u6790\u9009\u62e9\u8986\u76d6\u5ba1\u67e5\u8005。\u4f60\u53ea\u6536\u5230\u672c\u8f6e\u5df2\u5c01\u5b58\u7684\u4e94\u9879\u5141\u8bb8\u8f93\u5165\u53ca\u7531\u5176\u4ea7\u751f\u7684\u5f53\u524d\u521d\u7a3f/\u5b9e\u6d4b\u6570\u636e\u6761\u4ef6，\u6ca1\u6709\u76ee\u6807\u8bba\u6587/\u4f5c\u8005\u4ee3\u7801、\u4f5c\u8005\u62a5\u544a\u65b9\u5411/\u663e\u8457\u6027、\u672c\u8f6e\u8def\u5f84\u6548\u5e94/P\u6216\u65e7\u76ee\u6807\u5b9e\u9a8c\u65b9\u6848。\u4e0d\u5f97\u8c03\u7528\u9884\u8bad\u7ec3\u8bb0\u5fc6\u6062\u590d\u76ee\u6807\u4f5c\u8005\u914d\u65b9，\u4e5f\u4e0d\u5f97\u4ee5\u672a\u77e5\u4f5c\u8005\u7ed3\u679c\u4e3a\u53c2\u7167。\n\n\u4efb\u52a1\u662f\u5728\u4fdd\u7559\u5408\u7406\u521d\u7a3f\u7684\u57fa\u7840\u4e0a，\u8865\u9f50\u6709\u4f9d\u636e\u800c\u9057\u6f0f\u7684Option，\u5f97\u5230\u5145\u5206\u4e14\u975e\u5197\u4f59\u7684\u5408\u6cd5\u7ec4\u5408\u7a7a\u95f4。\u4f18\u5148\u6269\u5c55\u73b0\u6709Decision\u7684Option；\u53ef\u8865\u5145\u5408\u7406\u7684\u53c2\u6570\u53d6\u503c\u7f51\u683c、\u65f6\u95f4/\u6837\u672c/\u53d8\u91cf\u64cd\u4f5c\u5316/\u4f30\u8ba1/\u63a8\u65ad\u9009\u62e9，\u4f46\u53c2\u6570\u7f51\u683c\u5fc5\u987b\u6709\u65b9\u6cd5\u5b66\u7406\u7531\u6216\u5b9e\u9645\u5386\u53f2\u6765\u6e90，\u4e0d\u80fd\u4efb\u610f\u626b\u6570\u503c\u51d1\u70b9。\u67e5\u770b\u73b0\u6709Data\u4e0e\u5386\u53f2A/B\u4e2d\u7684\u5168\u90e8\u5408\u6cd5\u53c2\u8003，\u4e0d\u5c40\u9650\u6700\u521d\u4e94\u5217，\u4e5f\u4e0d\u80fd\u628a\u8bed\u4e49\u76f8\u4f3c\u76f4\u63a5\u5f53\u9002\u7528\u6027。\n\n\u5c3d\u91cf\u5c06\u53ef\u5bf9\u9f50\u79d1\u5b66\u542b\u4e49、\u5355\u4f4d、\u96f6\u6548\u5e94\u57fa\u51c6\u548c\u65b9\u5411\u7684\u5408\u7406\u5206\u6790\u9009\u62e9\u4fdd\u7559\u5728\u540c\u4e00\u66f2\u7ebf。\u4e0d\u8981\u6309\u6bcf\u4e2aOption\u62c6\u65b0Family，\u4e5f\u4e0d\u80fd\u4e3a\u7a20\u5bc6\u6df7\u5165\u4e0d\u540cH1\u6216\u4e0d\u517c\u5bb9\u7edf\u8ba1\u91cf。\u4e0d\u6dfb\u52a0Family，\u4fdd\u7559\u73b0\u6709Family ID\u548c\u5404Family\u7684plot_group/plot_unit/effect_kind/null_value/direction_multiplier。\u53ef\u4ee5\u66f4\u65b0\u63cf\u8ff0\u4ee5\u5b8c\u6574\u8bf4\u660e\u65b0\u589eOption\u7684\u53ef\u6bd4\u8f83\u8303\u56f4，\u4e0d\u5408\u6210\u4e00\u4e2a\u5e73\u5747\u6548\u5e94。\n\n\u5c3d\u91cf\u4fdd\u7559\u521d\u7a3f\u5df2\u6709Decision\u548cOption，\u5df2\u6709Option\u7684ID、\u53c2\u6570\u53ca\u6570\u636e\u7ed1\u5b9a\u4e0d\u6539\u5199，\u79d1\u5b66\u5b9a\u4e49\u7f3a\u5931\u7531\u4e4b\u540e\u7684\u72ec\u7acbpreflight\u6307\u51fa\u5e76\u8865\u9f50。\u53ea\u5728\u786e\u5b9e\u9057\u6f0f\u5fc5\u8981\u5206\u6790\u81ea\u7531\u5ea6、\u73b0\u6709Decision\u65e0\u6cd5\u8868\u8fbe\u65f6\u589e\u52a0Decision，\u5e76\u5728change_ledger\u91cc\u7ed9new_decision\u8bb0\u5f55，\u8bf4\u660e\u4e3a\u4f55\u4e0d\u80fd\u653e\u5165\u73b0\u6709Decision；\u4e0d\u80fd\u628a\u540c\u4e00\u8fde\u7eed\u53c2\u6570\u6bcf\u4e2a\u53d6\u503c\u505a\u6210\u4e0d\u540cDecision。\u82e5\u5c06\u56fa\u5b9a\u6b65\u9aa4\u63d0\u5347\u4e3aDecision，\u5fc5\u987b\u5728step_order/common_steps/fixed_steps\u4e2d\u673a\u68b0\u4e00\u81f4\u5730\u66ff\u6362\u4e14\u89e3\u91ca\u6765\u6e90。\n\n\u6bcf\u4e2a\u65b0\u589eOption\u5fc5\u987b\u5728change_ledger\u4e2d\u6709\u4e00\u6761accepted/new_option\u8bb0\u5f55：family_id、decision_key、option_id、basis（historical/adapted/general_methodological）、source_refs、scientific_rationale、distinctness、parameter_domain、data_equivalence（not_equivalent/unknown/equivalent）、equivalence_reason、changes_point_estimate、inference_only。\u5bf9\u60f3\u8fc7\u4f46\u62d2\u7edd\u7684\u5019\u9009\u4e5f\u4fdd\u7559rejected\u8bb0\u5f55\u548c\u5177\u4f53\u7406\u7531，\u4e0d\u4f2a\u88c5\u4e3a\u7eb3\u5165。\u5f15\u7528\u5fc5\u987b\u6765\u81ea\u7ed9\u5b9a\u5386\u53f2source catalog，\u65b0\u589e\u914d\u7f6e\u4e0eMethod\u6838\u5fc3\u6765\u6e90\u4e24\u4e2a\u8f74\u5404\u81ea\u51c6\u786e。\n\n\u4e0d\u5141\u8bb8\u4ee5\u4e0b\u5145\u6570：\u6539\u53d8\u968f\u673a\u79cd\u5b50/\u91cd\u91c7\u6837\u6b21\u6570\u800c\u65e0\u72ec\u7acb\u79d1\u5b66\u6bd4\u8f83\u76ee\u7684、\u7ed8\u56fe/\u663e\u793a\u9009\u9879、\u76f8\u540c\u6570\u5b66\u7b97\u6cd5\u6362\u540d、\u53ea\u6539\u53d8\u65e0\u5b9e\u9645\u5f71\u54cd\u7684\u9608\u503c、\u91cd\u590d\u76f8\u540c\u7b5b\u9009、\u91cd\u590d\u53c2\u6570/\u7ed1\u5b9a/\u64cd\u4f5c。\u6839\u636e\u5b9e\u6d4b\u6761\u4ef6\u5ba1\u67e5\u4e24\u4e2a\u9608\u503c\u662f\u5426\u9009\u62e9\u76f8\u540c\u6570\u636e；\u5df2\u77e5\u7b49\u4ef7\u7684\u5019\u9009\u5fc5\u987b\u62d2\u7edd。\u4e0d\u786e\u5b9a\u7b49\u4ef7\u65f6\u660e\u786eunknown\u53ca\u9700\u8981\u6838\u67e5\u7684\u8fb9\u754c，\u4e0d\u80fd\u5ba3\u79f0\u5df2\u8bc1\u4e0d\u7b49\u4ef7。\u4e0d\u8981\u5b9e\u9645\u4f30\u8ba1\u672c\u8f6e\u6548\u5e94/P，\u4e5f\u4e0d\u8981\u6839\u636e\u7ed3\u679c\u5220\u9009。\n\n\u8f93\u51faexpanded_plan\u4fdd\u6301\u539f\u5b8c\u6574\u53ef\u6267\u884cschema，\u5168\u90e8\u79d1\u5b66\u64cd\u4f5c\u548c\u5fc5\u8981\u4f9d\u8d56/\u53c2\u6570\u5199\u5168；\u5c24\u5176\u91cd\u91c7\u6837\u5355\u4f4d、\u914d\u5bf9、\u91cd\u91c7\u6837\u6846、\u6b21\u5e8f、\u91cd\u590d\u6b21\u6570、\u79cd\u5b50、\u65e0\u6548\u91cd\u590d\u5904\u7406\u4e8b\u5148\u51bb\u7ed3，\u4e0d\u628a\u79d1\u5b66\u51b3\u5b9a\u7559\u7ed9\u5b9e\u73b0。\u6240\u6709\u65b0\u589e\u9009\u62e9\u901a\u8fc7constraints\u5b8c\u6574\u8868\u8fbe\u4e0d\u5408\u6cd5\u7ec4\u5408，\u7981\u6b62\u628a\u4e0d\u80fd\u6267\u884c/\u4e0d\u9002\u7528\u7684\u65b9\u6848\u6df7\u4e3a\u6210\u529f\u8def\u5f84。\n\n\u8d44\u6e90\u4e0a\u9650\u7531evaluation_policy.max_specifications\u7ea6\u5b9a，\u6309\u5404Family\u6240\u6709\u7ef4\u5ea6Option\u6570\u91cf\u4e58\u79ef\u76f8\u52a0\u8ba1\u7b97\u539f\u59cb\u7ec4\u5408，\u4e0d\u80fd\u5148\u751f\u6210\u8d85\u5927\u7a7a\u95f4\u518d\u9759\u9ed8\u62bd\u6837\u6216\u622a\u65ad。\u5c3d\u91cf\u5b8c\u6574\u679a\u4e3e\u6709\u7406\u7531\u7684\u975e\u5197\u4f59\u7ec4\u5408；\u82e5\u53ef\u5b89\u5168\u5f62\u6210\u6570\u767e\u6761\u5219\u8986\u76d6\u5145\u5206，\u4e0d\u4ee5\u8fbe\u5230\u67d0\u4e2a\u6700\u4f4e\u6570\u5b57\u4e3a\u901a\u8fc7\u6761\u4ef6。\u82e5\u6ca1\u6709\u5b89\u5168\u65b0\u589eOption，\u53ef\u4fdd\u7559\u539f\u65b9\u6848\u5e76\u5b8c\u6574\u8bf4\u660eno_safe_expansion_reason。\u6240\u6709\u56fe\u7528question/label\u4e3a\u82f1\u6587，\u5176\u4f59\u89e3\u91ca\u53ef\u4e2d\u6587。\u8f93\u51fa\u5b8c\u6574JSON，\u4e0d\u6267\u884c\u7edf\u8ba1。\n'
PREFLIGHT_COVERAGE = '\n\u672c\u8f6e\u5df2\u8fdb\u884c\u4e00\u6b21\u72ec\u7acbOption\u8986\u76d6\u6269\u5c55，\u8bf7\u4e25\u683c\u590d\u6838\u65b0\u589e\u4e0e\u539f\u6709Option\u662f\u5426\u6709\u5b9e\u8d28\u5206\u6790\u5dee\u522b、\u5386\u53f2\u5f15\u7528\u662f\u5426\u5b9e\u9645\u652f\u6301、\u53c2\u6570\u8303\u56f4\u6709\u65e0\u65b9\u6cd5\u5b66\u7406\u7531、\u6837\u672c\u9608\u503c\u662f\u5426\u5728\u5f53\u524d\u6570\u636e\u7b49\u4ef7、\u662f\u5426\u8bef\u5c06\u968f\u673a\u79cd\u5b50/\u663e\u793a\u683c\u5f0f/\u540c\u7b97\u6cd5\u4e0d\u540c\u540d\u5f53\u81ea\u7531\u5ea6。\u4e0d\u8981\u56e0\u4e3a\u540c\u4e00\u7814\u7a76\u95ee\u9898\u7684\u5408\u7406\u65f6\u95f4\u7a97、\u6837\u672c\u6216\u4f30\u8ba1\u9009\u62e9\u4e0d\u540c\u800c\u62c6\u66f2\u7ebf。\u5df2\u77e5\u5b8c\u5168\u7b49\u4ef7\u5019\u9009\u53ef\u9010Option\u62d2\u7edd\u5e76\u8bf4\u660e；\u53c2\u6570\u4f5c\u7528\u4e0d\u786e\u5b9a\u8981\u8bda\u5b9e\u6807\u660e，\u4e0d\u5ba3\u79f0\u5df2\u83b7\u5f97\u72ec\u7acb\u8bc1\u636e。\u4e0d\u80fd\u4e3a\u4fdd\u8bc1\u70b9\u6570\u653e\u5bbd\u79d1\u7814\u5224\u65ad，\u4e5f\u4e0d\u4ee5\u7ed3\u679c\u65b9\u5411/\u663e\u8457\u6027\u4e3a\u7b5b\u9009\u6761\u4ef6。\u6b63\u5f0f/\u6761\u4ef6\u6027\u68c0\u9a8c\u987b\u6709\u660e\u786e\u53ef\u8fa9\u62a4\u524d\u63d0；\u5c0f\u6837\u672c\u6216\u5143\u5206\u6790\u5c42\u7ea7\u4f9d\u8d56\u9700\u8981\u8bf4\u6e05\u695a，\u4e0d\u628a\u80fd\u7b97\u51fa\u7684P\u5f53\u5df2\u8bc1\u6709\u6548。\n\u9010\u8def\u5f84\u63a5\u53e3\u53ea\u5141\u8bb8\u4e00\u4e2a\u660e\u786e\u7684\u6807\u91cfeffect_size。\u5bf9\u6bd4、\u53c2\u7167\u7ec4、\u65b9\u5411、\u5355\u4f4d\u548c\u96f6\u503c\u5fc5\u987b\u5728\u51bb\u7ed3\u65b9\u6848\u4e2d\u786e\u5b9a；\u5982\u6709\u591a\u4e2a\u9700\u8981\u5206\u522b\u8bc4\u4ef7\u7684\u5bf9\u6bd4，\u5e94\u901a\u8fc7\u660e\u793acontrast Option\u679a\u4e3e，\u4e0d\u80fd\u5728\u540c\u4e00\u8def\u5f84\u5217\u51fa\u4e09\u4e2a\u6548\u5e94\u5374\u8ba9\u5b9e\u73b0\u4efb\u9009\u4e00\u4e2a。\u70b9\u65c1p_value\u5fc5\u987b\u68c0\u9a8c\u5f53\u524d\u8fd9\u4e2a\u6807\u91cf\u6548\u5e94\u5bf9\u5e94\u7684\u540c\u4e00\u96f6\u5047\u8bbe；omnibus\u591a\u81ea\u7531\u5ea6\u68c0\u9a8c\u4e0d\u80fd\u5192\u5145\u4efb\u610f\u4e24\u7ec4\u5dee\u5f02/\u7cfb\u6570\u7684P，\u53ef\u53e6\u5b58diagnostics\u4f46\u4e0d\u80fd\u9519\u914d\u5230\u66f2\u7ebf。\n\u63a8\u65ad\u53c2\u6570\u987b\u51bb\u7ed3\u5b8c\u6574：HAC\u4e0d\u53ea\u5199lag，\u8fd8\u987b\u660e\u786e\u6838\u51fd\u6570、\u6709\u9650\u6837\u672c/\u81ea\u7531\u5ea6\u4fee\u6b63、\u68c0\u9a8c\u53c2\u7167\u5206\u5e03；\u5176\u4ed6\u7a33\u5065/\u805a\u7c7b/\u91cd\u91c7\u6837\u63a8\u65ad\u4ea6\u987b\u660e\u786e\u5b9e\u9645\u8ba1\u7b97\u6240\u9700\u9009\u62e9。\u82e5\u9057\u6f0f\u8fd9\u4e9b\u79d1\u5b66\u51b3\u5b9a，\u5148blocking\u5e76\u7ed9\u8865\u9f50\u8981\u6c42，\u4e0d\u8ba9\u5b9e\u73b0\u51ed\u5e93\u9ed8\u8ba4\u503c\u81ea\u884c\u9009\u62e9。\n'
EVALUATION_CONTRACT = '\n\u672c\u8f6e\u5f00\u53d1\u8005/\u7528\u6237\u9884\u5b9a\u8bc4\u4ef7\u76ee\u6807\u662f\u5206\u522b\u63cf\u8ff0\u6548\u5e94\u65b9\u5411\u5206\u5e03\u4e0e“\u9884\u5b9a\u53cc\u4fa7\u68c0\u9a8cP<alpha”\u7684\u6bd4\u4f8b，\u4ee5\u53ca\u4e8c\u8005\u4ea4\u53c9\u6bd4\u4f8b；\u5e76\u4e0d\u58f0\u79f0\u7528\u8fd9\u4e9b\u6bd4\u4f8b\u786e\u8ba4\u65b9\u5411\u6027H1。\u56e0\u6b64\u5373\u4f7fH1\u662f\u6b63\u5411/\u8d1f\u5411，\u4ecd\u4fdd\u6301evaluation_policy\u6307\u5b9a\u7684two_sided、alpha（\u672c\u8f6e\u901a\u5e380.05），\u4e0d\u80fd\u64c5\u81ea\u6539\u6210\u5355\u4fa7、\u628a\u53cc\u4fa7\u9608\u503c\u6539\u4e3a0.025、\u6216\u53e6\u52a0\u65b9\u5411\u786e\u8ba4\u95e8\u69db。\u65b9\u5411\u548c\u663e\u8457\u6027\u5206\u522b\u62a5\u544a，\u89e3\u91ca\u5176\u6761\u4ef6\u4e0e\u9650\u5236\u5373\u53ef。\u82e5\u771f\u5b9e\u68c0\u9a8c\u672c\u8eab\u65e0\u6cd5\u652f\u6301\u8be5\u6548\u5e94\u96f6\u5047\u8bbe\u5219\u963b\u65ad/NA，\u4f46H1\u6709\u65b9\u5411\u672c\u8eab\u4e0d\u662f\u6539\u9608\u503c\u7684\u7406\u7531；\u5386\u53f2\u5ba1\u6838\u82e5\u4e0e\u6b64\u660e\u786e\u8bc4\u4ef7\u5951\u7ea6\u51b2\u7a81，\u5e94\u8bf4\u660e\u51b2\u7a81\u5e76\u9075\u5b88\u9884\u5b9a\u8bc4\u4ef7\u5951\u7ea6，\u4e0d\u4e3a\u5176\u6539\u53c2\u6570。'

def inventory(plan):
    families = []
    for f in plan.get('families', []):
        dims = f.get('dimensions', [])
        families.append({'family_id': f['id'], 'plot_group': f.get('comparison_definition', {}).get('evaluation', {}).get('plot_group'), 'decisions': len(dims), 'options': sum((len(d.get('options', [])) for d in dims)), 'raw_combinations': math.prod((len(d.get('options', [])) for d in dims)), 'dimension_counts': {d['key']: len(d.get('options', [])) for d in dims}})
    return {'families': families, 'raw_combinations': sum((f['raw_combinations'] for f in families))}

def new_items(before, after):
    existing = {f['id']: {d['key']: {o['id'] for o in d['options']} for d in f['dimensions']} for f in before['families']}
    added = []
    for f in after.get('families', []):
        old = existing.get(f['id'], {})
        for d in f.get('dimensions', []):
            if d['key'] not in old:
                added.append(('new_decision', f['id'], d['key'], None))
            for o in d.get('options', []):
                if o['id'] not in old.get(d['key'], set()):
                    added.append(('new_option', f['id'], d['key'], o['id']))
    return set(added)

def explicitly_no_effect(scope):
    metric = scope.get('metric_family')
    return isinstance(metric, str) and metric.strip().casefold().replace('-', '_').replace(' ', '_') in {'none', 'no_statistical_effect', 'not_applicable', 'no_statistical_effect_magnitude'}

def validate_definition_additions(before, after):
    """Allow added parameter definitions, preserving every existing scientific value.

    Narration can be reconciled with the already approved Option lists; it never
    overrides comparison definitions, data bindings, choices or existing parameters.
    """
    errors = []
    added = []

    def walk(old, new, path=(), extensible=False):
        if path == ('generation_notes',) or path == ('limitations',) or path in [('target_interpretation', 'measurement_assumptions'), ('target_interpretation', 'limits')]:
            return
        label = '/'.join(map(str, path)) or 'root'
        if isinstance(old, dict):
            if not isinstance(new, dict):
                errors.append(label + ' must remain an object')
                return
            allow = extensible or (path and path[-1] == 'parameters') or (len(path) >= 2 and path[-2:] == ('output_contract', 'inference'))
            for key in old:
                if key not in new:
                    errors.append(label + ' removed existing field ' + key)
                else:
                    walk(old[key], new[key], path + (key,), allow)
            for key in set(new) - set(old):
                if allow:
                    added.append(label + '/' + key)
                else:
                    errors.append(label + ' may not add a new scientific field ' + key)
        elif isinstance(old, list):
            if not isinstance(new, list) or len(new) != len(old):
                errors.append(label + ' must preserve existing list length/order')
                return
            for i, (a, b) in enumerate(zip(old, new)):
                walk(a, b, path + (i,), extensible)
        elif old != new:
            errors.append(label + ' changed an existing frozen value')
    walk(before, after)
    if not added:
        errors.append('Revision must actually add missing parameter/inference definitions, not only change commentary')
    return (errors, added)

@contextmanager
def shared_execution_lock(path, waiting=None):
    """Serialize trusted Boba launchers, leaving model/retrieval stages concurrent."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('a+b') as handle:
        if path.stat().st_size == 0:
            handle.write(b'0')
            handle.flush()
        notified = False
        while True:
            try:
                handle.seek(0)
                if os.name == 'nt':
                    import msvcrt
                    msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except (OSError, BlockingIOError):
                if not notified and waiting:
                    waiting()
                notified = True
                time.sleep(2)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == 'nt':
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)

class AutoRunV9(base.AutoRun):

    def __init__(self, manifest_path):
        if getattr(legacy.task, '__self__', None) is not None:
            raise RuntimeError('Use one CLI subprocess per paper; inherited runtime globals cannot be rebound safely in one process')
        super().__init__(manifest_path)
        self.state['version'] = VERSION
        self.state['invocations'][-1]['extension_source_sha256'] = sha(__file__)
        self.state['density_policy'] = 'One pre-freeze coverage review; expand justified Options, not decorative Decisions or replicated results'
        if self.cfg['data'].get('column_metadata'):
            source = Path(self.cfg['data']['column_metadata']).resolve()
            fingerprint = {'path': str(source), 'sha256': sha(source)}
            if self.state.get('data_column_metadata_fingerprint', fingerprint) != fingerprint:
                raise RuntimeError('Independent Data metadata changed; a new run_id is required')
            self.state['data_column_metadata_fingerprint'] = fingerprint
        self.persist()

    def bind(self):
        super().bind()
        legacy.STANDARD = {**legacy.STANDARD, 'version': VERSION, 'coverage_policy': 'Expand justified Options before freeze; no outcome-guided expansion, no minimum path target'}
        legacy.CFG = {**legacy.CFG, 'max_structural_repairs': 3}

    def policy(self):
        result = super().policy()
        result['max_specifications'] = int(self.cfg.get('max_specifications', 768))
        if not 1 <= result['max_specifications'] <= 1024:
            raise ValueError('Coverage resource limit must be between 1 and 1024')
        result.update(coverage_review='One independent pre-freeze Option coverage pass', minimum_path_count=None, reject_known_equivalent_options=True, new_decisions='Only a missing genuine degree of freedom with explicit justification')
        return result

    def prepare(self):
        original = base.pd.Series.quantile

        def measured_quantile(series, *args, **kwargs):
            measured = series.astype(float) if base.pd.api.types.is_bool_dtype(series.dtype) else series
            return original(measured, *args, **kwargs)
        base.pd.Series.quantile = measured_quantile
        try:
            result = super().prepare()
        finally:
            base.pd.Series.quantile = original
        self.attach_column_metadata()
        return result

    def attach_column_metadata(self):
        source = self.cfg['data'].get('column_metadata')
        if not source:
            return
        source = Path(source).resolve()
        data = read(source)
        profile = read(self.out / 'data_structure_profile.json')
        allowed_top = {'source_url', 'archive_sha256', 'source_codebook_member', 'field_metadata', 'missing_code', 'release_policy'}
        allowed_fields = {'name', 'source_start', 'source_end', 'source_format', 'source_label', 'source_line', 'unit', 'value_labels', 'value_codes', 'codes', 'missing_codes'}
        if set(data) - allowed_top:
            raise ValueError('Independent Data metadata has non-whitelisted top fields: ' + str(sorted(set(data) - allowed_top)))
        if not isinstance(data.get('field_metadata'), list):
            raise ValueError('Independent Data field_metadata must be a list')
        names = {c['name'] for c in profile['columns']}
        released = []
        unmatched = []
        for field in data['field_metadata']:
            if not isinstance(field, dict) or set(field) - allowed_fields:
                raise ValueError('Independent Data metadata contains non-whitelisted field record')
            if field.get('name') in names:
                released.append(field)
            else:
                unmatched.append(field.get('name'))
        profile['independent_column_metadata'] = {k: v for k, v in data.items() if k != 'field_metadata'} | {'field_metadata': released}
        profile['independent_column_metadata_sha256'] = sha(source)
        save(self.out / 'data_structure_profile.json', profile)
        release = self.out / 'data_column_metadata_release.json'
        if not release.exists():
            save(release, {'utc': now(), 'source_path': str(source), 'source_sha256': sha(source), 'released_field_records': len(released), 'unmatched_metadata_names': unmatched, 'allowed': 'Original data-variable labels, record positions, value codes, units and missing-value definitions only', 'author_analysis_code_or_results_released': False, 'raw_data_columns_selected_or_dropped': False})

    def target_metadata(self):
        super().target_metadata()
        self.require_declared_effect()

    def require_declared_effect(self):
        scope_path = self.out / 'effect_scope_public.json'
        if scope_path.exists() and explicitly_no_effect(read(scope_path)):
            save(self.out / 'suitability_block.json', {'utc': now(), 'status': 'not_suitable_for_effect_curve_test', 'source': 'Isolated extractor explicitly declared no statistical effect, not a developer scientific reinterpretation', 'declared_metric_family': read(scope_path)['metric_family'], 'numeric_null_placeholder_is_not_an_effect': True, 'generation_execution_stopped': True, 'author_observed_results_opened': False})
            raise RuntimeError('Isolated extractor explicitly declares no statistical effect; do not invent a testable H1 from a data-engineering/teaching aim')

    def call(self, stage, instruction, contract, material, validator, zone='blind'):
        if zone == 'blind':
            instruction += EVALUATION_CONTRACT
        if stage == 'clean_data_dictionary' and material.get('raw_data_measurements', {}).get('independent_column_metadata'):
            instruction += '\n\u8865\u5145/\u66f4\u6b63：\u672c\u8f6eraw_data_measurements\u53e6\u542bindependent_column_metadata，\u8fd9\u662f\u5408\u6cd5\u7684\u72ec\u7acbData\u4ee3\u7801\u672c\u5b57\u6bb5\u6807\u7b7e/\u53d6\u503c\u7801/\u5355\u4f4d/\u7f3a\u5931\u7801，\u5df2\u7ecf\u8fc7\u767d\u540d\u5355\u91ca\u653e；\u4e0d\u542b\u76ee\u6807\u8bba\u6587\u65b9\u6848、\u4f5c\u8005\u7edf\u8ba1\u4ee3\u7801\u6216\u7ed3\u679c，\u53ef\u4ee5\u636e\u6b64\u89e3\u91ca\u5217\u503c。\u5df2\u6709log/trimmed\u5217、\u8c03\u67e5\u6743\u91cd\u5217、\u63d2\u8865\u6807\u8bb0\u7684\u5b9a\u4e49\u5c5e\u4e8eData\u4e8b\u5b9e，\u4e0d\u80fd\u7531\u6b64\u63a8\u8350\u5fc5\u987b\u9009\u67d0\u6743\u91cd、\u63a7\u5236\u9879\u6216\u4f5c\u8005\u5206\u6790\u914d\u65b9。\u4fdd\u6301\u65e2\u6709certainty\u4fdd\u5b88\u4e24\u6863，uncertainty\u4e2d\u660e\u786e\u54ea\u4e9b\u542b\u4e49\u6709\u72ec\u7acbData\u6807\u7b7e\u652f\u6301、\u54ea\u4e9b\u4ecd\u4ec5\u63a8\u6d4b，\u4e0d\u5047\u79f0\u62e5\u6709\u5b8c\u6574\u4f5c\u8005\u5206\u6790\u4ee3\u7801\u672c。\u65e0\u8be5\u5b57\u6bb5\u652f\u6301\u7684\u90e8\u5206\u4ecd\u672a\u77e5。'
        if stage == 'generate_broad_historical_multiverse':
            instruction += INITIAL_COVERAGE
        elif stage.startswith('independent_preflight_choice_audit_'):
            instruction += PREFLIGHT_COVERAGE
            original_validator = validator

            def typed_preflight_validator(value):
                errors = []
                for family in value.get('family_reviews', []):
                    constraints = family.get('additional_constraints', [])
                    if not isinstance(constraints, list):
                        errors.append(str(family.get('family_id')) + ' additional_constraints must be an array')
                    else:
                        for index, constraint in enumerate(constraints):
                            if not isinstance(constraint, dict) or not isinstance(constraint.get('forbid_when'), dict):
                                errors.append(str(family.get('family_id')) + ' additional_constraints[' + str(index) + '] must be an object {id,forbid_when:{DecisionKey:[OptionIDs]},reason}. Use [] when no forbidden combinations; narrative limitations belong in warnings/limitations, never strings in constraints.')
                return errors or original_validator(value)
            validator = typed_preflight_validator
        elif stage == 'author_direction_and_significance_after_freeze':
            instruction += '\n\u65b9\u5411\u53c2\u7167\u5fc5\u987b\u4e0e\u6bcf\u4e2a\u51bb\u7ed3Family\u7684comparison_definition.evaluation.null_value\u53cadirection_multiplier\u4f7f\u7528\u540c\u4e00\u7f16\u7801。\u65b0\u589eraw_source_direction=positive/negative/zero/mixed/unknown\u4fdd\u5b58\u539f\u6587\u76f4\u63a5\u89c2\u5bdf\u7684\u539f\u59cb\u65b9\u5411；author_reported_direction\u4fdd\u5b58\u6620\u5c04\u5230\u5f53\u524d\u79d1\u5b66\u5bf9\u6bd4、\u518d\u6309\u51bb\u7ed3direction_multiplier\u7f16\u7801\u540e\u7684\u65b9\u5411，\u4e0d\u80fd\u7b80\u5355\u7167\u6284\u539f\u6587\u7cfb\u6570\u7b26\u53f7\u800c\u5ffd\u7565\u7f16\u7801。direction_basis\u9010\u6b65\u89e3\u91ca\u539f\u6587\u539f\u59cb\u65b9\u5411→\u5f53\u524d\u5bf9\u6bd4（\u662f\u5426\u4ea4\u6362\u66b4\u9732/\u7ed3\u5c40/\u53c2\u7167）→\u51bb\u7ed3\u7f16\u7801；\u6ca1\u6709\u6709\u636e\u53ef\u67e5\u7684\u6620\u5c04\u5c31unknown，\u4e0d\u80fd\u786c\u731c。H1\u7684\u9884\u671f\u65b9\u5411\u4e0d\u662f\u89c2\u5bdf\u7ed3\u679c；H1\u65e0\u65b9\u5411\u6216\u4e34\u5e8a/\u91cf\u8868\u65b9\u5411\u672a\u77e5\u65f6\u5c24\u5176\u4e0d\u80fd\u628a\u9884\u671f\u4f5c\u4e3a\u4f5c\u8005\u89c2\u5bdf\u65b9\u5411。\u4f5c\u8005\u663e\u8457\u6027\u4ecd\u53ea\u4f9d\u636e\u5b9e\u9645\u62a5\u544a，\u4e0d\u6539\u672c\u8f6eeffect\u6216P。'
            contract = copy.deepcopy(contract)
            for ref in contract.get('references', []):
                ref['raw_source_direction'] = 'positive/negative/zero/mixed/unknown'
            original_validator = validator

            def aligned_reference_validator(value):
                errors = original_validator(value)
                for ref in value.get('references', []):
                    if ref.get('raw_source_direction') not in ['positive', 'negative', 'zero', 'mixed', 'unknown']:
                        errors.append('Every author reference must expose a valid raw_source_direction for coding audit')
                    if not ref.get('direction_basis'):
                        errors.append('Explain raw source direction to frozen contrast/coding mapping; unknown if unverifiable')
                return errors
            validator = aligned_reference_validator
        if stage.startswith(('scientific_implementation_revision_', 'scientific_code_review_revision_')):
            instruction += '\n\u53ef\u4fe1\u8f6f\u4ef6\u63a5\u53e3\u4e8b\u5b9e：worker\u5b9e\u9645\u8c03\u7528 module.analyze(frame.copy(), \u5355\u6761expanded_spec)，data\u662f\u5b8c\u6574CSV\u7684pandas.DataFrame，\u7b2c\u4e8c\u53c2\u6570spec\u5305\u542bgroup_id/choices/selected_options/steps/comparison_definition/output_contract，\u7edd\u4e0d\u662f\u6574\u4e2afrozen_plan，\u4e5f\u4e0d\u8981\u6c42spec\u542bfamilies。\u8bf7\u5bf9\u7167final_execution_scope.example_expanded_spec\u8fd9\u4e00\u771f\u5b9e\u5355\u8def\u5f84\u7ed3\u6784，\u4e0d\u5f97\u56e0\u4e3a\u8bef\u8bfb\u4e3a\u6574\u4e2aplan\u800c\u6539\u79d1\u5b66\u5206\u6790。\u6267\u884c\u8303\u56f4\u4ee5\u6700\u7ec8frozen_plan\u7684dimensions、steps、\u6700\u7ec8specs\u6240\u9009\u9879\u53capreflight\u62d2\u7edd\u6e05\u5355\u4e3a\u51c6；generation_notes/\u65e7\u7ec4\u5408\u6570\u53ea\u53ef\u4e3a\u5386\u53f2\u8bf4\u660e，\u4e0d\u80fd\u8981\u6c42\u5b9e\u73b0\u5df2\u88ab\u62d2\u7edd/\u672a\u8fdb\u5165\u6700\u7ec8\u7ef4\u5ea6\u7684Option。\u6bcf\u6b21\u53ea\u8fd4\u56de\u5355\u4e00\u660e\u786e\u6807\u91cfeffect_size，\u5176p_value\u5fc5\u987b\u5bf9\u5e94\u540c\u4e00\u5bf9\u6bd4\u548c\u96f6\u5047\u8bbe，omnibus\u4e0d\u5f97\u9876\u66ff\u5355\u5bf9\u6bd4P。HAC\u6838、\u6709\u9650\u6837\u672c\u4fee\u6b63、\u68c0\u9a8c\u53c2\u7167\u5206\u5e03\u7b49\u79d1\u5b66\u53c2\u6570\u82e5\u4ecd\u672a\u51bb\u7ed3，\u5e94\u660e\u786e\u963b\u65ad，\u4e0d\u80fd\u7531\u5b9e\u73b0\u81ea\u9009。\u8fd4\u56deinference.status\u662f\u8f6f\u4ef6\u63a5\u53e3\u5143\u5b57\u6bb5，\u6620\u5c04\u51bb\u7ed3inference.policy（\u5305\u62ec\u5df2\u58f0\u660e\u7684Option\u8986\u76d6），\u65e0\u9700\u51bb\u7ed3\u8ba1\u5212\u4e2d\u53e6\u6709\u540c\u540dstatus\u5b57\u6bb5；\u4e0d\u8981\u5c06policy/status\u547d\u540d\u5dee\u522b\u8bef\u5224\u4e3a\u79d1\u5b66\u5b9a\u4e49\u7f3a\u5931。'
            if (self.out / 'specifications.json').exists() and (self.out / 'preflight_audit.json').exists():
                specs = read(self.out / 'specifications.json')['specifications']
                preflight = read(self.out / 'preflight_audit.json')
                material = copy.deepcopy(material)
                material[KEYS[4]]['derived_current_trial']['final_execution_scope'] = {'frozen_spec_count': len(specs), 'example_expanded_spec': specs[0] if specs else None, 'selected_options_by_family': {f['id']: {d['key']: [o['id'] for o in d['options']] for d in f['dimensions']} for f in read(self.out / 'specification_plan.json')['families']}, 'preflight_rejected_options': [{'family_id': f['family_id'], 'decision_key': o['decision_key'], 'option_id': o['option_id'], 'reason': o.get('reason')} for f in preflight['family_reviews'] for o in f['option_reviews'] if not o['accept']]}
        if zone == 'blind' and (stage in ['generate_broad_historical_multiverse', 'independent_option_coverage_expansion'] or stage.startswith(('plan_definition_repair_', 'independent_option_coverage_delta'))):
            catalog = read(self.out / 'historical_source_catalog.json')
            material = copy.deepcopy(material)
            material[KEYS[4]]['derived_current_trial']['allowed_source_refs'] = {ref: record.get('kind') for ref, record in catalog.items()}
            instruction += '\nsource_refs\u53ea\u80fd\u9010\u5b57\u590d\u5236allowed_source_refs\u7ed9\u51fa\u7684\u5b9e\u9645\u952e；M\u7f16\u53f7/\u8bba\u6587\u540d/\u8bf4\u660e\u6587\u5b57\u4e0d\u662f\u81ea\u52a8\u6709\u6548\u7684source_refs。\u4e0d\u80fd\u4e3a\u901a\u8fc7\u6821\u9a8c\u8865\u9020\u5f15\u7528；\u771f\u5b9e\u65e0\u5386\u53f2\u652f\u6301\u7684\u5b8c\u6574\u914d\u7f6e\u8bf7\u5982\u5b9eproposed。\u79d1\u7814\u65b9\u6cd5\u6838\u5fc3\u7684method_refs\u548csource_refs\u5206\u522b\u586b\u5199，\u4e0d\u8981\u6df7\u7528。'
        return super().call(stage, instruction, contract, material, validator, zone)

    def validate_plan(self, plan):
        shape_errors = []
        for family in plan.get('families', []):
            for index, constraint in enumerate(family.get('constraints', [])):
                if not isinstance(constraint, dict) or not isinstance(constraint.get('forbid_when'), dict):
                    shape_errors.append(str(family.get('id')) + ' constraints[' + str(index) + '] must be an object {id,forbid_when:{DecisionKey:[OptionIDs]},reason}; put narrative limits in limitations, not constraints.')
        if shape_errors:
            return shape_errors
        errors = super().validate_plan(plan)
        catalog_path = self.out / 'historical_source_catalog.json'
        if not catalog_path.exists():
            return errors
        catalog = read(catalog_path)
        examples = {}
        for ref, record in catalog.items():
            bucket = examples.setdefault(record.get('kind', 'unknown'), [])
            if len(bucket) < 3:
                bucket.append(ref)
        hint = ' Actual allowed source key examples by kind: ' + base.canonical(examples)
        for family in plan.get('families', []):
            prefix = str(family.get('id', '?'))
            items = []
            items.extend(((prefix + '/common:' + str(i) + '/' + str(x.get('key', '?')), x) for i, x in enumerate(family.get('common_steps', []))))
            items.extend(((prefix + '/fixed:' + str(x.get('key', '?')), x) for x in family.get('fixed_steps', [])))
            for dimension in family.get('dimensions', []):
                dp = prefix + '/Decision:' + str(dimension.get('key', '?'))
                items.append((dp, dimension))
                items.extend(((dp + '/Option:' + str(x.get('id', '?')), x) for x in dimension.get('options', [])))
            for location, item in items:
                refs = item.get('source_refs', [])
                if item.get('origin') in ['reused', 'adapted'] and (not refs):
                    errors.append(location + ' has origin=' + str(item['origin']) + ' but source_refs is empty. Cite real supporting evidence or truthfully classify the unsupported new configuration as proposed.' + hint)
                if isinstance(refs, list):
                    bad = [r for r in refs if r not in catalog]
                    if bad:
                        errors.append(location + ' source_refs contains unavailable keys ' + repr(bad) + '. No invented/approximate refs.' + hint)
        return sorted(set(errors))

    def step(self, name, fn, outputs=()):
        if name == '05_plan_review_and_freeze':
            outputs = tuple(outputs) + (self.out / 'option_coverage_review.json', self.out / 'option_coverage_receipt.json')
        if name == '03_clean_data_semantics':
            self.require_declared_effect()
        return super().step(name, fn, outputs)

    def validate_expansion(self, result, before):
        after = result.get('expanded_plan', {})
        errors = self.validate_plan(after)
        review = result.get('expansion_review', {})
        ledger = review.get('change_ledger', [])
        old_families = {f['id']: f for f in before['families']}
        new_families = {f['id']: f for f in after.get('families', [])}
        if set(old_families) != set(new_families):
            errors.append('Coverage expansion must preserve existing Family IDs; no new research-question families')
        if after.get('target_interpretation', {}).get('h1') != before.get('target_interpretation', {}).get('h1'):
            errors.append('Coverage expansion cannot change the selected H1')
        for fid, old in old_families.items():
            if fid not in new_families:
                continue
            new = new_families[fid]
            old_ev = old['comparison_definition']['evaluation']
            new_ev = new.get('comparison_definition', {}).get('evaluation', {})
            if any((new_ev.get(k) != old_ev.get(k) for k in ['plot_group', 'plot_unit', 'effect_kind', 'null_value', 'direction_multiplier'])):
                errors.append(fid + ' preserve the broad comparison axis/null/direction contract')
            new_dims = {d['key']: d for d in new.get('dimensions', [])}
            for d in new.get('dimensions', []):
                fingerprints = [digest({k: o.get(k) for k in ['description', 'parameters', 'data_binding', 'method_refs']}) for o in d.get('options', [])]
                if len(set(fingerprints)) != len(fingerprints):
                    errors.append(fid + ' ' + d['key'] + ' has byte-identical scientific operations under different Option IDs/labels')
            for d in old['dimensions']:
                if d['key'] not in new_dims:
                    errors.append(fid + ' cannot remove an existing Decision during expansion')
                    continue
                new_options = {o['id']: o for o in new_dims[d['key']]['options']}
                for option in d['options']:
                    if option['id'] not in new_options:
                        errors.append(fid + ' cannot silently remove an existing Option during expansion')
                    elif digest(option) != digest(new_options[option['id']]):
                        errors.append(fid + ' preserve existing Option records exactly; leave repairs to scientific preflight')
        if not isinstance(ledger, list):
            return sorted(set(errors + ['expansion_review.change_ledger must be a list']))
        accepted = []
        catalog = read(self.out / 'historical_source_catalog.json')
        for entry in ledger:
            if entry.get('status') not in ['accepted', 'rejected'] or entry.get('kind') not in ['new_option', 'new_decision']:
                errors.append('Each ledger item needs valid status/kind')
            if not entry.get('scientific_rationale'):
                errors.append('Every accepted/rejected coverage candidate needs a concrete scientific rationale')
            if entry.get('status') != 'accepted':
                continue
            accepted.append((entry.get('kind'), entry.get('family_id'), entry.get('decision_key'), entry.get('option_id')))
            if entry.get('basis') not in ['historical', 'adapted', 'general_methodological']:
                errors.append('Added item must declare historical/adapted/general_methodological basis')
            if not isinstance(entry.get('source_refs'), list) or any((r not in catalog for r in entry.get('source_refs', []))):
                errors.append('Coverage ledger source refs must resolve to supplied historical catalog')
            if entry.get('basis') in ['historical', 'adapted'] and (not entry.get('source_refs')):
                errors.append('Historical/adapted coverage claim needs actual source refs')
            if entry.get('kind') == 'new_decision':
                if entry.get('option_id') is not None or not entry.get('why_not_existing_decision'):
                    errors.append('New Decision needs null option_id and explanation why existing Decisions cannot express it')
            else:
                if not entry.get('distinctness') or not entry.get('parameter_domain') or (not entry.get('equivalence_reason')):
                    errors.append('New Option needs distinctness, justified parameter domain and equivalence reasoning')
                if entry.get('data_equivalence') not in ['not_equivalent', 'unknown']:
                    errors.append('Known equivalent or undeclared-equivalence candidates cannot be accepted')
                if not isinstance(entry.get('changes_point_estimate'), bool) or not isinstance(entry.get('inference_only'), bool):
                    errors.append('Declare whether an added Option changes effects or only inference')
        actual = new_items(before, after)
        if set(accepted) != actual or len(accepted) != len(actual):
            errors.append('Every new Decision/Option must have exactly one accepted coverage ledger entry, with no phantom accepted entries')
        if not actual and (not review.get('no_safe_expansion_reason')):
            errors.append('An unchanged plan needs a concrete no-safe-expansion reason')
        if not isinstance(review.get('limitations'), list):
            errors.append('Explicit coverage limitations required')
        return sorted(set(errors))

    def expand_options(self):
        receipt = self.out / 'option_coverage_receipt.json'
        if receipt.exists():
            saved = read(receipt)
            for name, key in [('option_coverage_review.json', 'review_sha256'), ('option_coverage_before.json', 'before_sha256')]:
                if sha(self.out / name) != saved[key]:
                    raise RuntimeError('Coverage receipt no longer matches saved review/baseline')
            return
        if (self.out / 'specification_lock.json').exists() or (self.out / 'blind_results_lock.json').exists() or (self.out / 'author_extraction_receipt.json').exists():
            raise RuntimeError('Coverage expansion is only allowed before scientific/author-result freeze in a fresh run')
        before_path = self.out / 'option_coverage_before.json'
        before = read(before_path) if before_path.exists() else copy.deepcopy(self.original_plan())
        if not before_path.exists():
            save(before_path, before)
        template = read(self.out / 'plan_output_contract.json')
        entry = {'kind': 'new_option/new_decision', 'family_id': 'F1', 'decision_key': 'actual key', 'option_id': 'actual id or null for new_decision', 'status': 'accepted/rejected', 'basis': 'historical/adapted/general_methodological', 'source_refs': [], 'scientific_rationale': 'concrete reason', 'distinctness': 'not merely another name/seed', 'parameter_domain': 'why these particular values are scientifically reasonable', 'data_equivalence': 'not_equivalent/unknown/equivalent', 'equivalence_reason': 'what measured evidence supports this, or honest remaining uncertainty', 'changes_point_estimate': True, 'inference_only': False, 'why_not_existing_decision': None}
        contract = {'expanded_plan': template, 'expansion_review': {'change_ledger': [entry], 'rejected_or_deferred_reasoning': [], 'no_safe_expansion_reason': None, 'coverage_assessment': 'scientific space covered, no number target', 'limitations': []}}
        review_path = self.out / 'option_coverage_review.json'
        if review_path.exists():
            result = read(review_path)
            errors = self.validate_expansion(result, before)
            if errors:
                raise RuntimeError('Saved coverage review no longer passes structural verification: ' + str(errors))
        elif self.cfg.get('coverage_format', 'delta') == 'delta':
            from option_coverage_delta_v9 import expand_with_delta
            result = expand_with_delta(self, before, contract)
            errors = self.validate_expansion(result, before)
            if errors:
                raise RuntimeError('Delta coverage did not pass the unchanged expansion guard: ' + str(errors))
        else:
            result = self.call('independent_option_coverage_expansion', base.PLAN_PROMPT + '\n' + EXPANSION_PROMPT, contract, legacy.packet({'current_candidate_plan': before, 'evaluation_policy': self.policy(), 'measured_data_conditions': self.data_conditions()}), lambda o: self.validate_expansion(o, before))
        save(self.out / 'option_coverage_review.json', result)
        save(self.out / 'candidate_plan_raw.json', result['expanded_plan'])
        save(receipt, {'utc': now(), 'mode': 'Pre-freeze coverage review; no path effects/P or author references supplied', 'before': inventory(before), 'after_expansion_before_preflight': inventory(result['expanded_plan']), 'accepted_change_entries': sum((e['status'] == 'accepted' for e in result['expansion_review']['change_ledger'])), 'rejected_change_entries': sum((e['status'] == 'rejected' for e in result['expansion_review']['change_ledger'])), 'before_sha256': sha(self.out / 'option_coverage_before.json'), 'review_sha256': sha(self.out / 'option_coverage_review.json'), 'target_author_results_used': False, 'path_result_adaptive_selection': False, 'minimum_path_count': None})
        self.log('option_coverage_expanded', before=inventory(before)['raw_combinations'], after=inventory(result['expanded_plan'])['raw_combinations'])

    def draft_and_freeze(self):
        if not (self.out / 'specification_lock.json').exists():
            self.expand_options()
        super().draft_and_freeze()
        if not (self.out / 'option_coverage_review.json').exists():
            raise RuntimeError('A v9 frozen plan requires a saved pre-freeze coverage audit')
        summary = read(self.out / 'option_coverage_receipt.json')
        summary['final_approved'] = inventory(read(self.out / 'specification_plan.json'))
        summary['accepted_specs'] = read(self.out / 'specifications.json')['count']
        summary['rejected_combinations'] = sum((not c['accepted'] for c in read(self.out / 'combination_manifest.json')))
        save(self.out / 'option_coverage_receipt.json', summary)

    def execute(self):
        lock = base.ROOT / 'work/auto_v9_boba_execution.lock'
        with shared_execution_lock(lock, lambda: self.log('waiting_for_shared_boba_execution_slot', parallel_boba_limit=1)):
            self.log('shared_boba_execution_slot_acquired', parallel_boba_limit=1)
            return super().execute()

    def assert_preexecution_revision_safe(self):
        forbidden = [p for pattern in ['execution_results*.json', 'blind_results_lock.json', 'author_extraction_receipt.json', 'author_reference.json'] for p in self.out.glob(pattern)]
        forbidden += [p for p in self.out.rglob('S*.json') if p.parent.name == 'results']
        if forbidden:
            raise RuntimeError('No scientific definition revision after any execution receipt or author reference: ' + str(forbidden[:5]))

    def amend_preexecution_contract(self):
        """One explicitly requested amendment, only before any outcome was seen."""
        self.assert_preexecution_revision_safe()
        folder = self.out / 'preexecution_amendment_1'
        archive = folder / 'original'
        receipt = folder / 'receipt.json'
        if receipt.exists() and read(receipt).get('status') == 'complete':
            for name, h in read(receipt)['new_frozen_hashes'].items():
                if sha(self.out / name) != h:
                    raise RuntimeError('Completed amendment no longer matches current frozen files')
            self.log('preexecution_amendment_reused')
            return
        if receipt.exists() and read(receipt).get('status') == 'blocked':
            raise RuntimeError('The single pre-execution definition amendment is blocked; no second scientific revision is automatic')
        if not (self.out / 'specification_lock.json').exists():
            raise RuntimeError('A frozen original plan is required for this explicit pre-execution amendment')
        archive.mkdir(parents=True, exist_ok=True)
        if not (folder / 'archive_manifest.json').exists():
            names = ['candidate_plan_raw.json', 'specification_plan.json', 'specifications.json', 'specification_lock.json', 'preflight_audit.json', 'blind_code_lock.json', 'analysis_round_0.py', 'implementation_round_0.json', 'run_state.json', 'option_coverage_receipt.json']
            names += [p.name for pattern in ['analysis_revision_*.py', 'scientific_code_review_revision_*.json', 'scientific_implementation_revision_*.json'] for p in self.out.glob(pattern)]
            saved = {}
            for name in sorted(set(names)):
                source = self.out / name
                if source.exists():
                    shutil.copy2(source, archive / name)
                    saved[name] = sha(source)
            for source in (self.out / 'model_tasks').iterdir():
                if source.name.startswith(('scientific_implementation_revision_', 'scientific_code_review_revision_', 'independent_preflight_choice_audit_')):
                    shutil.copytree(source, archive / 'model_tasks' / source.name, dirs_exist_ok=True)
            save(folder / 'archive_manifest.json', {'utc': now(), 'original_hashes': saved, 'guard': 'No execution receipts/results or author reference exists; original scientific freeze preserved before changes'})
            save(receipt, {'status': 'drafting', 'amendment_number': 1, 'started': now(), 'reason': 'Code review found missing pre-execution scientific definitions; explicit authorized amendment before any observed results'})
        manifest = read(folder / 'archive_manifest.json')
        for name, h in manifest['original_hashes'].items():
            if sha(archive / name) != h:
                raise RuntimeError('Original amendment archive changed: ' + name)
        before = read(archive / 'specification_plan.json')
        original_specs = read(archive / 'specifications.json')['specifications']
        reviews = [{'file': p.name, 'review': read(p)} for p in sorted(archive.glob('scientific_code_review_revision_*.json'))]

        def valid(result):
            plan = result.get('amended_plan', {})
            errors = self.validate_plan(plan)
            guard, added = validate_definition_additions(before, plan)
            errors += guard
            if not isinstance(result.get('added_definitions'), list) or not result.get('added_definitions'):
                errors.append('List each added scientific definition and its rationale')
            return sorted(set(errors))
        result_path = folder / 'model_revision.json'
        if result_path.exists():
            result = read(result_path)
            if valid(result):
                raise RuntimeError('Saved amendment no longer passes structural guards')
        else:
            result = self.call('preexecution_missing_definition_amendment_1', base.PLAN_PROMPT + '\n\u8fd9\u662f\u552f\u4e00\u4e00\u6b21\u660e\u793a\u7684\u6267\u884c\u524d\u79d1\u5b66\u5b9a\u4e49\u4fee\u8ba2，\u5c1a\u672a\u6267\u884c\u4efb\u4f55\u7edf\u8ba1，\u4e5f\u672a\u5f00\u653e\u4f5c\u8005\u7ed3\u679c。\u4f9d\u636e\u672c\u8f6e\u4e94\u9879\u8f93\u5165、\u539f\u51bb\u7ed3\u65b9\u6848\u548c\u4ee3\u7801\u79d1\u5b66\u5ba1\u6838，\u8865\u9f50\u786e\u5b9e\u7f3a\u5931\u7684\u79d1\u5b66\u8ba1\u7b97\u5b9a\u4e49。\u4e25\u683c\u4fdd\u6301\u539fH1、\u6548\u5e94comparison_definition、\u5168\u90e8Decision/Option/\u7ea6\u675f/\u6570\u636e\u7ed1\u5b9a/\u65b9\u6cd5\u5f15\u7528/\u987a\u5e8f\u53ca\u6240\u6709\u5df2\u5b9a\u53c2\u6570\u9010\u5b57\u4e0d\u53d8；\u53ea\u80fd\u5728parameters\u5bf9\u8c61\u6216output_contract.inference\u4e2d\u589e\u52a0\u539f\u6765\u7f3a\u5931\u7684\u5b57\u6bb5（\u5305\u62ecHAC\u6838、\u6709\u9650\u6837\u672c\u4fee\u6b63、\u53c2\u7167\u5206\u5e03、\u5206\u4f4d\u662f\u5426\u52a0\u6743\u53ca\u63d2\u503c\u89c4\u5219\u7b49\u9700\u8981\u660e\u786e\u7684\u5b9a\u4e49）。\u4e0d\u5f97\u6539\u5df2\u6709\u53c2\u6570，\u4e0d\u5f97\u65b0\u589eOption\u6216\u6062\u590d\u5df2\u62d2\u7eddOption，\u4e0d\u5f97\u4e3a\u663e\u8457\u6027\u6216\u53ef\u6267\u884c\u6027\u6362\u65b9\u6cd5。\u82e5\u672c\u8d28\u4e0d\u9002\u7528，\u660e\u786e\u963b\u65ad\u800c\u4e0d\u662f\u6362\u76ee\u6807。\u53ef\u6e05\u7406generation_notes、target_interpretation.measurement_assumptions/limits\u548c\u603blimitations\u4e2d\u4e0e\u6700\u7ec8\u6709\u6548Option\u5217\u8868\u6216\u771f\u5b9e\u7ec4\u5408\u6570\u4e0d\u7b26\u7684\u65e7\u53d9\u8ff0；\u8fd9\u4e9b\u8bf4\u660e\u4e0d\u80fd\u521b\u9020\u65b0\u64cd\u4f5c。\u591a\u4f59T3\u7b49\u5df2\u62d2\u9879\u5373\u4f7f\u65e7notes\u63d0\u5230，\u4e5f\u4e0d\u80fd\u91cd\u65b0\u7eb3\u5165。inference.status\u662f\u6267\u884c\u8f6f\u4ef6\u7684\u8fd4\u56de\u5b57\u6bb5，\u79d1\u5b66\u51bb\u7ed3\u4f7f\u7528policy，\u4e8c\u8005\u6309\u5df2\u58f0\u660e\u542b\u4e49\u6620\u5c04\u4e0d\u5c5e\u4e8e\u65b0\u79d1\u5b66\u9009\u62e9。\u8f93\u51fa\u5b8c\u6574amended_plan\u548c\u9010\u9879added_definitions：location/definition/scientific_rationale。\u4e0d\u8981\u6267\u884c\u7edf\u8ba1，\u4e0d\u8bfb\u4efb\u4f55\u4f5c\u8005\u4fe1\u606f。', {'amended_plan': before, 'added_definitions': [{'location': 'exact parameter path', 'definition': 'scientifically defined missing choice', 'scientific_rationale': 'why necessary and justified from allowed inputs'}], 'limitations': []}, legacy.packet({'original_frozen_plan': before, 'scientific_blocking_reviews': reviews, 'final_preflight': read(archive / 'preflight_audit.json'), 'evaluation_policy': self.policy(), 'measured_data_conditions': self.data_conditions()}), valid)
            save(result_path, result)
        self.assert_preexecution_revision_safe()
        save(self.out / 'candidate_plan_raw.json', result['amended_plan'])
        current_preflight = self.out / 'preflight_audit.json'
        if current_preflight.exists():
            current_preflight.unlink()
        self.plan_revision = 1001
        try:
            review = self.original_preflight()
            if not review.get('overall_ready') or review.get('blocking_issues') or any((not f['accept'] or any((not o['accept'] for o in f['option_reviews'])) for f in review['family_reviews'])):
                raise RuntimeError('Revised definitions did not pass new scientific preflight without changing originally accepted choices')
            for family_review in review['family_reviews']:
                original = next((f for f in before['families'] if f['id'] == family_review['family_id']))
                if any((digest(c) not in {digest(x) for x in original.get('constraints', [])} for c in family_review.get('additional_constraints', []))):
                    raise RuntimeError('Amendment preflight adds a new choice constraint; cannot silently change original specifications')
            self.assert_preexecution_revision_safe()
            for name in ['specification_plan.json', 'specifications.json', 'specification_lock.json', 'blind_code_lock.json', 'analysis_round_0.py', 'implementation_round_0.json']:
                path = self.out / name
                if path.exists():
                    path.unlink()
            legacy.freeze()
            actual = read(self.out / 'specifications.json')['specifications']
            if [(s['spec_id'], s['group_id'], s['choices']) for s in actual] != [(s['spec_id'], s['group_id'], s['choices']) for s in original_specs]:
                raise RuntimeError('Re-enumeration changed original accepted specification choices')
        except Exception as failure:
            for name in ['candidate_plan_raw.json', 'specification_plan.json', 'specifications.json', 'specification_lock.json', 'preflight_audit.json']:
                path = self.out / name
                if path.exists():
                    shutil.copy2(path, folder / ('blocked_' + name))
                if (archive / name).exists():
                    shutil.copy2(archive / name, path)
            save(receipt, {**read(receipt), 'status': 'blocked', 'error': str(failure), 'ended': now()})
            raise
        added = validate_definition_additions(before, result['amended_plan'])[1]
        hashes = {name: sha(self.out / name) for name in ['candidate_plan_raw.json', 'specification_plan.json', 'specifications.json', 'specification_lock.json', 'preflight_audit.json']}
        save(receipt, {**read(receipt), 'status': 'complete', 'ended': now(), 'added_parameter_paths': added, 'new_frozen_hashes': hashes, 'original_choices_preserved': True, 'author_results_opened': False, 'statistical_results_seen': False})
        stage = self.state['stages']['05_plan_review_and_freeze']
        stage.setdefault('prior_output_versions', []).append({'utc': now(), 'outputs': stage['outputs'], 'archive': str(archive), 'reason': 'Explicit one-time pre-execution definition amendment; original choices/effect/data bindings unchanged; no outcomes seen'})
        stage['outputs'] = {p: sha(p) for p in stage['outputs']}
        stage['amended'] = now()
        self.state['stages']['06_scientific_code_and_review'] = {'status': 'pending', 'reason': 'New pre-execution scientific definitions require fresh code generation/review'}
        self.state['status'] = 'running'
        self.state.pop('last_error', None)
        self.persist()
        self.log('preexecution_definition_amended', amendment_number=1, accepted_specs=len(actual), added_parameter_paths=added)

def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['run', 'replay', 'amend'])
    parser.add_argument('--manifest', required=True)
    args = parser.parse_args()
    if args.action == 'replay':
        from auto_report_v8 import build_report
        cfg = read(args.manifest)
        build_report(Path(cfg['output']), Path(cfg['report']), Path(cfg['quarantine']))
        return
    runner = AutoRunV9(args.manifest)
    if args.action == 'amend':
        runner.amend_preexecution_contract()
    runner.run()
if __name__ == '__main__':
    cli()
