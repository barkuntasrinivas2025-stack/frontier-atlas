from dataclasses import dataclass
from rapidfuzz.fuzz import ratio
from .normalizer import normalize_name
@dataclass(frozen=True)
class Resolution:
    raw_name:str; normalized_name:str; canonical_name:str; method:str; confidence:float
class EntityResolver:
    def __init__(self, seed:dict[str,list[str]]|None=None):
        self.alias_to_canonical={}
        for canonical,aliases in (seed or {}).items():
            for x in [canonical,*aliases]: self.alias_to_canonical[normalize_name(x)]=canonical
    def resolve(self,name:str)->Resolution:
        raw=name.strip(); norm=normalize_name(raw)
        if not norm: return Resolution(raw,norm,raw,'unresolved',0.0)
        if norm in self.alias_to_canonical: return Resolution(raw,norm,self.alias_to_canonical[norm],'seed_exact',1.0)
        return Resolution(raw,norm,raw,'unresolved',0.0)
    def resolve_against(self,name:str, candidates:list[str])->Resolution:
        r=self.resolve(name)
        if r.method!='unresolved': return r
        best=max(candidates,key=lambda c:ratio(r.normalized_name,normalize_name(c)),default='')
        score=ratio(r.normalized_name,normalize_name(best))/100 if best else 0
        if score>=0.92: return Resolution(r.raw_name,r.normalized_name,best,'fuzzy_high',score)
        return r
