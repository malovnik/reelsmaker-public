# Этап 05: Фронт — дизайн-система и темы

> Статус: ⬜ Не начат
> Родитель: [[PIPELINE-НАВИГАТОР]]
> Проект: **videomaker-рефакторинг**

## Суть этапа

Фундамент для всех UI-чанков 06–08. Здесь рождается дизайн-код видео-сервиса 2026: динамичный как YouTube/Instagram, с тёмной темой по умолчанию + светлой альтернативой, CSS variables, persist, **ни одного клише AI-slop**.

Владелец явно назвал референсы: **YouTube, Instagram**. Работа с видео, большие превью, тёмный фон, яркие thumbnail-карточки, минимум хрома, максимум контента. Не «editorial magazine». Не «brutalist». А «media-heavy studio» с ритмом и энергией.

**Критически:** в каждом чанке этапа 05–08 **обязательно** запускается `frontend-design` skill (Phase 1–2 чеклиста) **до** первой строки кода. Skill проверяет:
- Понимание контекста, пользователя, устройства.
- Выбор конкретного эстетического направления (не «modern and clean»).
- Наличие acent-цвета с контрастом (не всё муть-нейтральное).
- Отказ от AI-slop: generic градиенты, стоковые shadcn-кнопки как есть, фальшивые glassmorphism.

**Режим работы:** Sequential. 7 чанков, каждый завершает один слой системы.

## Подэтапы (REFACTR-32..REFACTR-38)

- **REFACTR-32** — Принципы дизайна: референсы, эстетическое направление, manifest ⬜
- **REFACTR-33** — Палитры: dark (основная) + light (альтернатива), токены ⬜
- **REFACTR-34** — Типографика (Inter Variable, SF Mono для кодов), spacing scale ⬜
- **REFACTR-35** — Атомы: Button, Input, Select, Chip, Badge, Avatar, Icon ⬜
- **REFACTR-36** — Молекулы: Card, Modal, Toast, Tooltip, Popover, Tabs ⬜
- **REFACTR-37** — ThemeProvider + persist (localStorage + backend settings) + переключатель ⬜
- **REFACTR-38** — Motion: микро-транзиции + правила анимаций ⬜

## Вход

- Frontend-стек после миграции (Этап 04).
- Требования владельца: YouTube/Instagram-стиль, dark default + light, persist.
- Skill `frontend-design` (**обязателен в каждом чанке этапа**).

## Выход

- `apps/frontend/src/design/tokens.ts` — все цветовые/spacing/typo токены.
- `apps/frontend/src/design/themes.css` — dark + light CSS variables.
- `apps/frontend/src/design/components/` — атомы и молекулы.
- `apps/frontend/src/design/ThemeProvider.tsx`.
- `apps/frontend/src/design/motion.ts` — утилиты анимаций.
- `docs/design/STYLEGUIDE.md` — руководство + скриншоты.

## Роли пайплайна этапа

- **R-DESIGN-ALCHEMIST** — лидирующая роль (создаётся через `role-factory` если нет).
- **R-MOTION** — подключается на чанке 38.
- **R-UX-WRITER** — проверяет ВСЕ UI-тексты атомов/молекул на русский язык, отсутствие клише.

## GATE-чекпоинт этапа

- [ ] Все 7 чанков завершены, артефакты на месте.
- [ ] Dark и light темы работают на одной странице (демо-странице `/design-preview`).
- [ ] Persist через localStorage + синхронизация с backend (подтверждено: reload → тема сохранена).
- [ ] Типографика, spacing, радиусы — в коде через токены (нет raw `px`/`hex` значений в компонентах).
- [ ] Нет generic shadcn/ui «серых» компонентов — каждый атом имеет визуальную идентичность videomaker.
- [ ] `frontend-design` skill активирован в логе каждого чанка этапа.
