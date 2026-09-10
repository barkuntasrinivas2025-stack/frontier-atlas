from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from urllib.request import Request, urlopen

PWC_URL = "https://huggingface.co/datasets/pwc-archive/links-between-paper-and-code/resolve/main/data/train-00000-of-00001.parquet"
DEFAULT_PATH = Path("data/processed/pwc-links-between-paper-and-code.parquet")


def normalize_arxiv_id(value: str | None) -> str:
    """Normalize ArXiv identifiers for matching PWC's unversioned IDs."""
    if not value:
        return ""
    value = str(value).strip()
    value = value.rsplit("/", 1)[-1]
    if value.lower().endswith(".pdf"):
        value = value[:-4]
    # PWC stores the base id, while ArXiv API URLs often contain v1/v2/etc.
    import re
    value = re.sub(r"v\d+$", "", value, flags=re.IGNORECASE)
    return value


def download_pwc_snapshot(path: Path = DEFAULT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > 1_000_000:
        return path
    request = Request(PWC_URL, headers={"User-Agent": "FrontierAtlas/0.1"})
    with urlopen(request, timeout=120) as response, path.open("wb") as out:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
    return path


@dataclass(frozen=True, slots=True)
class PWCLink:
    paper_arxiv_id: str
    repo_url: str
    is_official: bool = False
    mentioned_in_paper: bool = False
    mentioned_in_github: bool = False


class PWCLinkIndex:
    """Local lookup over the Papers with Code paper/code snapshot."""

    def __init__(self, path: Path = DEFAULT_PATH) -> None:
        self.path = Path(path)
        self._mapping: dict[str, list[PWCLink]] | None = None

    def _ensure_loaded(self) -> None:
        if self._mapping is not None:
            return
        download_pwc_snapshot(self.path)
        import pyarrow.parquet as pq

        table = pq.read_table(
            self.path,
            columns=[
                "paper_arxiv_id",
                "repo_url",
                "is_official",
                "mentioned_in_paper",
                "mentioned_in_github",
            ],
        )
        mapping: dict[str, list[PWCLink]] = {}
        for row in table.to_pylist():
            aid = normalize_arxiv_id(row.get("paper_arxiv_id"))
            repo = str(row.get("repo_url") or "").strip()
            if not aid or not repo:
                continue
            mapping.setdefault(aid, []).append(
                PWCLink(
                    paper_arxiv_id=aid,
                    repo_url=repo,
                    is_official=bool(row.get("is_official")),
                    mentioned_in_paper=bool(row.get("mentioned_in_paper")),
                    mentioned_in_github=bool(row.get("mentioned_in_github")),
                )
            )
        for candidates in mapping.values():
            candidates.sort(
                key=lambda x: (
                    x.is_official,
                    x.mentioned_in_paper,
                    x.mentioned_in_github,
                ),
                reverse=True,
            )
        self._mapping = mapping

    def lookup_all(self, arxiv_id: str) -> list[PWCLink]:
        self._ensure_loaded()
        return list(self._mapping.get(normalize_arxiv_id(arxiv_id), []))

    def lookup(self, arxiv_id: str) -> PWCLink | None:
        candidates = self.lookup_all(arxiv_id)
        return candidates[0] if candidates else None

    def lookup_many(self, arxiv_ids: set[str]) -> dict[str, list[PWCLink]]:
        self._ensure_loaded()
        return {
            aid: list(self._mapping.get(normalize_arxiv_id(aid), []))
            for aid in arxiv_ids
            if normalize_arxiv_id(aid) in self._mapping
        }


def load_repo_map(arxiv_ids: set[str], path: Path = DEFAULT_PATH) -> dict[str, list[dict[str, object]]]:
    index = PWCLinkIndex(path)
    result: dict[str, list[dict[str, object]]] = {}
    for aid, candidates in index.lookup_many(arxiv_ids).items():
        result[aid] = [
            {
                "paper_arxiv_id": c.paper_arxiv_id,
                "repo_url": c.repo_url,
                "is_official": c.is_official,
                "mentioned_in_paper": c.mentioned_in_paper,
                "mentioned_in_github": c.mentioned_in_github,
            }
            for c in candidates
        ]
    return result
