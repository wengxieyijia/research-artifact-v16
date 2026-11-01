# Recorded v16 source. Original prompt strings are preserved with Unicode escapes.
"""Mechanical many-to-one Data join; no statistical fitting or author code."""
import hashlib, json
from pathlib import Path
import pandas as pd
import pyreadr
ROOT = Path(__file__).resolve().parents[2]

def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()

def save(p, v):
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2), encoding='utf-8')

def prepare():
    folder = ROOT / 'work/nlsy_linkage_inputs_20261030'
    original = ROOT / 'work/testset_v9_inputs_20261029/01_nlsy/data.csv'
    values = pd.read_csv(original)
    public = pyreadr.read_r(str(folder / 'SubjectDetails79.rda'))['SubjectDetails79']
    lookup = public[['SubjectTag', 'ExtendedID']].copy()
    if lookup.SubjectTag.duplicated().any():
        raise ValueError('Public identity is not unique; cannot silently select a family')
    joined = values.merge(lookup, on='SubjectTag', how='left', validate='many_to_one', sort=False)
    pd.testing.assert_frame_equal(values.reset_index(drop=True), joined[list(values)].reset_index(drop=True))
    path = folder / 'data_with_family.csv'
    joined.to_csv(path, index=False)
    metadata = {'source_url': 'https://github.com/nlsy-links/NlsyLinks/blob/master/R/subject-details-79-doc.R', 'archive_sha256': sha(folder / 'SubjectDetails79.rda'), 'source_codebook_member': 'NlsyLinks public SubjectDetails79 documentation', 'field_metadata': [{'name': 'SubjectTag', 'source_label': 'Unique subject identity in NlsyLinks. For original-generation NLSY79 respondents the recorded CaseID has 00 appended.'}, {'name': 'ExtendedID', 'source_label': 'Extended family identifier supplied in the public NlsyLinks Data; connected to the NLSY79 household identity. A group identifier, not a genetic effect estimate.'}], 'release_policy': 'Public observation identifiers and data-variable labels only. No target author analysis code, method choices, estimates or significance.'}
    save(folder / 'column_metadata.json', metadata)
    receipt = {'original_data_sha256': sha(original), 'public_data_sha256': sha(folder / 'SubjectDetails79.rda'), 'joined_data_sha256': sha(path), 'join_key': 'SubjectTag', 'relationship': 'many_to_one', 'original_rows': len(values), 'joined_rows': len(joined), 'original_columns_unchanged': True, 'added_columns': ['ExtendedID'], 'missing_family_rows': int(joined.ExtendedID.isna().sum()), 'unique_subjects': int(joined.SubjectTag.nunique()), 'unique_observed_families': int(joined.ExtendedID.nunique()), 'rows_selected_or_dropped': False, 'statistical_models_or_target_author_code_executed': False, 'source_receipt': 'download_receipt.json'}
    save(folder / 'join_receipt.json', receipt)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
if __name__ == '__main__':
    prepare()
