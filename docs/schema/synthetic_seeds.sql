-- =========================================================================
-- SYNTHETIC DATA SEEDS
-- =========================================================================
-- Location: docs/public/schema/synthetic_seeds.sql
--
-- IMPORTANT NOTICE:
-- These data inserts are completely synthetic, designed for offline demo
-- validation and logical structure verification. They contain no real-life
-- family info, secrets, or actual bot tokens.
-- =========================================================================

-- Clean up any existing data in conceptual model
TRUNCATE TABLE "api"."request_logs" CASCADE;
TRUNCATE TABLE "api"."token_scopes" CASCADE;
TRUNCATE TABLE "med"."medical_entries" CASCADE;
TRUNCATE TABLE "books"."reading_sessions" CASCADE;
TRUNCATE TABLE "books"."notes" CASCADE;
TRUNCATE TABLE "books"."books" CASCADE;
TRUNCATE TABLE "books"."authors" CASCADE;
TRUNCATE TABLE "kitchen"."dishes" CASCADE;
TRUNCATE TABLE "core"."telegram_chat_audit" CASCADE;
TRUNCATE TABLE "core"."runtime_app_sessions" CASCADE;
TRUNCATE TABLE "core"."app_users" CASCADE;
TRUNCATE TABLE "core"."persons" CASCADE;

-- -----------------------------------------------------
-- 1. Seed Core Identity Data
-- -----------------------------------------------------
INSERT INTO "core"."persons" ("id", "person_key", "display_name", "first_name", "last_name") VALUES
(1, 'member_alpha', 'Алексей (Семья)', 'Алексей', 'Иванов'),
(2, 'member_beta', 'Елена (Семья)', 'Елена', 'Иванова');

-- 990001 and 990002 are synthetic Telegram IDs for unit tests/sandbox
INSERT INTO "core"."app_users" ("id", "telegram_user_id", "person_id", "display_name", "is_active") VALUES
(10, 990001, 1, 'Алексей Ivanov', true),
(20, 990002, 2, 'Елена Ivanova', true);

INSERT INTO "core"."runtime_app_sessions" ("telegram_user_id", "current_state", "state_data") VALUES
(990001, 'main_menu', '{"last_action": "check_recipes", "selected_domain": "kitchen"}'::jsonb),
(990002, 'waiting_for_metrics', '{"selected_subject": "self", "pending_metric": "blood_pressure"}'::jsonb);

INSERT INTO "core"."telegram_chat_audit" ("telegram_user_id", "direction", "message_type", "intent_detected") VALUES
(990001, 'inbound', 'text', 'kitchen.recipe.save'),
(990001, 'outbound', 'text', 'core.ask_clarification'),
(990002, 'inbound', 'text', 'medical.log.pressure');


-- -----------------------------------------------------
-- 2. Seed Kitchen/Recipes Data
-- -----------------------------------------------------
INSERT INTO "kitchen"."dishes" ("id", "user_id", "title", "recipe", "photo_main", "photo_main_thumb", "photo_main_hash", "rating", "tags") VALUES
(100, 10, 'Классический луковый суп', '1. Нарезать лук полукольцами.\n2. Пассировать в сливочном масле на медленном огне 40 минут до карамелизации.\n3. Добавить бульон, довести до кипения.\n4. Подавать с гренками и тертым сыром.', 'attachments/kitchen/onion_soup_main.webp', 'attachments/kitchen/onion_soup_thumb.webp', 'sha256_soup_fake_hash', 9, ARRAY['супы', 'французская кухня']),
(200, 20, 'Овсяные оладьи с яблоком', '1. Измельчить овсяные хлопья.\n2. Смешать с кефиром, яйцом и тертым яблоком.\n3. Выпекать на антипригарной сковороде без масла.', 'attachments/kitchen/oat_pancakes.webp', NULL, NULL, 8, ARRAY['завтраки', 'полезное']);


-- -----------------------------------------------------
-- 3. Seed Books Library Data
-- -----------------------------------------------------
INSERT INTO "books"."authors" ("id", "name", "bio", "notes", "personal_rating") VALUES
(1000, 'Виктор Классик', 'Синтетический писатель классического жанра.', 'Вымышленные романы.', 10),
(2000, 'Артур Дистопик', 'Синтетический писатель-фантаст.', 'Антиутопии и научная фантастика.', 9);

INSERT INTO "books"."books" ("id", "title", "author_id", "isbn_13", "description", "page_count", "published_year", "language", "impression") VALUES
(10100, 'Хроники Зеленого Архива (Часть 1)', 1000, NULL, 'Эпическая сага Виктора Классика о вымышленном Зеленом Архиве.', 360, 1869, 'ru', 'Глубокий сюжет и проработка мира.'),
(20200, '2094', 2000, NULL, 'Фантастический роман о технологиях будущего.', 320, 2094, 'ru', 'Интригующий взгляд на развитие синтетического интеллекта.');

INSERT INTO "books"."notes" ("id", "book_id", "content", "source") VALUES
(50, 10100, 'История Зеленого Архива закладывает основы сюжета.', 'manual'),
(60, 20200, 'Синтетические концепты общества будущего.', 'agent_extraction');

INSERT INTO "books"."reading_sessions" ("book_id", "status", "started_at", "finished_at", "progress_percent", "rating") VALUES
(10100, 'reading', '2026-05-10', NULL, 45, NULL),
(20200, 'finished', '2026-04-01', '2026-04-15', 100, 10);


-- -----------------------------------------------------
-- 4. Seed Medical Logs Data
-- -----------------------------------------------------
INSERT INTO "med"."medical_entries" ("created_by_user_id", "subject_person_id", "metric_type", "systolic", "diastolic", "pulse", "glucose_value", "glucose_unit", "glucose_context", "note_text", "raw_text", "measured_at", "status") VALUES
(10, 1, 'blood_pressure', 120, 80, 72, NULL, NULL, NULL, 'Измерено в спокойном состоянии утром.', 'Давление 120 на 80 пульс 72', '2026-06-01 08:30:00+03', 'confirmed'),
(20, 2, 'glucose', NULL, NULL, NULL, 5.4, 'mmol/L', 'fasting', 'Сахар натощак в норме.', 'сахар 5.4', '2026-06-01 07:15:00+03', 'confirmed'),
(10, 2, 'note', NULL, NULL, NULL, NULL, NULL, NULL, 'Повышенная утомляемость к вечеру.', 'Чувствую усталость', '2026-05-31 21:00:00+03', 'needs_review');


-- -----------------------------------------------------
-- 5. Seed API Access Data
-- -----------------------------------------------------
INSERT INTO "api"."token_scopes" ("id", "app_name", "scopes", "is_active") VALUES
(1, 'external_home_dashboard', ARRAY['recipes:read', 'books:read'], true),
(2, 'health_sync_agent', ARRAY['health:write'], true);

INSERT INTO "api"."request_logs" ("token_id", "endpoint", "method", "status_code", "response_time_ms", "ip_address") VALUES
(1, '/api/recipes', 'GET', 200, 12, '192.168.1.50'),
(2, '/api/health/metrics', 'POST', 201, 45, '127.0.0.1');
