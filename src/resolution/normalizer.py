import re
LEGAL={'inc','inc.','llc','ltd','ltd.','corp','corp.','corporation','company','co','co.','limited'}
def normalize_name(name:str)->str:
    s=name.casefold().replace('&',' and ')
    s=re.sub(r'[.,]',' ',s); parts=[p for p in re.split(r'\s+',s) if p and p not in LEGAL]
    return ' '.join(parts)
