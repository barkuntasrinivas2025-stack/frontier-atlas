from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class SourceProvenance(BaseModel):
    source_url: HttpUrl
    source_name: str
    collected_at: datetime
    content_hash: str | None = None


class Startup(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1)
    description: str | None = None
    website: HttpUrl | None = None
    founded_year: int | None = None
    funding: str | None = None
    source: SourceProvenance


class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = Field(min_length=1)
    description: str | None = None
    website: HttpUrl | None = None
    category: str | None = None
    company_name: str | None = None
    source: SourceProvenance


class ResearchPaper(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1)
    arxiv_id: str | None = None
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    paper_url: HttpUrl
    published_at: datetime | None = None
    github_url: HttpUrl | None = None
    github_stars: int | None = None
    source: SourceProvenance


class Job(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1)
    company: str | None = None
    location: str | None = None
    url: HttpUrl
    description: str | None = None
    published_at: datetime | None = None
    source: SourceProvenance


class NewsArticle(BaseModel):
    model_config = ConfigDict(extra="ignore")
    title: str = Field(min_length=1)
    url: HttpUrl
    summary: str | None = None
    content: str | None = None
    published_at: datetime | None = None
    source: SourceProvenance
