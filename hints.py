import json

import requests

from meeting import Line
from sprint_snapshot import Task

GROQ_ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "openai/gpt-oss-120b"
LOOKBACK_SECONDS = 90.0

SYSTEM_PROMPT = (
    "Ты помогаешь ведущему дейлика во время встречи. Тебе даны реплики за "
    "последние 90 секунд разговора и карточка задачи, которую сейчас "
    "обсуждают.\n\n"
    "Верни СТРОГО JSON-объект вида:\n"
    '{"said": ["строка 1", "строка 2"], "ask": "вопрос" или null}\n\n'
    "Правила:\n"
    "- said — не более 3 строк по 60-90 знаков, каждая ОБЯЗАНА опираться на "
    "конкретную произнесённую реплику. Не пересказывай реплики целиком — "
    "выжимай только суть.\n"
    "- Ничего не выдумывай: если в репликах нет содержательной информации "
    "по задаче — верни пустой список said.\n"
    "- ask — один вопрос ведущему, только если есть явное расхождение между "
    "сказанным и карточкой задачи, или незакрытая договорённость. Если "
    "повода нет — null.\n"
    "- Никогда не предлагай действий в Jira — это вне твоей роли."
)


def _task_card(task: Task) -> str:
    parts = [f"Ключ: {task.key}", f"Заголовок: {task.title}", f"Статус: {task.status}"]
    parts.append(f"Исполнитель: {task.assignee}")
    if task.priority:
        parts.append(f"Приоритет: {task.priority}")
    return "\n".join(parts)


def _recent_lines_text(lines: list[Line], now_t: float) -> str:
    recent = [l for l in lines if now_t - l.t <= LOOKBACK_SECONDS]
    return "\n".join(f"{l.who or '?'}: {l.text}" for l in recent)


def get_hints(
    lines: list[Line], task: Task, api_key: str, timeout: float = 3.0
) -> tuple[list[str], str | None]:
    if not lines:
        return [], None
    now_t = lines[-1].t
    user_content = (
        f"Карточка задачи:\n{_task_card(task)}\n\n"
        f"Реплики за последние 90с:\n{_recent_lines_text(lines, now_t)}"
    )
    payload = {
        "model": GROQ_MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "response_format": {"type": "json_object"},
        "temperature": 0,
    }
    try:
        resp = requests.post(
            GROQ_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=timeout,
        )
        resp.raise_for_status()
        content = resp.json()["choices"][0]["message"]["content"]
        parsed = json.loads(content)
        said = parsed.get("said", [])
        ask = parsed.get("ask")
        if not isinstance(said, list):
            return [], None
        return said[:3], ask
    except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError):
        return [], None
