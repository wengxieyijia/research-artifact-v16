# --- (BOBA_CONFIG)
{
  "graph": [
    "Run"
  ],
  "decisions": [
    {
      "var": "SPEC_ID",
      "options": [
        "'S0001'",
        "'S0002'",
        "'S0003'",
        "'S0004'",
        "'S0005'",
        "'S0006'",
        "'S0007'",
        "'S0008'",
        "'S0009'",
        "'S0010'",
        "'S0011'",
        "'S0012'",
        "'S0013'",
        "'S0014'",
        "'S0015'",
        "'S0016'",
        "'S0017'",
        "'S0018'",
        "'S0019'",
        "'S0020'",
        "'S0021'",
        "'S0022'",
        "'S0023'",
        "'S0024'",
        "'S0025'",
        "'S0026'",
        "'S0027'",
        "'S0028'",
        "'S0029'",
        "'S0030'",
        "'S0031'",
        "'S0032'",
        "'S0033'",
        "'S0034'",
        "'S0035'",
        "'S0036'",
        "'S0037'",
        "'S0038'",
        "'S0039'",
        "'S0040'",
        "'S0041'",
        "'S0042'",
        "'S0043'",
        "'S0044'",
        "'S0045'",
        "'S0046'",
        "'S0047'",
        "'S0048'",
        "'S0049'",
        "'S0050'",
        "'S0051'",
        "'S0052'",
        "'S0053'",
        "'S0054'",
        "'S0055'",
        "'S0056'",
        "'S0057'",
        "'S0058'",
        "'S0059'",
        "'S0060'"
      ]
    }
  ]
}

# --- (Run)
import sys
sys.path.insert(0,'external_workspace/2026-10-20\\h1-1-desicion-option-2-dag-8\\outputs\\Automated_Five_v9_20261029\\05_nlsy_linked\\isolated_execution')
from blind_five_worker_v7 import run_one
SPEC_ID = {{SPEC_ID}}
run_one('external_workspace/2026-10-20\\h1-1-desicion-option-2-dag-8\\outputs\\Automated_Five_v9_20261029\\05_nlsy_linked\\isolated_execution',SPEC_ID,execution_round=0)
