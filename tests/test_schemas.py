from datetime import datetime,timezone
from src.extraction.schemas import NewsArticle,SourceProvenance

def test_provenance_required():
 s=SourceProvenance(source_url='https://example.com',source_name='test',collected_at=datetime.now(timezone.utc)); n=NewsArticle(title='AI',url='https://example.com/a',published_at=datetime.now(timezone.utc),source=s); assert n.title=='AI'
