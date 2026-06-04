import logging
from dataclasses import dataclass
from src.sandbox.fake_llm import FakeLLMClient
from src.sandbox.contracts import ButlerClassifierService, MedicalEntry
from src.sandbox.agent_registry import AGENT_REGISTRY
from src.sandbox.core import FlowResult, TraceHelper, OutputBuilder

logger = logging.getLogger(__name__)


@dataclass
class FakeBook:
    title: str
    author: str
    description: str | None = None
    year: int | None = None


class FakeBooksService:
    def __init__(self, db_list: list[FakeBook]):
        self.db_list = db_list

    async def get_all_books(self) -> list[FakeBook]:
        return self.db_list

    async def create_book(self, title: str, author: str, description: str | None = None, year: int | None = None):
        book = FakeBook(title=title, author=author, description=description, year=year)
        self.db_list.append(book)
        return book


class FakeMedicalService:
    def __init__(self, db_list: list[MedicalEntry]):
        self.db_list = db_list

    async def get_recent_entries(self, limit: int = 100) -> list[MedicalEntry]:
        return list(reversed(self.db_list))[:limit]


@dataclass
class FakeRecipe:
    title: str
    ingredients: list[str] | None = None
    instructions: str | None = None


class FakeKitchenService:
    def __init__(self, db_list: list[FakeRecipe]):
        self.db_list = db_list

    async def get_all_recipes(self) -> list[FakeRecipe]:
        return self.db_list

    async def create_recipe(self, title: str, ingredients: list[str] | None = None, instructions: str | None = None):
        recipe = FakeRecipe(title=title, ingredients=ingredients, instructions=instructions)
        self.db_list.append(recipe)
        return recipe


class SandboxHarness:
    """
    Harness for run-through smoke flows in local sandbox.
    Uses in-memory fake persistence and FakeLLMClient.
    """
    def __init__(self):
        self.books_db: list[FakeBook] = []
        self.medical_db: list[MedicalEntry] = []
        self.kitchen_db: list[FakeRecipe] = []
        
        self.books_db_service = FakeBooksService(self.books_db)
        self.medical_db_service = FakeMedicalService(self.medical_db)
        self.kitchen_db_service = FakeKitchenService(self.kitchen_db)
        
        self.dp = {
            "books_service": self.books_db_service,
            "medical_service": self.medical_db_service,
            "kitchen_service": self.kitchen_db_service
        }

    async def run_flow(self, text: str) -> dict:
        """
        Runs full smoke flow offline:
        butler -> simulated domain entrypoint -> mock extract/validate -> mock save
        """
        # Step 1: Routing via ButlerClassifierService
        fake_butler_client = FakeLLMClient(agent_id="core.butler")
        classifier = ButlerClassifierService(llm_client=fake_butler_client)
        result = await classifier.classify(text, "text")
        
        domain_id = result.domain
        trace_helper = TraceHelper()
        if not domain_id:
            trace_helper.add_routing(None)
            return FlowResult(
                routing=result.decision.model_dump(),
                trace=trace_helper.build(),
                success=False,
                output=result.decision.clarification_question,
                include_display_name=False
            ).to_dict()

        # Step 2: Handle domains
        trace_helper.add_routing(domain_id)
        output_builder = OutputBuilder()
        persisted = False

        if domain_id == "kitchen":
            # Extract via kitchen client
            fake_kitchen_client = FakeLLMClient(agent_id="kitchen.recorder")
            response, active_model = await fake_kitchen_client.send_with_fallback(
                chat=None,
                message=text,
                current_model="fake-model",
                history=[]
            )
            recipe_extraction = response.parsed  # This is RecipeDraft
            
            display_name = AGENT_REGISTRY["kitchen.recorder"].display_name
            output_builder.add_header("⏳ Анализирую рецепт...", display_name)
            
            if recipe_extraction.ready_to_save:
                await self.kitchen_db_service.create_recipe(
                    title=recipe_extraction.title,
                    ingredients=recipe_extraction.ingredients,
                    instructions=recipe_extraction.instructions
                )
                persisted = True
                records_count = len(self.kitchen_db)
                trace_helper.add_flow_steps(
                    extraction=True, validation=True, persistence=True, records_count=records_count
                )
                output_builder.add_line(f"✅ Рецепт «{recipe_extraction.title}» успешно сохранен в sandbox!")
            else:
                persisted = False
                trace_helper.add_flow_steps(
                    extraction=True, validation=False, persistence=False
                )
                output_builder.add_line(recipe_extraction.next_question or "Недостаточно данных для сохранения.")

        elif domain_id == "books":
            # Extract via books client
            fake_books_client = FakeLLMClient(agent_id="books.librarian")
            response, active_model = await fake_books_client.send_with_fallback(
                chat=None,
                message=text,
                current_model="fake-model",
                history=[]
            )
            book_extraction = response.parsed  # This is BookExtraction
            
            display_name = AGENT_REGISTRY["books.librarian"].display_name
            output_builder.add_header("⏳ Обрабатываю описание книги...", display_name)
            
            if book_extraction.ready_to_save:
                await self.books_db_service.create_book(
                    title=book_extraction.title,
                    author=book_extraction.author,
                    description=book_extraction.description,
                    year=book_extraction.year
                )
                persisted = True
                records_count = len(self.books_db)
                trace_helper.add_flow_steps(
                    extraction=True, validation=True, persistence=True, records_count=records_count
                )
                output_builder.add_line(f"✅ Книга «{book_extraction.title}» успешно сохранена в sandbox!")
                output_builder.add_line("Для просмотра: /last_book")
            else:
                persisted = False
                trace_helper.add_flow_steps(
                    extraction=True, validation=False, persistence=False
                )
                output_builder.add_line(book_extraction.next_question or "Недостаточно данных для сохранения.")

        elif domain_id == "medical":
            # Extract via medical client
            fake_medical_client = FakeLLMClient(agent_id="health.recorder")
            response, active_model = await fake_medical_client.send_with_fallback(
                chat=None,
                message=text,
                current_model="fake-model",
                history=[]
            )
            medical_extraction = response.parsed  # This is MedicalExtraction
            
            display_name = AGENT_REGISTRY["health.recorder"].display_name
            output_builder.add_header("⏳ Анализирую медицинские показатели...", display_name)
            
            if medical_extraction.entries:
                for entry in medical_extraction.entries:
                    self.medical_db.append(entry)
                persisted = True
                records_count = len(self.medical_db)
                trace_helper.add_flow_steps(
                    extraction=True, validation=True, persistence=True, records_count=records_count
                )
                output_builder.add_line(f"❤️ Запись успешно сохранена в sandbox для субъекта: {medical_extraction.subject_label or 'Не указан'}")
            else:
                persisted = False
                trace_helper.add_flow_steps(
                    extraction=False, validation=False, persistence=False
                )
                output_builder.add_line(medical_extraction.next_question or "Не удалось извлечь медицинские показатели.")

        agent_id = result.decision.agent_id
        display_name = AGENT_REGISTRY[agent_id].display_name if agent_id in AGENT_REGISTRY else None

        return FlowResult(
            routing=result.decision.model_dump(),
            trace=trace_helper.build(),
            success=persisted,
            output=output_builder.build(),
            display_name=display_name,
            include_display_name=True
        ).to_dict()
