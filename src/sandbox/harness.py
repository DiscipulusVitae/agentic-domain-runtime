import logging
from dataclasses import dataclass
from src.sandbox.fake_llm import FakeLLMClient
from src.sandbox.contracts import ButlerClassifierService, MedicalEntry

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


class SandboxHarness:
    """
    Harness for run-through smoke flows in local sandbox.
    Uses in-memory fake persistence and FakeLLMClient.
    """
    def __init__(self):
        self.books_db: list[FakeBook] = []
        self.medical_db: list[MedicalEntry] = []
        
        self.books_db_service = FakeBooksService(self.books_db)
        self.medical_db_service = FakeMedicalService(self.medical_db)
        
        self.dp = {
            "books_service": self.books_db_service,
            "medical_service": self.medical_db_service
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
        if not domain_id:
            trace = ["[routing: ambiguous/clarification_needed]"]
            return {
                "routing": result.decision.model_dump(),
                "trace": " -> ".join(trace),
                "success": False,
                "output": result.decision.clarification_question
            }

        # Step 2: Handle domains
        if domain_id == "kitchen":
            trace = [f"[routing: {domain_id}]", "[kitchen: stub — interactive batching not included]"]
            return {
                "routing": result.decision.model_dump(),
                "trace": " -> ".join(trace),
                "success": True,
                "stub": True
            }

        trace = [f"[routing: {domain_id}]"]
        output_lines = []
        persisted = False

        if domain_id == "books":
            # Extract via books client
            fake_books_client = FakeLLMClient(agent_id="books.cataloger")
            response, active_model = await fake_books_client.send_with_fallback(
                chat=None,
                message=text,
                current_model="fake-model",
                history=[]
            )
            book_extraction = response.parsed  # This is BookExtraction
            
            output_lines.append("⏳ Обрабатываю описание книги...")
            output_lines.append("---")
            output_lines.append("[Книги · Томас]")
            
            if book_extraction.ready_to_save:
                await self.books_db_service.create_book(
                    title=book_extraction.title,
                    author=book_extraction.author,
                    description=book_extraction.description,
                    year=book_extraction.year
                )
                persisted = True
                records_count = len(self.books_db)
                trace.append("[extraction: success]")
                trace.append("[validation: success]")
                trace.append(f"[persistence: saved ({records_count} records)]")
                output_lines.append(f"✅ Книга «{book_extraction.title}» успешно сохранена в sandbox!")
                output_lines.append("Для просмотра: /last_book")
            else:
                persisted = False
                trace.append("[extraction: success]")
                trace.append("[validation: failed]")
                trace.append("[persistence: failed]")
                output_lines.append(book_extraction.next_question or "Недостаточно данных для сохранения.")

        elif domain_id == "medical":
            # Extract via medical client
            fake_medical_client = FakeLLMClient(agent_id="medical.recorder")
            response, active_model = await fake_medical_client.send_with_fallback(
                chat=None,
                message=text,
                current_model="fake-model",
                history=[]
            )
            medical_extraction = response.parsed  # This is MedicalExtraction
            
            output_lines.append("⏳ Анализирую медицинские показатели...")
            output_lines.append("---")
            
            if medical_extraction.entries:
                for entry in medical_extraction.entries:
                    self.medical_db.append(entry)
                persisted = True
                records_count = len(self.medical_db)
                trace.append("[extraction: success]")
                trace.append("[validation: success]")
                trace.append(f"[persistence: saved ({records_count} records)]")
                output_lines.append(f"❤️ Запись успешно сохранена в sandbox для субъекта: {medical_extraction.subject_label or 'Не указан'}")
            else:
                persisted = False
                trace.append("[extraction: failed]")
                trace.append("[validation: failed]")
                trace.append("[persistence: failed]")
                output_lines.append(medical_extraction.next_question or "Не удалось извлечь медицинские показатели.")

        return {
            "routing": result.decision.model_dump(),
            "trace": " -> ".join(trace),
            "success": persisted,
            "output": "\n".join(output_lines)
        }
