#!/root/miniconda3/envs/kb/bin/python
# -*- coding: utf-8 -*-
"""
match_document_pdf_v2.py — 化工安全标准/法规 文档-PDF多阶段自动匹配
================================================================
Phase 1: 标准编号匹配 (code + doc_id extraction, confidence=1.0)
Phase 2: 法规编号匹配 (regulation document number, confidence=0.95)
Phase 3: 附件ID匹配   (attachment_id, confidence=1.0)
Phase 4: 标题模糊匹配 (rapidfuzz + multiprocessing, confidence=0.85/0.70/0.60)
Phase 5: 未匹配候选输出 (top-3 candidates for manual review)
"""

import pandas as pd
import re
import os
from datetime import datetime
from rapidfuzz import fuzz
from collections import defaultdict
from multiprocessing import Pool, cpu_count

# ============================================
# 配置
# ============================================
PROJECT_ROOT = '/root/autodl-tmp/chemical_kb'
DOC_MASTER_PATH = f'{PROJECT_ROOT}/data/parsed/document_master.csv'
PDF_INV_PATH = f'{PROJECT_ROOT}/data/pdf_inventory.csv'
OUT_MAPPING = f'{PROJECT_ROOT}/data/document_pdf_mapping.csv'
OUT_UNMATCHED = f'{PROJECT_ROOT}/data/unmatched_documents.csv'


# ============================================
# 日志工具
# ============================================
class Logger:
    def __init__(self):
        self.start_time = datetime.now()
        self.lines = []

    def log(self, msg):
        ts = datetime.now().strftime('%H:%M:%S')
        line = f'[{ts}] {msg}'
        self.lines.append(line)
        print(line)

    def write(self, path):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(f'Match Log - {self.start_time.isoformat()}\n')
            f.write('=' * 60 + '\n')
            for line in self.lines:
                f.write(line + '\n')


logger = Logger()


# ============================================
# 标准化函数
# ============================================

def normalize_standard_code(code):
    """统一化标准编号: 去除所有分隔符, 只保留字母数字。
    DB11/T 1578-2025 -> DB11T15782025
    """
    if pd.isna(code) or str(code).strip() == '':
        return None
    code = str(code).strip()
    code = re.sub(r'[\s_/–—―−\-‐]', '', code)  # all dash variants
    code = code.upper()
    return code


def extract_std_code_from_doc_id(doc_id):
    """从 doc_id 格式提取标准编号。
    STD_AQ_4104_2025 -> AQ 4104-2025
    STD_SY_T_5857_2025 -> SY/T 5857-2025
    """
    if pd.isna(doc_id) or not str(doc_id).startswith('STD_'):
        return None
    parts = str(doc_id).split('_')
    if len(parts) < 4:
        return None
    prefix = parts[1]
    t_flag = False
    idx = 2
    if idx < len(parts) and parts[idx] == 'T':
        t_flag = True
        idx += 1
    if idx >= len(parts):
        return None
    number = parts[idx]
    idx += 1
    if idx >= len(parts):
        return None
    year = parts[idx]
    if t_flag:
        code = f'{prefix}/T {number}-{year}'
    else:
        code = f'{prefix} {number}-{year}'
    return normalize_standard_code(code)


def extract_std_code_from_filename(filename):
    """从 PDF 文件名提取标准编号 (修复版, 正确处理 _T /T 模式)。

    SN_T 2414.1-2010.pdf -> SN/T 2414.1-2010 -> SNT2414.12010
    DB11_T 1578-2025.pdf  -> DB11/T 1578-2025  -> DB11T15782025
    AQ 3011-2007.pdf      -> AQ 3011-2007      -> AQ30112007
    DB11_ 358-2016.pdf    -> DB11 358-2016     -> DB113582016
    """
    if pd.isna(filename):
        return None
    name = str(filename)
    name = re.sub(r'\.pdf$', '', name, flags=re.IGNORECASE)

    # 检测是否为 /T 或 _T 类型标准 (T 是推荐性标准标记)
    is_T = bool(re.search(r'[_/]\s*T\b', name, re.IGNORECASE))

    # 提取: 前缀(2+字母+可选数字) + 分隔符 + 编号(可带小数) + 破折号 + 年份
    pat = r'([A-Z]{2,}\d{0,4})\s*[_T/\s]*?(\d{2,5}(?:\.\d+)?)\s*[\-–—]\s*(\d{4})'
    m = re.search(pat, name, re.IGNORECASE)
    if m:
        prefix, num, year = m.group(1), m.group(2), m.group(3)
        if is_T:
            return normalize_standard_code(f'{prefix}/T {num}-{year}')
        return normalize_standard_code(f'{prefix} {num}-{year}')
    return None


def normalize_regulation_code_for_match(code):
    """统一化法规编号: 统一括号为[]"""
    if pd.isna(code) or str(code).strip() == '':
        return None
    code = str(code).strip()
    code = re.sub(r'\s+', '', code)
    code = code.replace('〔', '[').replace('〕', ']')  # 〔〕
    code = code.replace('﹝', '[').replace('﹞', ']')  # ﹝﹞
    return code


def extract_reg_code_from_filename(filename):
    """从 PDF 文件名提取法规文号。"""
    if pd.isna(filename):
        return None
    name = str(filename)
    name = re.sub(r'\.pdf$', '', name, flags=re.IGNORECASE)
    patterns = [
        r'[一-鿿]+令第\d+号',
        r'[一-鿿]+〔\d{4}〕\d+号',
        r'[一-鿿]+公告\d{4}年第\d+号',
        r'[一-鿿]+通令第\d+号',
    ]
    for pat in patterns:
        m = re.search(pat, name)
        if m:
            return m.group(0)
    return None


def extract_attachment_id_from_filename(filename):
    """从 PDF 文件名提取 16 位 hex attachment_id。"""
    if pd.isna(filename):
        return None
    m = re.search(r'([0-9A-F]{16})', str(filename), re.IGNORECASE)
    return m.group(1).upper() if m else None


def clean_for_title_match(text):
    """清理文本用于 fuzzy 匹配 (关键修复版).

    修复点: 保留书名号内核心内容, 仅删除公文套话.
    """
    if pd.isna(text) or str(text).strip() == '':
        return ''
    t = str(text).strip()

    # 去除 .pdf
    t = re.sub(r'\.pdf$', '', t, flags=re.IGNORECASE)

    # 日期前后缀
    t = re.sub(r'^\d{8}\s*-{1,3}', '', t)
    t = re.sub(r'[-_]{1,3}\d{8}$', '', t)
    t = re.sub(r'\.\d{8}$', '', t)

    # 标准编号前缀
    t = re.sub(r'^[A-Z]{2,}\s*[_T/]?\s*\d{2,5}(?:\.\d+)?\s*[\-–—]\s*\d{4}\s*_?', '', t)

    # 核心修复: 提取书名号内容 (去掉《》但保留内部标题!)
    t = re.sub(r'《([^》]*)》', r'\1', t)  # 《》
    t = re.sub(r'〈([^〉]*)〉', r'\1', t)  # 〈〉

    # 去除全角括号及其内容
    t = re.sub(r'（[^）]*）', '', t)  # （）
    t = re.sub(r'〔[^〕]*〕', '', t)  # 〔〕
    t = re.sub(r'［[^］]*］', '', t)  # ［］
    t = re.sub(r'「[^」]*」', '', t)  # 「」
    t = re.sub(r'『[^』]*』', '', t)  # 『』

    # 去除公文套话
    boilerplate = [
        '关于印发', '关于做好', '关于进一步加强', '关于公布', '关于发布',
        '关于调整', '关于修订', '关于转发', '关于', '印发',
    ]
    for bp in boilerplate:
        t = re.sub(re.escape(bp), '', t)

    # 去除尾部公文词
    t = re.sub(r'的通知$', '', t)
    t = re.sub(r'的公告$', '', t)
    t = re.sub(r'的通告$', '', t)
    t = re.sub(r'的办法$', '', t)
    t = re.sub(r'的规定$', '', t)
    t = re.sub(r'的意见$', '', t)
    t = re.sub(r'的方案$', '', t)
    t = re.sub(r'的通知$', '', t)

    # 去除标点空格
    t = re.sub(r'[、。，！“”‘’；：!?,:;\s]+', '', t)
    t = re.sub(r'[\-–—―_/\\·]+', '', t)

    return t.strip()


def extract_core_title(filename):
    """从 PDF 文件名提取核心标题 (去日期/编号前后缀)。"""
    if pd.isna(filename):
        return ''
    t = str(filename).strip()
    t = re.sub(r'\.pdf$', '', t, flags=re.IGNORECASE)
    t = re.sub(r'^\d{8}\s*-{1,3}', '', t)
    t = re.sub(r'[-_]{1,3}\d{8}$', '', t)
    t = re.sub(r'^[A-Z]{2,}\s*[_T/]?\s*\d{2,5}(?:\.\d+)?\s*[\-–—]\s*\d{4}\s*_?', '', t)
    return t.strip()


# ============================================
# 多进程辅助函数 (模块级别, 可 pickle)
# ============================================

def _fuzz_max_score(a, b):
    """计算两个清洗后字符串的最高 fuzzy 得分。"""
    if not a or not b:
        return 0
    return max(
        fuzz.token_sort_ratio(a, b),
        fuzz.partial_ratio(a, b),
        fuzz.token_set_ratio(a, b)
    )


def _compute_doc_scores(args):
    """为一个 doc 计算与 PDF 池的所有得分 (>=50 保留)。
    args = (doc_id, doc_cleaned, [(pdf_id, pdf_cleaned), ...])
    """
    doc_id, doc_cleaned, pdf_pool = args
    scores = []
    if not doc_cleaned:
        return (doc_id, [])
    for pdf_id, pdf_cleaned in pdf_pool:
        score = _fuzz_max_score(doc_cleaned, pdf_cleaned)
        if score >= 50:
            scores.append((pdf_id, score))
    scores.sort(key=lambda x: x[1], reverse=True)
    return (doc_id, scores)


def _compute_top3(args):
    """为一个 doc 找 top-3 PDF 候选 (score>30)。
    args = (doc_id, doc_title, doc_cleaned, doc_type, [(pdf_id, filename, cleaned), ...])
    """
    doc_id, doc_title, doc_cleaned, doc_type, pdf_pool = args
    rows = []
    candidates = []
    if doc_cleaned:
        for pdf_id, filename, pdf_cleaned in pdf_pool:
            score = _fuzz_max_score(doc_cleaned, pdf_cleaned)
            if score > 30:
                candidates.append((pdf_id, filename, score))
    candidates.sort(key=lambda x: x[2], reverse=True)
    top3 = candidates[:3]

    if top3:
        for i, (pdf_id, fn, score) in enumerate(top3):
            rows.append({
                'doc_id': doc_id, 'title': doc_title, 'doc_type': doc_type,
                'candidate_rank': i + 1, 'candidate_pdf_id': pdf_id,
                'candidate_filename': fn, 'candidate_score': score
            })
    else:
        rows.append({
            'doc_id': doc_id, 'title': doc_title, 'doc_type': doc_type,
            'candidate_rank': 0, 'candidate_pdf_id': '',
            'candidate_filename': '', 'candidate_score': 0
        })
    return rows


# ============================================
# 主匹配逻辑
# ============================================

def main():
    logger.log('=' * 60)
    logger.log('Document-PDF Matching v2 (fixed title cleaning)')
    logger.log('=' * 60)

    # --- 加载 ---
    logger.log('Loading document_master.csv ...')
    df_doc = pd.read_csv(DOC_MASTER_PATH, encoding='utf-8-sig', dtype=str)
    logger.log(f'  {len(df_doc)} documents')

    logger.log('Loading pdf_inventory.csv ...')
    df_pdf = pd.read_csv(PDF_INV_PATH, encoding='utf-8-sig', dtype=str)
    logger.log(f'  {len(df_pdf)} PDFs')

    df_std = df_doc[df_doc['doc_type'] == 'standard'].copy()
    df_reg = df_doc[df_doc['doc_type'] == 'regulation'].copy()
    df_pdf_std = df_pdf[df_pdf['document_type'] == '标准'].copy()  # 标准
    df_pdf_reg = df_pdf[df_pdf['document_type'] == '法规'].copy()  # 法规

    logger.log(f'  Standards:  {len(df_std)} docs / {len(df_pdf_std)} PDFs')
    logger.log(f'  Regulations: {len(df_reg)} docs / {len(df_pdf_reg)} PDFs')

    matched_pdf_ids = set()
    matched_doc_ids = set()
    results = []

    # ====================================================================
    # PHASE 1: 标准编号匹配 (confidence=1.0)
    # ====================================================================
    logger.log('=' * 60)
    logger.log('PHASE 1: Standard Code Matching')

    pdf_code_index = defaultdict(list)
    # Source 1: standard_code field
    for _, row in df_pdf_std.iterrows():
        code = normalize_standard_code(row['standard_code'])
        if code:
            pdf_code_index[code].append(row['pdf_id'])
    # Source 2: filename extraction (for PDFs with empty standard_code)
    fn_added = 0
    for _, row in df_pdf_std.iterrows():
        code = extract_std_code_from_filename(row['filename'])
        if code:
            if code not in pdf_code_index:
                pdf_code_index[code] = [row['pdf_id']]
                fn_added += 1
            elif row['pdf_id'] not in pdf_code_index[code]:
                pdf_code_index[code].append(row['pdf_id'])

    logger.log(f'  PDF code index: {len(pdf_code_index)} unique codes (fn-supplement: {fn_added})')

    p1_count = 0
    for _, doc in df_std.iterrows():
        doc_id = doc['doc_id']
        if doc_id in matched_doc_ids:
            continue

        # Try multiple sources for the standard code
        codes = []
        c1 = normalize_standard_code(doc['code'])
        if c1:
            codes.append(('code_field', c1))
        c2 = extract_std_code_from_doc_id(doc['doc_id'])
        if c2 and c2 not in [c for _, c in codes]:
            codes.append(('doc_id', c2))

        for source, code in codes:
            if code in pdf_code_index:
                candidates = [p for p in pdf_code_index[code] if p not in matched_pdf_ids]
                if candidates:
                    pid = candidates[0]
                    pdf_row = df_pdf[df_pdf['pdf_id'] == pid].iloc[0]
                    results.append({
                        'doc_id': doc_id, 'title': doc['title'],
                        'pdf_id': pid, 'pdf_path': pdf_row['path'],
                        'match_method': f'standard_code_{source}', 'confidence': 1.0
                    })
                    matched_pdf_ids.add(pid)
                    matched_doc_ids.add(doc_id)
                    p1_count += 1
                    break

    logger.log(f'  Phase 1 matched: {p1_count}')

    # ====================================================================
    # PHASE 2: 法规编号匹配 (confidence=0.95)
    # ====================================================================
    logger.log('=' * 60)
    logger.log('PHASE 2: Regulation Code Matching')

    reg_pdf_code_index = defaultdict(list)
    for _, row in df_pdf_reg.iterrows():
        code = extract_reg_code_from_filename(row['filename'])
        if code:
            nc = normalize_regulation_code_for_match(code)
            if nc:
                reg_pdf_code_index[nc].append(row['pdf_id'])

    logger.log(f'  Regulation codes in PDF filenames: {len(reg_pdf_code_index)}')

    p2_count = 0
    for _, doc in df_reg.iterrows():
        doc_id = doc['doc_id']
        if doc_id in matched_doc_ids:
            continue
        doc_code = normalize_regulation_code_for_match(doc['code'])
        if not doc_code:
            continue
        if doc_code in reg_pdf_code_index:
            candidates = [p for p in reg_pdf_code_index[doc_code] if p not in matched_pdf_ids]
            if candidates:
                pid = candidates[0]
                pdf_row = df_pdf[df_pdf['pdf_id'] == pid].iloc[0]
                results.append({
                    'doc_id': doc_id, 'title': doc['title'],
                    'pdf_id': pid, 'pdf_path': pdf_row['path'],
                    'match_method': 'regulation_code', 'confidence': 0.95
                })
                matched_pdf_ids.add(pid)
                matched_doc_ids.add(doc_id)
                p2_count += 1

    logger.log(f'  Phase 2 matched: {p2_count}')

    # ====================================================================
    # PHASE 3: 附件ID匹配 (confidence=1.0)
    # ====================================================================
    logger.log('=' * 60)
    logger.log('PHASE 3: Attachment ID Matching')

    pdf_att_index = defaultdict(list)
    for _, row in df_pdf.iterrows():
        att = extract_attachment_id_from_filename(row['filename'])
        if att:
            pdf_att_index[att].append(row['pdf_id'])

    logger.log(f'  Attachment IDs in PDF filenames: {len(pdf_att_index)}')

    p3_count = 0
    for _, doc in df_reg.iterrows():
        doc_id = doc['doc_id']
        if doc_id in matched_doc_ids:
            continue
        att_id = str(doc['attachment_id']).strip().upper() if pd.notna(doc['attachment_id']) else ''
        if not att_id or att_id in ('', 'NAN', 'NONE'):
            continue
        if att_id in pdf_att_index:
            candidates = [p for p in pdf_att_index[att_id] if p not in matched_pdf_ids]
            if candidates:
                pid = candidates[0]
                pdf_row = df_pdf[df_pdf['pdf_id'] == pid].iloc[0]
                results.append({
                    'doc_id': doc_id, 'title': doc['title'],
                    'pdf_id': pid, 'pdf_path': pdf_row['path'],
                    'match_method': 'attachment_id', 'confidence': 1.0
                })
                matched_pdf_ids.add(pid)
                matched_doc_ids.add(doc_id)
                p3_count += 1

    logger.log(f'  Phase 3 matched: {p3_count}')

    # ====================================================================
    # PHASE 4: 标题模糊匹配 (multiprocessing)
    # ====================================================================
    logger.log('=' * 60)
    logger.log('PHASE 4: Title Fuzzy Matching (rapidfuzz + multiprocessing)')

    unmatched_docs = df_doc[~df_doc['doc_id'].isin(matched_doc_ids)]
    unmatched_pdfs = df_pdf[~df_pdf['pdf_id'].isin(matched_pdf_ids)]
    logger.log(f'  Before Phase 4: {len(unmatched_docs)} docs / {len(unmatched_pdfs)} PDFs')

    # 预处理 PDF
    pdf_list = []
    for _, row in unmatched_pdfs.iterrows():
        core = extract_core_title(row['filename'])
        cleaned = clean_for_title_match(core) if core else clean_for_title_match(row['filename'])
        pdf_list.append({
            'pdf_id': row['pdf_id'], 'cleaned': cleaned,
            'path': row['path'], 'document_type': row['document_type']
        })

    # 预处理 Doc
    doc_list = []
    for _, row in unmatched_docs.iterrows():
        doc_list.append({
            'doc_id': row['doc_id'], 'cleaned': clean_for_title_match(row['title']),
            'title': row['title'], 'doc_type': row['doc_type']
        })

    p4_high = 0
    p4_medium = 0
    p4_low = 0
    num_workers = min(cpu_count(), 64)
    logger.log(f'  Using {num_workers} workers')

    for doc_type_label in ['standard', 'regulation']:
        pdf_type_label = '标准' if doc_type_label == 'standard' else '法规'

        docs_subset = [d for d in doc_list if d['doc_type'] == doc_type_label]
        pdfs_subset = [p for p in pdf_list if p['document_type'] == pdf_type_label]

        if not docs_subset or not pdfs_subset:
            logger.log(f'  [{doc_type_label}] Skip')
            continue

        logger.log(f'  [{doc_type_label}] {len(docs_subset)} docs x {len(pdfs_subset)} PDFs = {len(docs_subset)*len(pdfs_subset)} pairs')

        pdf_pool_tuples = [(p['pdf_id'], p['cleaned']) for p in pdfs_subset]
        tasks = [(d['doc_id'], d['cleaned'], pdf_pool_tuples) for d in docs_subset]

        with Pool(num_workers) as pool:
            doc_scores = pool.map(_compute_doc_scores, tasks)

        # Greedy matching
        all_pairs = []
        for did, scores in doc_scores:
            for pid, score in scores:
                all_pairs.append((did, pid, score))
        all_pairs.sort(key=lambda x: x[2], reverse=True)

        assigned_docs = set()
        assigned_pdfs = set()
        for did, pid, score in all_pairs:
            if did in assigned_docs or pid in assigned_pdfs:
                continue
            if score < 60:
                break

            doc_row = df_doc[df_doc['doc_id'] == did].iloc[0]
            pdf_row = df_pdf[df_pdf['pdf_id'] == pid].iloc[0]

            if score >= 85:
                confidence, method = 0.85, 'title_fuzzy_high'
                p4_high += 1
            elif score >= 70:
                confidence, method = 0.70, 'title_fuzzy_medium'
                p4_medium += 1
            else:
                confidence, method = 0.60, 'title_fuzzy_low'
                p4_low += 1

            results.append({
                'doc_id': did, 'title': doc_row['title'],
                'pdf_id': pid, 'pdf_path': pdf_row['path'],
                'match_method': method, 'confidence': confidence
            })
            matched_pdf_ids.add(pid)
            matched_doc_ids.add(did)
            assigned_docs.add(did)
            assigned_pdfs.add(pid)

    logger.log(f'  Phase 4 high (>=85): {p4_high}')
    logger.log(f'  Phase 4 medium (70-84): {p4_medium}')
    logger.log(f'  Phase 4 low (60-69): {p4_low}')

    # ====================================================================
    # PHASE 5: 未匹配候选输出
    # ====================================================================
    logger.log('=' * 60)
    logger.log('PHASE 5: Unmatched Candidates')

    final_unmatched_docs = df_doc[~df_doc['doc_id'].isin(matched_doc_ids)]
    final_unmatched_pdfs = df_pdf[~df_pdf['pdf_id'].isin(matched_pdf_ids)]
    logger.log(f'  Finally unmatched: {len(final_unmatched_docs)} docs / {len(final_unmatched_pdfs)} PDFs')

    final_pdf_list = []
    for _, row in final_unmatched_pdfs.iterrows():
        core = extract_core_title(row['filename'])
        cleaned = clean_for_title_match(core) if core else clean_for_title_match(row['filename'])
        final_pdf_list.append({
            'pdf_id': row['pdf_id'], 'filename': row['filename'],
            'cleaned': cleaned, 'document_type': row['document_type']
        })

    final_doc_list = []
    for _, row in final_unmatched_docs.iterrows():
        final_doc_list.append({
            'doc_id': row['doc_id'], 'title': row['title'],
            'cleaned': clean_for_title_match(row['title']),
            'doc_type': row['doc_type']
        })

    unmatched_rows = []
    for doc_type_label in ['standard', 'regulation']:
        pdf_type_label = '标准' if doc_type_label == 'standard' else '法规'
        docs_t = [d for d in final_doc_list if d['doc_type'] == doc_type_label]
        pdfs_t = [(p['pdf_id'], p['filename'], p['cleaned']) for p in final_pdf_list
                  if p['document_type'] == pdf_type_label]

        if not docs_t:
            continue

        tasks = [(d['doc_id'], d['title'], d['cleaned'], d['doc_type'], pdfs_t) for d in docs_t]

        with Pool(num_workers) as pool:
            result_batches = pool.map(_compute_top3, tasks)
        for batch in result_batches:
            unmatched_rows.extend(batch)

    logger.log(f'  Candidates generated: {len(unmatched_rows)} rows')

    # ====================================================================
    # 保存
    # ====================================================================
    logger.log('=' * 60)
    logger.log('Saving results ...')
    os.makedirs(os.path.dirname(OUT_MAPPING), exist_ok=True)

    df_result = pd.DataFrame(results).sort_values('doc_id').reset_index(drop=True)
    df_result.to_csv(OUT_MAPPING, index=False, encoding='utf-8-sig')
    logger.log(f'  -> {OUT_MAPPING} ({len(df_result)} rows)')

    df_unmatched = pd.DataFrame(unmatched_rows)
    df_unmatched.to_csv(OUT_UNMATCHED, index=False, encoding='utf-8-sig')
    logger.log(f'  -> {OUT_UNMATCHED} ({len(df_unmatched)} rows)')

    # ====================================================================
    # 统计
    # ====================================================================
    logger.log('=' * 60)
    logger.log('MATCHING STATISTICS')
    logger.log('=' * 60)

    total_docs = len(df_doc)
    matched_docs_n = len(set(r['doc_id'] for r in results))
    unmatched_docs_n = len(final_unmatched_docs)

    logger.log(f'  Documents: {total_docs} total')
    logger.log(f'    Matched:   {matched_docs_n} ({matched_docs_n/total_docs*100:.1f}%)')
    logger.log(f'    Unmatched: {unmatched_docs_n} ({unmatched_docs_n/total_docs*100:.1f}%)')

    for dtype, label, prefix in [('standard', 'Standard', 'STD_'), ('regulation', 'Regulation', 'REG_')]:
        total_t = len(df_doc[df_doc['doc_type'] == dtype])
        matched_t = len([r for r in results if r['doc_id'].startswith(prefix)])
        unm_t = total_t - matched_t
        rate = matched_t / total_t * 100 if total_t > 0 else 0
        logger.log(f'  {label}: {total_t} total, {matched_t} matched, {unm_t} unmatched ({rate:.1f}%)')

    logger.log('  By match method:')
    for method, count in df_result['match_method'].value_counts().items():
        logger.log(f'    {method}: {count}')

    logger.log('  By confidence:')
    for conf, count in df_result['confidence'].value_counts().sort_index().items():
        logger.log(f'    {conf:.2f}: {count}')

    logger.log('=' * 60)
    logger.log('DONE')
    log_path = f'{PROJECT_ROOT}/data/match_v2_log.txt'
    logger.write(log_path)
    logger.log(f'Log saved to {log_path}')

    return df_result, df_unmatched


if __name__ == '__main__':
    main()
