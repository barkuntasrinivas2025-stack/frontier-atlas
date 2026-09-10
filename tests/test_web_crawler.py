from src.crawlers.web import (
    extract_fulltext,
    is_anti_bot_page,
    needs_js_render,
)


def test_extract_fulltext_removes_navigation_and_scripts():
    html = """
    <html>
      <body>
        <nav>Navigation</nav>
        <article>
          <h1>AI News</h1>
          <p>This is the article body.</p>
        </article>
        <script>alert('x')</script>
        <footer>Footer</footer>
      </body>
    </html>
    """

    text = extract_fulltext(html)

    assert "AI News" in text
    assert "This is the article body." in text
    assert "Navigation" not in text
    assert "Footer" not in text
    assert "alert" not in text


def test_antibot_page_is_detected():
    html = """
    <html>
      <body>
        <div>Verify you are human</div>
        <div>Cloudflare</div>
      </body>
    </html>
    """

    assert is_anti_bot_page(html)


def test_normal_article_is_not_antibot():
    html = """
    <article>
      <h1>New AI model released</h1>
      <p>This is normal publisher content.</p>
    </article>
    """

    assert not is_anti_bot_page(html)


def test_js_heavy_page_is_detected():
    html = """
    <html>
      <body>
        <div id="app"></div>
        <script>console.log(1)</script>
        <script>console.log(2)</script>
        <script>console.log(3)</script>
      </body>
    </html>
    """

    assert needs_js_render(html)


def test_content_page_does_not_require_js():
    html = """
    <article>
      <h1>Artificial Intelligence</h1>
      <p>
        This is a sufficiently large server-rendered article body containing
        useful readable information for the crawler.
      </p>
    </article>
    """

    assert not needs_js_render(html)
