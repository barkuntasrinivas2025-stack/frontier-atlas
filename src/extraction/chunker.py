from dataclasses import dataclass
import re
@dataclass(frozen=True)
class Chunk:
    text: str
    index: int
    estimated_tokens: int
class IntelligentChunker:
    def __init__(self,max_tokens=3000,overlap_tokens=300): self.max_tokens=max_tokens; self.overlap_tokens=overlap_tokens
    def split(self,text:str)->list[Chunk]:
        sentences=[s.strip() for s in re.split(r'(?<=[.!?])\s+',text.strip()) if s.strip()]
        out=[]; cur=[]; tokens=0; idx=0
        for s in sentences:
            n=max(1,len(s)//4)
            if cur and tokens+n>self.max_tokens:
                t=' '.join(cur); out.append(Chunk(t,idx,tokens)); idx+=1
                overlap=[]; ot=0
                for old in reversed(cur):
                    on=max(1,len(old)//4)
                    if ot+on>self.overlap_tokens: break
                    overlap.insert(0,old); ot+=on
                cur=overlap+[s]; tokens=ot+n
            else: cur.append(s); tokens+=n
        if cur: out.append(Chunk(' '.join(cur),idx,tokens))
        return out
