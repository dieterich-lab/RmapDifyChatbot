# Code Node: KR Chunk Filter
# Node ID: 1778800001036

import re
import json

NL = chr(10)  # newline - avoids YAML escaping issues

def _extract_text(chunk):
    if isinstance(chunk, dict):
        seg = chunk.get('segment', {})
        if isinstance(seg, dict) and seg.get('content', '').strip():
            return str(seg['content']).strip()
        if chunk.get('content', '').strip():
            return str(chunk['content']).strip()
        ccs = chunk.get('child_chunks', [])
        if ccs:
            parts = [str(c.get('content','')).strip() for c in ccs if isinstance(c, dict)]
            return NL.join(p for p in parts if p)
        return ''
    text = str(chunk or '').strip()
    if text.startswith('{') or text.startswith('['):
        try:
            obj = json.loads(text)
            if isinstance(obj, dict):
                return _extract_text(obj)
            if isinstance(obj, list):
                parts = [_extract_text(i) for i in obj[:3]]
                return NL.join(p for p in parts if p)
        except Exception:
            pass
    return text

def _is_reference_chunk(text):
    t = str(text or '').strip()
    if not t or len(t) < 20:
        return False
    
    doi_count = len(re.findall(r'doi\.org/\S+|DOI:\s*\S+', t, re.IGNORECASE))
    numbered_refs = len(re.findall(r'(?:^|' + NL + r')\s*(?:\d+\.[ \t]|\[\d+\][ \t])', t))
    etal_count = len(re.findall(r'\bet\s+al\b', t, re.IGNORECASE))
    year_parens = len(re.findall(r'\((?:19|20)\d{2}[a-z]?\)', t))
    
    score = doi_count * 3.0 + numbered_refs * 1.5 + etal_count * 0.5 + year_parens * 0.3
    density = score / max(1.0, len(t) / 500.0)
    
    if doi_count >= 2:
        return True
    if numbered_refs >= 4:
        return True
    if density > 3.0:
        return True
    
    first_line = t.split(NL)[0].strip()
    if re.match(r'^\d+[\.,]\s', first_line) or re.match(r'^\[\d+\]', first_line):
        if density > 1.5:
            return True
    
    return False

def main(kr_result=None):
    if not isinstance(kr_result, list):
        return {'filtered_chunks': [], 'chunk_count': 0, 'chunks_removed': 0}
    kept = []
    removed = 0
    for c in kr_result:
        text = _extract_text(c)
        if not text or len(text) < 20:
            continue
        if _is_reference_chunk(text):
            removed += 1
        else:
            kept.append(text)
    if not kept:
        kept.append('ALL ' + str(len(kr_result)) + ' RETRIEVED CHUNKS WERE REFERENCE LISTS AND FILTERED OUT. The query may match bibliography sections rather than paper body text. Try a more specific query or different search terms.')
    return {'filtered_chunks': kept, 'chunk_count': len(kept), 'chunks_removed': removed}
