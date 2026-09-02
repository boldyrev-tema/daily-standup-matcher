import json

import requests

from meeting import Line
from sprint_snapshot import Task

OPENROUTER_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"
# Tried in order until one succeeds. Empirically measured (31 авг, two 8-call
# batches on this project's real prompt shape): free-tier models on OpenRouter
# are single-provider with no automatic failover, and reliability swings hard
# batch to batch (nemotron-3-super went from 9/10 to 3/8 between two runs on
# the same day - "Service temporarily overloaded"/"Upstream idle timeout").
# nano-omni and nemotron-3-super are both hosted by Nvidia - if Nvidia has a
# bad day both fail together - so minimax-m3 (GMICloud, a different upstream)
# is kept as a genuinely independent fallback, not just a second guess.
#   nemotron-3-nano-omni-30b (reasoning off): 8/8, ~1.8s avg - fastest+most reliable so far
#   minimax-m3:                                8/8, ~2-4s typical (one 37s outlier)
#   nemotron-3-super (reasoning off):          3/8 this batch, 9/10 a batch earlier
MODEL_CHAIN: list[tuple[str, dict]] = [
    ("nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free", {"reasoning": {"enabled": False}}),
    ("minimax/minimax-m3:free", {}),
    ("nvidia/nemotron-3-super-120b-a12b:free", {"reasoning": {"enabled": False}}),
]
LOOKBACK_SECONDS = 90.0

SYSTEM_PROMPT = (
    "Ты помогаешь ведущему дейлика во время встречи. Тебе даны реплики за "
    "обсуждаемый период и карточка задачи, которую сейчас обсуждают.\n\n"
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
    "- Короткие реплики-подтверждения без новой информации по задаче "
    "(например: \"окей\", \"хорошо\", \"жду\", \"понял\", \"ага\", \"ok\") "
    "ПРОПУСКАЙ ПОЛНОСТЬЮ — не создавай для них отдельную строку said и не "
    "приписывай говорящему готовность, согласие или обязательство "
    "что-либо сделать/принять/выполнить. Пример ошибки: из реплики "
    "\"окей, хорошо, жду\" НЕЛЬЗЯ делать строку вида \"готов принять ревью\" "
    "или \"готов ждать результат\" — такой строки просто не должно быть.\n"
    "- В целом: не приписывай реплике намерения, обещания или будущие "
    "результаты, которых в ней нет — только то, что было сказано буквально "
    "или является прямым перефразированием.\n"
    "- Никогда не предлагай действий в Jira — это вне твоей роли."
)


def _task_card(task: Task) -> str:
    parts = [f"Ключ: {task.key}", f"Заголовок: {task.title}", f"Статус: {task.status}"]
    parts.append(f"Исполнитель: {task.assignee}")
    if task.priority:
        parts.append(f"Приоритет: {task.priority}")
    return "\n".join(parts)


def _recent_lines_text(lines: list[Line], now_t: float, lookback_seconds: float | None) -> str:
    if lookback_seconds is None:
        recent = lines
    else:
        recent = [l for l in lines if now_t - l.t <= lookback_seconds]
    return "\n".join(f"{l.who or '?'}: {l.text}" for l in recent)


def _request_hints(payload: dict, api_key: str, timeout: float) -> tuple[list[str], str | None]:
    resp = requests.post(
        OPENROUTER_ENDPOINT,
        headers={"Authorization": f"Bearer {api_key}"},
        json=payload,
        timeout=timeout,
    )
    resp.raise_for_status()
    # OpenRouter can return HTTP 200 with an error body (observed both
    # {"error": {"message": "Upstream idle timeout exceeded", "code": 504}}
    # and {"message": "...Service temporarily overloaded", "code": 502}) when
    # the free model's own backend is struggling — raise_for_status() doesn't
    # catch this, "choices" is simply missing, which raises KeyError below.
    content = resp.json()["choices"][0]["message"]["content"]
    parsed = json.loads(content)
    if not isinstance(parsed, dict):
        return [], None
    said = parsed.get("said", [])
    ask = parsed.get("ask")
    if not isinstance(said, list):
        return [], None
    return said[:3], ask


def get_hints(
    lines: list[Line],
    task: Task,
    api_key: str,
    timeout: float = 6.0,
    lookback_seconds: float | None = LOOKBACK_SECONDS,
) -> tuple[list[str], str | None]:
    if not lines:
        return [], None
    now_t = lines[-1].t
    window_label = "за последние 90с" if lookback_seconds is not None else "за всё обсуждение"
    user_content = (
        f"Карточка задачи:\n{_task_card(task)}\n\n"
        f"Реплики {window_label}:\n{_recent_lines_text(lines, now_t, lookback_seconds)}"
    )
    # Walk the fallback chain instead of retrying the same model — a free
    # model's backend having a bad minute is common enough (see MODEL_CHAIN
    # comment) that a different provider recovers more often than a retry on
    # the same one.
    for model, extra in MODEL_CHAIN:
        payload = {
            "model": model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0,
            **extra,
        }
        try:
            return _request_hints(payload, api_key, timeout)
        except (requests.exceptions.RequestException, KeyError, IndexError, TypeError, json.JSONDecodeError):
            continue
    return [], None
