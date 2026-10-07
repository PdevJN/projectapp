"""タスクのリンク(URL)の規則。置き換え・検証・テンプレートの削除と名前の変更。NiceGUI には依存しない。"""

from dataclasses import dataclass, replace
from urllib.parse import quote

from projectapp.models import ID_KEY, URL_KEY, Project, TaskUrl, UrlTemplate

ALLOWED_SCHEMES = ("http://", "https://")
PLACEHOLDER = "{ID}"
SCHEME_MESSAGE = "URL は http:// か https:// で始めてください"


def has_allowed_scheme(url: str) -> bool:
    return url.lower().startswith(ALLOWED_SCHEMES)


def resolve(link: TaskUrl, templates: list[UrlTemplate]) -> str:
    """開く URL を返す。値が空・テンプレートがない・http(s) でないときは ValueError。"""
    if link.template is None:
        url = link.values.get(URL_KEY, "").strip()
        if not url:
            raise ValueError("URL を入力してください")
    else:
        template = next((t for t in templates if t.name == link.template), None)
        if template is None:
            raise ValueError(f"テンプレート「{link.template}」が見つかりません")
        identifier = link.values.get(ID_KEY, "").strip()
        if not identifier:
            raise ValueError("ID を入力してください")
        url = template.pattern.replace(PLACEHOLDER, quote(identifier, safe=""))
    if not has_allowed_scheme(url):
        raise ValueError(SCHEME_MESSAGE)
    return url


def validate_templates(templates: list[UrlTemplate]) -> None:
    """名前が空・重複、または型が http(s) で始まらないとき ValueError。"""
    seen: set[str] = set()
    for template in templates:
        name = template.name.strip()
        if not name:
            raise ValueError("テンプレートの名前を入力してください")
        if name in seen:
            raise ValueError(f"テンプレート名「{name}」が重複しています")
        seen.add(name)
        if not has_allowed_scheme(template.pattern):
            raise ValueError(f"テンプレート「{name}」の URL の型は http:// か https:// で始めてください")


def validate_urls(urls: list[TaskUrl], templates: list[UrlTemplate]) -> None:
    for link in urls:
        resolve(link, templates)


def count_usage(project: Project, name: str) -> int:
    return sum(link.template == name for task in project.all_tasks() for link in task.urls)


def expand_template(project: Project, name: str) -> int:
    """そのテンプレートを使うリンクを、置き換え済みの URL(テンプレートなし)にする。展開した件数を返す。"""
    count = 0
    for task in project.all_tasks():
        expanded: list[TaskUrl] = []
        for link in task.urls:
            if link.template == name:
                url = resolve(link, project.url_templates)
                link = TaskUrl(link.title, None, {URL_KEY: url})
                count += 1
            expanded.append(link)
        task.urls = expanded
    return count


def rename_templates(project: Project, renames: dict[str, str]) -> None:
    """テンプレート名の変更(元の名前 → 新しい名前)を、リンクの参照へ一度に反映する。入れ替えでも混ざらない。"""
    for task in project.all_tasks():
        task.urls = [
            replace(link, template=renames.get(link.template, link.template))
            if link.template is not None
            else link
            for link in task.urls
        ]


@dataclass(frozen=True)
class TemplateEdit:
    """設定ダイアログでのテンプレートの編集結果。"""

    templates: list[UrlTemplate]  # 編集後の一覧(順序どおり)
    renames: dict[str, str]  # 元の名前 → 新しい名前
    removed: list[str]  # 削除した元の名前


def apply_template_edit(project: Project, edit: TemplateEdit) -> None:
    """削除したテンプレートのリンクを展開し(古い型で)、名前の変更を反映してから、一覧を置き換える。"""
    for name in edit.removed:
        expand_template(project, name)
    rename_templates(project, edit.renames)
    project.url_templates = list(edit.templates)
