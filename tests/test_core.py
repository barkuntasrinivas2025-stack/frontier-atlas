from datetime import datetime,timezone,timedelta
import asyncio
from src.extraction.chunker import IntelligentChunker
from src.freshness.dates import parse_publication_date,is_within_previous_24h
from src.freshness.dedup import canonical_url,sha256_text
from src.resolution.resolver import EntityResolver
from src.acquisition.phase2 import parse_feed
from src.crawlers.phase2_sources import SourceConfig

def test_chunker():
 c=IntelligentChunker(100,10).split('Sentence one. '*200); assert len(c)>1 and all(x.text for x in c)
def test_dates():
 now=datetime(2026,9,10,12,tzinfo=timezone.utc); assert parse_publication_date('3 hours ago',now=now)==now-timedelta(hours=3); assert not is_within_previous_24h(now-timedelta(hours=25),now=now)
def test_url(): assert canonical_url('HTTPS://Example.com:443/path/?utm_source=x&b=2&a=1')=='https://example.com/path?a=1&b=2'
def test_resolver():
 r=EntityResolver({'OpenAI':['Open AI','OpenAI, Inc.']}).resolve('OpenAI, Inc.'); assert r.canonical_name=='OpenAI' and r.confidence==1
def test_empty(): assert EntityResolver().resolve('!!!').confidence==0
def test_feed():
 feed=b'''<rss><channel><item><title>New AI model</title><link>https://example.com/a</link><pubDate>Thu, 10 Sep 2026 10:00:00 GMT</pubDate><description>artificial intelligence</description></item></channel></rss>'''; rows=parse_feed(feed,SourceConfig('x','news','x',('ai',)),datetime(2026,9,10,12,tzinfo=timezone.utc)); assert len(rows)==1

def test_hash(): assert sha256_text('a')==sha256_text('a')
