import pytest
from src.sandbox.harness import SandboxHarness


@pytest.mark.asyncio
async def test_books_flow():
    harness = SandboxHarness()
    
    # Run harness with parsed book metadata
    result = await harness.run_flow("Добавь книгу Война и мир, Лев Толстой, великий роман, 1869")
    
    assert result["success"] is True
    assert result["routing"]["domain_id"] == "books"
    assert "[routing: books]" in result["trace"]
    assert "[extraction: success]" in result["trace"]
    assert "[validation: success]" in result["trace"]
    assert "[persistence: saved" in result["trace"]
    
    # Verify records in in-memory storage
    books_service = harness.dp["books_service"]
    books = await books_service.get_all_books()
    assert len(books) > 0
    
    last_book = books[0]
    assert last_book.title == "Война и мир"
    assert last_book.author == "Лев Толстой"
    assert last_book.year == 1869


@pytest.mark.asyncio
async def test_books_flow_numerical_title():
    harness = SandboxHarness()

    # Run harness with numerical book title
    result = await harness.run_flow("Добавь книгу 1984, Джордж Оруэлл")

    assert result["success"] is True
    assert result["routing"]["domain_id"] == "books"

    books_service = harness.dp["books_service"]
    books = await books_service.get_all_books()
    assert len(books) > 0

    last_book = books[0]
    assert last_book.title == "1984"
    assert last_book.author == "Джордж Оруэлл"
    assert last_book.year is None
