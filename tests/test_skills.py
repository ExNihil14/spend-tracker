"""Структурные проверки проектных скиллов (`.opencode/skills/`) — оффлайн, без сети.

Скиллы (bank-adapter / release / verify-spendtrack) — публичный интерфейс агента:
держим механику opencode (SKILL.md, frontmatter, `name` == каталог), обязательную
секцию Gotchas и живые указатели на файлы репо, чтобы знания в них не гнили.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKILLS = ROOT / ".opencode" / "skills"
EXPECTED = ("bank-adapter", "release", "verify-spendtrack")
NAME_RE = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")
FRONTMATTER_RE = re.compile(r"\A---\n(.*?)\n---\n", re.DOTALL)
TOKEN_RE = re.compile(r"`([^`\n]+)`")
PATH_EXT = {".py", ".md", ".toml", ".txt", ".csv", ".sh", ".ps1", ".yml", ".yaml",
            ".json", ".css", ".html", ".db"}


def _read(name: str) -> str:
    return (SKILLS / name / "SKILL.md").read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict[str, str]:
    match = FRONTMATTER_RE.match(text)
    assert match, "нет YAML-frontmatter (--- ... ---)"
    fields: dict[str, str] = {}
    for line in match.group(1).splitlines():
        key, sep, value = line.partition(":")
        if sep and not line.startswith((" ", "\t")):
            fields[key.strip()] = value.strip()
    return fields


def _looks_like_path(token: str) -> bool:
    t = token.strip()
    if not t or any(c in t for c in "*?<>{}|$=\"'"):
        return False
    if t.startswith(("http://", "https://", "-")) or t.endswith(("\\", "/")):
        return False
    if re.match(r"^[A-Za-z]:[\\/]", t):
        return True  # абсолютный Windows-путь (пробелы допустимы)
    if " " in t:
        return False
    if "/" in t or "\\" in t:
        return Path(t).suffix.lower() in PATH_EXT
    return False


def _discovered() -> tuple[str, ...]:
    """Скиллы на диске: новый каталог попадает в проверки автоматически."""
    if not SKILLS.is_dir():
        return ()
    return tuple(sorted(p.name for p in SKILLS.iterdir() if (p / "SKILL.md").is_file()))


def test_expected_skills_present() -> None:
    assert set(EXPECTED) <= set(_discovered()), "ожидаемый скилл пропал/переименован"


@pytest.mark.parametrize("name", _discovered())
def test_skill_frontmatter_and_gotchas(name: str) -> None:
    path = SKILLS / name / "SKILL.md"
    assert path.is_file(), f"нет {path}"
    text = path.read_text(encoding="utf-8")
    meta = _frontmatter(text)
    assert meta.get("name") == name, "name должен совпадать с каталогом"
    assert NAME_RE.match(name), "name: lowercase-слова через один дефис"
    description = meta.get("description", "")
    assert 1 <= len(description) <= 1024, "description: 1..1024 символов"
    assert re.search(r"^#{2,3}\s*Gotchas\b", text, re.MULTILINE), "обязательная секция Gotchas"


@pytest.mark.parametrize("name", _discovered())
def test_skill_pointers_alive(name: str) -> None:
    missing: list[str] = []
    for raw in TOKEN_RE.findall(_read(name)):
        token = raw.strip()
        if not _looks_like_path(token):
            continue
        resolved = Path(token) if re.match(r"^[A-Za-z]:[\\/]", token) else ROOT / token
        if not resolved.exists():
            missing.append(token)
    assert not missing, f"битые указатели: {missing}"
