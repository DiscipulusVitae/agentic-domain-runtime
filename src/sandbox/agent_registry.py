from dataclasses import dataclass
from typing import Optional

@dataclass
class AgentInfo:
    agent_id: str
    display_name: str
    description: str

AGENT_REGISTRY = {
    "core.butler": AgentInfo(
        agent_id="core.butler",
        display_name="Дворецкий",
        description="Классификация и маршрутизация входящих сообщений"
    ),
    "kitchen.recorder": AgentInfo(
        agent_id="kitchen.recorder",
        display_name="Кулинарный ассистент",
        description="Разбор, уточнение и сохранение рецептов"
    ),
    "books.librarian": AgentInfo(
        agent_id="books.librarian",
        description="Каталогизация книг и ведение прогресса чтения",
        display_name="Библиотекарь"
    ),
    "health.recorder": AgentInfo(
        agent_id="health.recorder",
        description="Ведение журнала показателей здоровья и симптомов",
        display_name="Ассистент здоровья"
    )
}
