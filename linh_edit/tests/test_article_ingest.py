from linh_edit.article_ingest import ArticleData, apply_article, article_scenes, parse_article_html
from linh_edit.project import ProjectState


def test_article_html_parser_extracts_title_description_paragraphs_and_images():
    html = """
    <html>
      <head>
        <title>Tiêu đề dự phòng</title>
        <meta property="og:title" content="Tiêu đề chính">
        <meta name="description" content="Mô tả ngắn của bài viết">
        <meta property="og:image" content="/hero.jpg">
      </head>
      <body>
        <article>
          <p>Đây là đoạn nội dung thứ nhất đủ dài để trở thành một cảnh trong video.</p>
          <p>Đây là đoạn nội dung thứ hai với thêm dữ kiện để kể tiếp câu chuyện.</p>
          <img src="/inside.jpg">
        </article>
      </body>
    </html>
    """
    article = parse_article_html(html, "https://example.com/news/item")

    assert article.title == "Tiêu đề chính"
    assert article.description == "Mô tả ngắn của bài viết"
    assert len(article.paragraphs) == 2
    assert article.image_urls[0] == "https://example.com/hero.jpg"
    assert "https://example.com/inside.jpg" in article.image_urls


def test_article_storyboard_is_source_grounded_and_bounded():
    article = ArticleData(
        url="https://example.com/a",
        title="Một tiêu đề bài viết",
        description="Mô tả bài viết dùng làm cảnh mở đầu.",
        paragraphs=tuple(
            f"Đoạn số {index} cung cấp dữ kiện nguồn cho câu chuyện đang được biên tập."
            for index in range(1, 15)
        ),
        image_urls=(),
        local_images=("one.jpg", "two.jpg"),
    )
    scenes = article_scenes(article, target_scenes=7)

    assert 4 <= len(scenes) <= 10
    assert scenes[0].title == article.title
    assert all(scene.voice_text in article.source_text for scene in scenes)


def test_apply_article_routes_into_unified_news_editor():
    article = ArticleData(
        url="https://example.com/a",
        title="Tiêu đề từ URL",
        description="Đoạn mô tả nguồn cho video.",
        paragraphs=(
            "Đây là đoạn thứ nhất có đủ thông tin để làm cảnh.",
            "Đây là đoạn thứ hai giúp mở rộng câu chuyện.",
            "Đây là đoạn thứ ba để kết thúc câu chuyện.",
            "Đây là đoạn thứ tư bổ sung thêm bối cảnh.",
        ),
        image_urls=("https://example.com/one.jpg",),
        local_images=("C:/tmp/one.jpg",),
    )
    project = ProjectState(target_seconds=50)

    apply_article(project, article, total_seconds=36)

    assert project.profile == "EXPLAINER_NEWS"
    assert project.source_mode == "ARTICLE_URL"
    assert project.source_url == article.url
    assert project.title == article.title
    assert project.target_seconds == 36.0
    assert project.story_scenes
