# REFACTR-32 — Принципы дизайна (референсы, эстетическое направление, manifest)

> **Этап:** 05 — Фронт: дизайн-система и темы
> **Шаг:** 33 из 67
> **Зависимости:** REFACTR-06 (UX-боли), REFACTR-31 (Vite готов).
> **Следующий шаг:** REFACTR-33 (Палитры темы)

**ОБЯЗАТЕЛЬНО:** активировать `frontend-design` skill в начале чанка.

---

## Роли

### R-DESIGN-ALCHEMIST — Дизайн-алхимик
**Профессия:** Senior UI/UX designer-dev с 12+ лет опыта в медиа-продуктах.
**Soul:** Референсы — не плагиат. Это координаты на карте. YouTube Studio и CapCut — наши ориентиры, но у videomaker собственное лицо: инструмент для одного, не социальный продукт.

### R-MOTION (консультативно)
**Soul:** Manifest должен содержать принципы движения. Если в principles нет motion — motion не появится.

### R-UX-WRITER
**Soul:** Manifest на русском. Каждое слово взвешено. «Distinctive» не подходит, «узнаваемое» — да.

---

## ТРИЗ-принцип

*Принцип предварительного действия.* Перед первой линией кода дизайн-системы — сформулировать принципы. Иначе 7 следующих чанков будут писать разный код, подчинённый разным логикам.

---

## Оркестрация

**Режим:** Sequential + `frontend-design` Phase 1.

---

## Микрозадачи

### 32.1 Активация frontend-design skill

- [ ] `Skill: frontend-design`.
- [ ] Пройти Phase 1 (Understand the Context):
  - Product: локальное приложение для нарезки вертикальных видео.
  - User: один человек, owner-operator, привык к CapCut/Premiere/Final Cut.
  - Device: Mac (desktop-heavy), 1366-2560 ширина.
  - Existing: проект уже есть, но весь текущий UI будет заменён (дизайн-система создаётся с нуля).

### 32.2 Референсы — 10 скриншотов

- [ ] YouTube Studio (dashboard, video edit, analytics).
- [ ] CapCut Web (home, editor).
- [ ] DaVinci Resolve (project library).
- [ ] Linear (command palette, list views).
- [ ] Figma (menus, tooltips, floating UI).
- [ ] Sora/Runway (video AI, dark theme media apps).
- [ ] Vercel dashboard (settings organisation).
- [ ] Cursor IDE (dense UI без клаустрофобии).
- [ ] Arc browser (персональность).
- [ ] Raycast (Cmd+K эталон).

Сохранить в `docs/design/references/`. Выписать что берём у каждого (одно-два предложения на референс).

### 32.3 Эстетическое направление

Назвать направление **одной фразой**, не «modern and clean». Варианты для выбора:

- «Studio dark, neon-sparing» — dark dominant, минимум акцентов, они — как кнопка rec на камере, редкие, но без них ничего.
- «Kinetic editorial» — типографика почти журнальная, но с движением.
- «Monolithic tool» — один блок, плотный, как Pro-инструмент.

**Выбор фиксируется в manifest.** Дальше — подчинение ему.

### 32.4 Manifest

`docs/design/MANIFEST.md`:

```markdown
# videomaker — дизайн-манифест

## Одна строка
«Studio-dark инструмент для ремесленника: плотный, но не клаустрофобный; динамичный, но не шумный.»

## Что мы делаем
- Dark тема — дефолт.
- Контент (превью видео, кадры) доминирует, хром минимальный.
- Акцент-цвет один, используется скупо.
- Движение помогает пониманию (не украшает).

## Что мы не делаем
- Generic градиенты.
- Стоковые shadcn-компоненты без доработки.
- Фальшивый glassmorphism.
- "Modern and clean" ощущение — плоско и без лица.
- Эмодзи в UI.
- Клише в текстах кнопок (no "Learn more", no "Get started free").

## Атмосфера
— Студия звукозаписи ночью: чёрно, сфокусировано, только нужное горит.
— CapCut показывает что динамичное видео-приложение может быть лёгким.
— YouTube Studio показывает что инструмент для профессионала не обязан быть Adobe.

## Ключевые референсы
- YouTube Studio — иерархия контента.
- CapCut — скорость и моторика.
- Raycast — Cmd+K и плотность.
- Linear — дисциплина форм и списков.
```

### 32.5 Principles (list)

`docs/design/PRINCIPLES.md`:

- Dark dominant, контент > хром.
- Один акцент-цвет (в REFACTR-33 выберем конкретный).
- Типографика — Inter Variable 100-700 + моноширинный для кодов/ID.
- Spacing 4/8-based.
- Радиусы 6-12 px, не «пузыри».
- Motion 150-250 ms, easing стандартный `cubic-bezier(0.2, 0, 0.2, 1)`.
- Русский язык — обязательно, клише запрещены.

### 32.6 Phase 2 frontend-design

- [ ] Пройти раздел «Visual Impact First»: аccент-цвет подтверждён, палитра проработана в следующем чанке.
- [ ] Пройти раздел «Anti-AI-slop»: проверочный лист — что НЕ делать.

### 32.7 Commit + Serena memory

---

## GATE-чекпоинт

- [ ] `frontend-design` skill активирован.
- [ ] 10 референсов сохранены и прокомментированы.
- [ ] Manifest и Principles написаны (на русском).
- [ ] Эстетическое направление названо одной фразой.
- [ ] Serena memory обновлена.

---

## Артефакт на выходе

`docs/design/MANIFEST.md` + `docs/design/PRINCIPLES.md` + `docs/design/references/` — основа для всех чанков этапа 05-08.
