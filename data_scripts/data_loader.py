import json
import os
from typing import Any


class StreamlitDataLoader:
    def __init__(self, base_path: str):
        self.base_path = base_path
        self.github_catalog_path = os.path.join(
            base_path, "sources", "github-snapshot-2026-10-06", "catalog"
        )

    def load_jsonl(self, file_path: str) -> list[dict[str, Any]]:
        data = []
        if not os.path.exists(file_path):
            return data
        with open(file_path, encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    data.append(json.loads(line))
        return data

    def get_exposed_issues(self) -> list[int]:
        exposure_file = os.path.join(self.base_path, "development_exposure.json")
        with open(exposure_file, encoding="utf-8") as f:
            exposure_data = json.load(f)
            return exposure_data.get("issue_numbers", [])

    def load_and_clean_issues(self) -> list[dict[str, Any]]:
        raw_issues = self.load_jsonl(os.path.join(self.github_catalog_path, "issue_records.jsonl"))
        exposed_issues = self.get_exposed_issues()
        return [issue for issue in raw_issues if issue.get("number") not in exposed_issues]

    def load_and_clean_comments(self) -> dict[int, list[dict[str, Any]]]:
        raw_comments = self.load_jsonl(
            os.path.join(self.github_catalog_path, "comment_records.jsonl")
        )
        cleaned_comments = [
            c for c in raw_comments if not (c.get("is_bot") or c.get("author_type") == "Bot")
        ]
        comments_by_issue = {}
        for comment in cleaned_comments:
            issue_number = comment.get("issue_number")
            if issue_number not in comments_by_issue:
                comments_by_issue[issue_number] = []
            comments_by_issue[issue_number].append(comment)
        return comments_by_issue

    def build_full_issue_context(self) -> list[dict[str, Any]]:
        issues = self.load_and_clean_issues()
        comments_by_issue = self.load_and_clean_comments()
        full_contexts = []
        for issue in issues:
            issue_num = issue["number"]
            issue_comments = sorted(
                comments_by_issue.get(issue_num, []), key=lambda x: x.get("created_at", "")
            )
            full_contexts.append(
                {
                    "issue_number": issue_num,
                    "title": issue["title"],
                    "body": issue["body"],
                    "state": issue["state"],
                    "labels": issue.get("labels", []),
                    "comments": issue_comments,
                    "created_at": issue["created_at"],
                    "html_url": issue["html_url"],
                }
            )
        return full_contexts
