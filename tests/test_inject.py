import subprocess
from pathlib import Path

import pytest

from fireflyer import gitutil, inject


def _init_repo(tmp_path: Path, remote: str | None = "git@github.com:owner/blog.git") -> Path:
    repo = tmp_path / "blog"
    repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q", "-b", "master", str(repo)], check=True)
    if remote is not None:
        subprocess.run(["git", "-C", str(repo), "remote", "add", "origin", remote], check=True)
    return repo


def test_renames_dotfiles_only():
    assert inject.destination(Path("node-version")) == Path(".node-version")
    assert inject.destination(Path("src/content/gitattributes")) == Path("src/content/.gitattributes")
    assert inject.destination(Path("public/admin/config.yml")) == Path("public/admin/config.yml")


def test_render_substitutes_placeholders_in_text_files():
    context = {inject.REPO_PLACEHOLDER: "owner/blog"}
    rendered = inject.render(Path("config.yml"), b"repo: __FIREFLYER_REPO__", context)
    assert rendered == b"repo: owner/blog"


def test_render_leaves_non_templated_files_byte_identical():
    """The multi-megabyte bundle must never be decoded and re-encoded."""
    context = {inject.REPO_PLACEHOLDER: "owner/blog"}
    data = b"\x00\xff__FIREFLYER_REPO__\xfe"
    assert inject.render(Path("sveltia-cms.js"), data, context) == data


def test_context_requires_an_origin_remote(tmp_path):
    repo = _init_repo(tmp_path, remote=None)
    with pytest.raises(RuntimeError, match="origin"):
        inject.build_context(repo)


@pytest.mark.parametrize(
    ("remote", "expected"),
    [
        ("git@github.com:owner/blog.git", "owner/blog"),
        ("https://github.com/owner/blog.git", "owner/blog"),
        ("https://github.com/owner/blog", "owner/blog"),
    ],
)
def test_context_parses_both_remote_styles(tmp_path, remote, expected):
    repo = _init_repo(tmp_path, remote)
    assert inject.build_context(repo) == {inject.REPO_PLACEHOLDER: expected}


def test_all_layer_files_are_written(tmp_path):
    repo = _init_repo(tmp_path)
    assert inject.inject_repository(repo, announce=False) == 0
    destinations = [inject.destination(relative) for relative, _ in inject.iter_layer()]
    assert len(destinations) >= 10
    for destination in destinations:
        assert (repo / destination).is_file()


def test_second_run_changes_nothing(tmp_path):
    repo = _init_repo(tmp_path)
    inject.inject_repository(repo, announce=False)
    changes = inject.plan(repo, inject.build_context(repo))
    assert {change.action for change in changes} == {inject.Action.UNCHANGED}


def test_check_reports_drift_without_writing(tmp_path):
    repo = _init_repo(tmp_path)
    inject.inject_repository(repo, announce=False)
    tampered = repo / "FIREFLYER.md"
    tampered.write_bytes(b"tampered\n")
    assert inject.inject_repository(repo, check=True, announce=False) == 1
    assert tampered.read_bytes() == b"tampered\n"


def test_inject_configures_the_merge_driver(tmp_path):
    """The driver lives in .git/config, so a fresh clone starts without it."""
    repo = _init_repo(tmp_path)
    assert gitutil.has_merge_driver(repo) is False
    inject.inject_repository(repo, announce=False)
    assert gitutil.has_merge_driver(repo) is True


def test_content_directory_carries_the_merge_attribute(tmp_path):
    repo = _init_repo(tmp_path)
    inject.inject_repository(repo, announce=False)
    posts = repo / "src" / "content" / "posts"
    posts.mkdir(parents=True)
    (posts / "x.md").write_text("hi", encoding="utf-8")
    result = subprocess.run(
        ["git", "-C", str(repo), "check-attr", "merge", "src/content/posts/x.md"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip().endswith("merge: ours")


def test_theme_config_directories_are_not_pinned_to_ours(tmp_path):
    """src/config/ must keep accepting upstream's changes."""
    repo = _init_repo(tmp_path)
    inject.inject_repository(repo, announce=False)
    result = subprocess.run(
        ["git", "-C", str(repo), "check-attr", "merge", "src/config/siteConfig.ts"],
        capture_output=True,
        text=True,
        check=True,
    )
    assert "unspecified" in result.stdout


def test_detects_paths_the_blog_repo_ignores(tmp_path):
    """Regression: text-mode stdin on Windows appended \\r to every path, so
    git matched none of them and the warning never fired."""
    repo = _init_repo(tmp_path)
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")

    ignored = gitutil.ignored_paths(repo, [Path("build/out.txt")])
    assert ignored == [Path("build/out.txt")]
    assert gitutil.ignored_paths(repo, [Path("public/admin/index.html")]) == []


def test_rendered_config_points_at_the_origin_remote(tmp_path):
    repo = _init_repo(tmp_path, "git@github.com:someone/my-blog.git")
    inject.inject_repository(repo, announce=False)
    text = (repo / "public" / "admin" / "config.yml").read_text(encoding="utf-8")
    assert "repo: someone/my-blog" in text
    assert inject.REPO_PLACEHOLDER not in text
