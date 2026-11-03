# Протокол AM1 — стійкість типізованих мереж розподіленого адитивного виробництва

**Статус:** попередньо зареєстрований протокол до реалізації та запуску.

**Призначення:** створити новий AM-орієнтований експериментальний блок для статті
`Resilience-Oriented Design of Distributed Additive Manufacturing Networks`, який
не повторює результати статей 1–4 і використовує попередню графово-потокову модель
лише як методологічну основу.

**Базова версія коду:** commit `9225f94d0615eaea4398cc9ec101c44b6f1fea0d`,
tag `v4.0-submission`.

**Ізольована гілка:** `codex/am1-experiment`.

> Повна серія AM1 не запускається до завершення smoke- і calibration-gates та
> окремого підтвердження людини. Наявні модулі, конфігурації й результати серій
> S1–S6, R1–R5, D1–D2, M0–M5 та I1 не редагуються.

---

## 1. Наукове позиціонування

### 1.1. Що вже встановлено в попередніх роботах

Попередні статті встановили:

1. вплив загальної топології, резервування, масштабу й незворотності на
   структурно-функціональну стійкість мереж поставок;
2. цільову крихкість хабових мереж;
3. переваги потоково обізнаного порядку відновлення;
4. достатність локальної видимості та роль координації у багатоагентному
   відновленні.

Ці результати є **prior evidence**. AM1 не повторює їхні факторні плани, не
перевидає їхні таблиці або рисунки й не подає їхні числові значення як нові.

### 1.2. Нова прогалина

Загальні топологічні архетипи не відображають послідовні технологічні стадії
адитивного виробництва, кваліфікаційні обмеження між стадіями та спільні цифрові
залежності. Невідомо, який тип AM-специфічної надлишковості найкраще захищає
нижній хвіст виробничої функціональності за різних механізмів порушення.

### 1.3. Мета

Кількісно оцінити, як кваліфікаційно обмежені маршрути, спільні технологічні
вузькі місця та цифрові залежності впливають на стійкість розподілених мереж
адитивного виробництва, і порівняти AM-специфічні архітектурні втручання за
однакового **структурного**, а не грошового, бюджету.

### 1.4. Дослідницьке питання

> Which AM-specific redundancy mechanism provides the largest improvement in
> lower-tail production-flow resilience under an equal structural intervention
> budget, and how does this ranking depend on the disruption mechanism?

### 1.5. Новий внесок AM1

AM1:

- вводить типізовану багатостадійну AM-мережу;
- моделює qualification-constrained маршрути;
- відокремлює матеріальний потік від цифрових enabling dependencies;
- вводить каскадне блокування AM-вузлів при відмові цифрового сервісу;
- порівнює feedstock, printer-qualification, downstream і digital redundancy;
- використовує парний Monte Carlo дизайн для прямого порівняння архітектур.

---

## 2. Межі дослідження

AM1 є контрольованим синтетичним експериментом, а не моделлю конкретного
підприємства. Модель описує один узагальнений клас деталей і агрегований
виробничий потік. Вона не містить:

- реальних комерційних даних підприємства;
- багатотоварного планування;
- інвентарних політик і lead times;
- економічної вартості втручань;
- геометричної складності деталей;
- технологічного браку або якості поверхні;
- неоднакових тривалостей ремонту й повторної кваліфікації.

Термін **equal budget** у AM1 означає однакову кількість доданих
кваліфікаційних або enabling relations. Він не означає однакову фінансову
вартість.

---

## 3. Типізована AM-мережа

### 3.1. Матеріальний маршрут

Мережа є орієнтованим графом із послідовністю ролей:

`feedstock supplier → preprocessing → AM hub → post-processing → quality assurance → demand`.

Окремі `digital coordination service` вузли не переносять матеріальний потік.
Вони задають enabling dependencies для AM hubs.

### 3.2. Канонічний масштаб AM1-A

Фіксована кількість вузлів `N = 50`:

| Роль | Кількість |
|---|---:|
| Feedstock suppliers | 4 |
| Preprocessing facilities | 6 |
| AM hubs | 20 |
| Post-processing facilities | 6 |
| Quality-assurance facilities | 4 |
| Demand locations | 8 |
| Digital coordination services | 2 |

### 3.3. Перевірка масштабу AM1-B

Вторинна серія чутливості використовує `N = 80`:

| Роль | Кількість |
|---|---:|
| Feedstock suppliers | 6 |
| Preprocessing facilities | 8 |
| AM hubs | 32 |
| Post-processing facilities | 10 |
| Quality-assurance facilities | 6 |
| Demand locations | 16 |
| Digital coordination services | 2 |

AM1-B перевіряє напрям ефектів, а не повну асимптотичну масштабованість.

### 3.4. Генерація і кваліфікаційні обмеження

- Кожний вузол має атрибути `role`, `region` і `qualification_group`.
- Ребро існує лише між суміжними технологічними стадіями.
- Базова мережа гарантує щонайменше один кваліфікований end-to-end маршрут для
  кожного demand-вузла.
- Додаткові ребра означають нову кваліфіковану технологічну сумісність, а не
  довільний зв'язок.
- Capacity задається seed-контрольованим розподілом у межах, специфічних для
  кожної пари стадій.
- Сума базової пропозиції становить `1.2 ×` сумарний базовий попит.
- Усі архітектури одного `paired_run_id` будуються з одного базового графа;
  відрізняється лише набір активованих резервних relations.

### 3.5. Цифрові залежності

- У базовій архітектурі AM hubs залежать від primary digital service.
- Відмова сервісу тимчасово блокує залежні AM hubs, але не позначає їх як
  фізично зруйновані.
- Backup relation дозволяє AM hub залишатися активним, якщо хоча б один його
  digital service доступний.
- Після відновлення сервісу каскадно заблоковані AM hubs повертаються без
  окремого фізичного ремонту.

---

## 4. Архітектурні варіанти

Для `N = 50` структурний бюджет дорівнює `B = 8` доданих relations; для
`N = 80` — `B = 12`. Вузли однакові в усіх варіантах; змінюється лише
активований набір relations.

| Код | Архітектура | Використання бюджету |
|---|---|---|
| `A0_baseline` | Базова AM-мережа | Без додаткових relations; контроль |
| `A1_feedstock` | Feedstock diversification | Додаткові supplier→preprocessing qualifications |
| `A2_cross_qualification` | Printer/material cross-qualification | Додаткові preprocessing→AM qualifications |
| `A3_downstream` | Downstream redundancy | Додаткові AM→post-processing та post-processing→QA relations |
| `A4_digital` | Digital backup | Додаткові backup-service→AM enabling dependencies |
| `A5_balanced` | Balanced portfolio | Бюджет порівну розподілений між чотирма типами relations |

`A0_baseline` не входить до порівняння рівності бюджету; він є нульовою точкою
для оцінювання приросту. Варіанти A1–A5 мають однаковий структурний бюджет.

---

## 5. Сценарії порушень

Порівняння архітектур виконується **всередині кожного сценарію**. Ранги між
різними сценаріями не трактуються як пряме порівняння тяжкості, оскільки
механізми пошкодження різні.

| Код | Сценарій | Правило |
|---|---|---|
| `D1_printer_random` | Випадкові відмови AM hubs | Fixed budget: 20% AM hubs |
| `D2_feedstock_targeted` | Втрата критичного джерела сировини | Supplier із найбільшим базовим flow impact |
| `D3_postprocess_targeted` | Втрата downstream bottleneck | Post-processing node із найбільшим базовим flow impact |
| `D4_digital_outage` | Відмова primary digital service | Каскадне блокування залежних AM hubs без backup relation |
| `D5_regional_cluster` | Регіональний інцидент | Відмова фізичних вузлів однієї seed-визначеної region |

Для кожного прогону записуються фактична кількість фізично пошкоджених,
каскадно заблокованих і функціонально втрачених вузлів.

---

## 6. Відновлення

- Одна repair action на дискретний крок (`mu = 1`).
- Горизонт `T = 50`; calibration перевіряє достатність горизонту.
- Єдина основна політика — `flow_greedy_am`: на кожному кроці обирає repairable
  physical або digital element, відновлення якого дає найбільший поточний
  приріст material max flow з урахуванням digital dependencies.
- Tie-break є детермінованим за стабільним node identifier.
- Random recovery дозволяється лише як secondary calibration benchmark і не є
  центральним фактором AM1.

Такий дизайн навмисно фіксує політику відновлення: AM1 досліджує AM-архітектуру
й механізм порушення, а не повторює порівняння recovery strategies зі статті 3.

---

## 7. Метрики

### 7.1. Первинна метрика

`rho_CVaR_0.10` — середнє інтегральної стійкості в найгірших 10% прогонів.

Основний ефект для архітектури `Ai` у сценарії `Dj`:

`Delta_CVaR(Ai, Dj) = rho_CVaR(Ai, Dj) - rho_CVaR(A0, Dj)`.

### 7.2. Вторинні метрики

- median integral resilience;
- bootstrap 95% CI;
- immediate robustness;
- final recovery level;
- non-recovered share;
- initial maximum flow `F0`;
- minimum normalized performance;
- number of physically failed nodes;
- number of dependency-blocked AM hubs;
- time to 95% functional recovery.

### 7.3. Робастна maximin-оцінка

Для кожної архітектури обчислюється мінімальний приріст CVaR серед п'яти
сценаріїв. Це secondary metric для перевірки, чи balanced portfolio забезпечує
кращу міжсценарну робастність, навіть якщо не є найкращим у кожному окремому
сценарії.

---

## 8. Гіпотези

Гіпотези задають напрям аналізу, але нульові або протилежні результати
зберігаються й повідомляються без зміни протоколу.

### H1 — scenario alignment

Архітектурне втручання, безпосередньо пов'язане з механізмом порушення,
матиме найбільший `Delta_CVaR` у відповідному сценарії:

- A1 у D2;
- A3 у D3;
- A4 у D4.

### H2 — balanced maximin resilience

A5 матиме найкращий або статистично еквівалентний найкращому мінімальний
`Delta_CVaR` серед усіх сценаріїв.

### H3 — dependency specificity

Надлишковість, яка не обходить уражену спільну залежність, матиме малий
нижньохвостовий ефект навіть за однакового структурного бюджету.

### H4 — directional scale stability

Знак основних paired `Delta_CVaR` для N=50 збережеться в AM1-B при N=80.

---

## 9. Monte Carlo дизайн

### 9.1. Парність

Один `paired_run_id` фіксує:

- базовий graph seed;
- capacity seed;
- region assignment;
- disruption seed;
- цільове місце порушення.

У межах `paired_run_id` запускаються всі A0–A5. Це ізолює ефект
архітектурного втручання від випадкової різниці мереж і пошкоджень.

### 9.2. Етапи

1. **Unit tests:** без Monte Carlo.
2. **Smoke:** `M = 5` на одну канонічну комбінацію.
3. **Calibration:** `M = 30` для всіх A×D при N=50.
4. **AM1-A:** `M = 400` paired runs на кожний сценарій при N=50.
5. **AM1-B:** `M = 100` paired runs на кожний сценарій при N=80.

Повний план: `6 architectures × 5 disruptions × 400 = 12,000` запусків для
AM1-A та `3,000` запусків для AM1-B.

### 9.3. Seed namespaces

- smoke: `910000–910099`;
- calibration: `911000–911999`;
- AM1-A: `920000–929999`;
- AM1-B: `930000–939999`.

Ці діапазони не перетинаються з попередніми серіями.

---

## 10. Статистичний аналіз

- Paired bootstrap різниці CVaR, `B = 2000`.
- Paired median difference для per-run integral resilience.
- Wilcoxon signed-rank як secondary test.
- Holm correction усередині кожного disruption scenario.
- Rank-biserial effect size для парних порівнянь.
- Частка non-recovered: paired binary comparison і bootstrap різниці часток.
- H4: порівняння знаків ефекту та Spearman correlation рейтингів A1–A5 між
  N=50 і N=80.

Статистична значущість не замінює практичну: разом повідомляються point
estimate, 95% CI й effect size.

---

## 11. Output schema

### 11.1. Raw results

Кожний рядок відповідає одному `architecture × disruption × paired_run_id` і
містить щонайменше:

- `series`, `scale`, `architecture`, `disruption`, `paired_run_id`;
- усі seeds;
- role counts і intervention budget;
- `F0`, `rho`, `robustness`, `final_recovery`, `t95`;
- physical failures, blocked hubs, repaired elements;
- validity flag та exclusion reason;
- runtime;
- git commit і config hash.

Q(t) зберігається окремо з ключем `paired_run_id`.

### 11.2. Ізольовані outputs

- `results/raw/am1/`;
- `results/aggregated/am1/`;
- `results/figures/am1/`;
- `results/reports/am1/`.

Жодний AM1 runner не має права писати у каталоги попередніх серій.

---

## 12. Захист попередніх статей і дисертації

### 12.1. Дозволені зміни

До завершення AM1 дозволено лише нові файли:

- `am1_main.py`;
- `config/series_AM1.yaml`;
- `src/am1/**`;
- `tests/am1/**`;
- `docs/Protocol_AM1_distributed_additive_manufacturing.md`;
- AM1 outputs у власних каталогах.

Наявні файли `src/network/**`, `src/disruptions/**`, `src/recovery/**`,
`src/experiments/**`, `src/analysis/**`, `config/series_S*.yaml`,
`config/series_R*.yaml`, `config/series_M*.yaml` і `main.py` не редагуються.

### 12.2. Regression gates

Перед і після кожного етапу:

1. `git diff --name-status v4.0-submission` містить лише дозволені AM1 paths.
2. Повний наявний набір тестів: `288 passed` або більше без нових failures.
3. `tests/regression/test_article1_unchanged.py` — PASS.
4. SHA-256 маніфест канонічних попередніх results не змінюється.
5. AM1 smoke outputs пишуться лише у тимчасовий або AM1-каталог.

Контрольна SHA-256 сума попередніх results на момент реєстрації протоколу:

`6444295c58495afd3e6a4d33868de776f9a88e948ccfbffb3a93b1e519197891`.

### 12.3. Відновлюваність

Оригінальна версія завжди доступна через tag `v4.0-submission`. Основний
репозиторій і гілка `main` не використовуються для реалізації AM1.

---

## 13. Implementation stages

### Stage A — model and unit tests

- `src/am1/network.py`;
- `src/am1/dependencies.py`;
- `src/am1/disruptions.py`;
- unit tests структури, кваліфікацій і цифрового failover.

**Gate:** старі 288 tests PASS; нові AM1 unit tests PASS.

### Stage B — recovery and runner

- `src/am1/recovery.py`;
- `src/am1/runner.py`;
- `config/series_AM1.yaml`;
- `am1_main.py`.

**Gate:** deterministic smoke M=5; outputs лише в temp/AM1 namespace.

### Stage C — calibration

- M=30 для всього N=50 factorial plan;
- перевірка invalid share, T=50, saturation, paired integrity і runtime;
- до повного запуску допускаються лише параметричні корекції, описані у
  calibration report.

### Stage D — full simulations

- AM1-A M=400;
- AM1-B M=100;
- raw outputs після запуску не переписуються; повторний запуск отримує окремий
  timestamped namespace.

### Stage E — analysis and manuscript integration

- statistical report;
- нові AM1 tables and figures;
- оновлення рукопису;
- point-by-point response редактору;
- перевірка змістового перекриття зі статтями 1–4.

---

## 14. Stop conditions

Робота зупиняється до рішення людини, якщо:

- будь-який старий regression test перестає проходити;
- змінено файл поза AM1 allowlist;
- змінилася контрольна сума старих results;
- invalid run share перевищує 5% у будь-якій комірці;
- AM1 generator не гарантує end-to-end flow до disruption;
- парність seeds/targets порушена;
- calibration показує, що T=50 недостатній для більшості recoverable runs;
- реалізація потребує зміни математичного змісту попередніх статей.

---

## 15. Правила наукової доброчесності

- Не підбирати параметри для отримання бажаного рангу архітектур.
- Не вилучати валідні adverse runs через небажаний результат.
- Усі exclusions задаються до повної серії та логуються.
- Нульові й негативні ефекти повідомляються.
- Старі результати цитуються як prior work, а не як нові AM1 findings.
- Synthetic assumptions явно зазначаються в статті.
- Формулювання `equal structural intervention budget` не замінюється на
  `equal cost` без емпіричних економічних даних.
