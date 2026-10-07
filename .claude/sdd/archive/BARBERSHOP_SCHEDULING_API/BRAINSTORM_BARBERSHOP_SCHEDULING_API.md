# BRAINSTORM: Barbershop Scheduling API

> Exploratory session to clarify intent and approach before requirements capture

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | BARBERSHOP_SCHEDULING_API |
| **Date** | 2026-10-06 |
| **Author** | brainstorm-agent |
| **Status** | ✅ Complete (Defined) |

---

## Initial Idea

**Raw Input:** API Web (backend) em FastAPI ou Flask para gerenciar agendamentos de serviços de barbearias. Expõe rotas HTTP para cadastro de clientes, prestadores de serviço e horários disponíveis. O cliente cria um agendamento; a API valida a disponibilidade do profissional (evitando choque de horários), registra no banco e aciona uma rotina simulada de notificação por e-mail com a confirmação e as informações. Pode servir de backend para uma aplicação web/mobile.

**Context Gathered:**
- Workspace vazio (greenfield): sem código, sem CLAUDE.md, sem repositório git.
- Nenhum padrão existente no código para reaproveitar.
- KB do AgentSpec tem padrões de Python, Pydantic e testes (sem padrões de Flask).

**Technical Context Observed (for Define):**

| Aspect | Observation | Implication |
|--------|-------------|-------------|
| Likely Location | `app/` (código) e `tests/` na raiz do projeto | Projeto Python único, sem monorepo |
| Relevant KB Domains | python, pydantic, testing | Consultar clean-architecture, validators/extraction-schema e unit/integration tests |
| IaC Patterns | N/A | Sem infraestrutura no MVP (SQLite local) |

---

## Discovery Questions & Answers

| # | Question | Answer | Impact |
|---|----------|--------|--------|
| 1 | Qual é o objetivo principal? | Projeto de portfólio/estudo | Prioriza clareza, testes e qualidade de código sobre recursos de produção |
| 2 | Quem são os usuários modelados no MVP? | Cliente + Barbeiro, sem login | Sem autenticação nem papéis; foco na regra de agendamento |
| 3 | Qual banco e ambiente? | SQLite local + SQLAlchemy | Zero configuração; trocar para Postgres depois exige só mudar a URL |
| 4 | Qual o critério de sucesso do MVP? | Testes pytest, docs OpenAPI navegáveis e README | Requisitos de qualidade e documentação entram como metas; conflito de horário e e-mail simulado seguem como requisitos funcionais da descrição original |

---

## Sample Data Inventory

| Type | Location | Count | Notes |
|------|----------|-------|-------|
| Input files | N/A | 0 | Nenhum fornecido |
| Output examples | N/A | 0 | Nenhum fornecido |
| Ground truth | N/A | 0 | Nenhum fornecido |
| Related code | N/A | 0 | Workspace vazio |

**How samples will be used:**

- O usuário não tem material; os exemplos de barbeiros, serviços, disponibilidades e agendamentos serão definidos na fase Define.
- Esses exemplos servirão como fixtures de teste e como exemplos nos schemas OpenAPI.
- O texto do e-mail de confirmação será definido na fase Define (cliente, barbeiro, serviço, horário).

---

## Approaches Explored

### Approach A: FastAPI em camadas + SQLAlchemy + Pydantic ⭐ Recommended

**Description:** FastAPI com `routers → services → repositories`, SQLAlchemy sobre SQLite e schemas Pydantic. A regra de conflito de horário fica isolada em um serviço; a notificação roda em `BackgroundTasks` (e-mail simulado por log).

**Pros:**
- OpenAPI/Swagger automático, o que atende o critério de docs.
- Pydantic valida as entradas.
- Camada de serviço fácil de testar; `TestClient` cobre as rotas.

**Cons:**
- Mais arquivos que o mínimo.
- Exige entender injeção de dependências (`Depends`).

**Why Recommended:** KB (`pydantic`, `python/clean-architecture`, `testing`) cobre quase todo o conjunto (confiança 0.85: KB sem match no código). Isolar a regra de disponibilidade a torna a peça mais testável.

---

### Approach B: Flask + SQLAlchemy + Marshmallow

**Description:** Flask com blueprints; validação via Marshmallow ou Pydantic manual; OpenAPI por extensão (flask-smorest ou apispec).

**Pros:**
- Simples e conhecido, com muito material de estudo.

**Cons:**
- OpenAPI exige extensões e configuração extra.
- Validação não vem integrada.
- KB sem padrões para Flask.

---

### Approach C: FastAPI mínimo (módulo único)

**Description:** `main.py` com rotas, modelos e lógica juntos.

**Pros:**
- Mais rápido de escrever.

**Cons:**
- Mistura regra de negócio com HTTP, dificulta testes.
- Menos valor como portfólio.

---

## Selected Approach

| Attribute | Value |
|-----------|-------|
| **Chosen** | Approach A |
| **User Confirmation** | 2026-10-06 (resposta direta na sessão) |
| **Reasoning** | Atende o critério de docs OpenAPI e testes, e a separação em camadas mostra qualidade de código |

---

## Key Decisions Made

| # | Decision | Rationale | Alternative Rejected |
|---|----------|-----------|----------------------|
| 1 | FastAPI em camadas (routers/services/repositories) | OpenAPI nativo, testabilidade | Flask; FastAPI em módulo único |
| 2 | SQLite + SQLAlchemy, `create_all` no startup | Zero configuração para estudo | PostgreSQL/Docker; Supabase |
| 3 | Sem autenticação no MVP | Foco na regra de agendamento | JWT com papéis |
| 4 | Notificação simulada via log em `BackgroundTasks`, atrás de uma interface | Não bloqueia a resposta; troca por SMTP fica fácil | SMTP real |
| 5 | Conflito retorna 409; fora da disponibilidade ou no passado retorna 422 | Semântica HTTP clara para o front-end | Código único de erro |
| 6 | Intervalos encostados (fim = início) são permitidos; cancelados não contam | Evita falsos conflitos | Bloquear tudo que toca |
| 7 | Checagem e gravação na mesma transação | Reduz condição de corrida | Checagem separada da gravação |
| 8 | Horários como `datetime` local, sem fuso | Simplicidade no MVP | Suporte a fusos |

---

## Features Removed (YAGNI)

| Feature Suggested | Reason Removed | Can Add Later? |
|-------------------|----------------|----------------|
| Autenticação JWT e papéis (cliente/barbeiro/admin) | Decidido: sem login no MVP; não é necessário para a regra central | Yes |
| E-mail real via SMTP | A descrição pede notificação simulada | Yes |
| Pagamento, lembretes e reagendamento | Não resolvem o problema central (evitar conflito) | Yes |
| Docker, migrations Alembic e CI | SQLite local com `create_all` basta; pouco ganho para o estudo agora | Yes |
| Suporte a fusos horários | Complexidade sem valor no MVP | Yes |

---

## Incremental Validations

| Section | Presented | User Feedback | Adjusted? |
|---------|-----------|---------------|-----------|
| Conceito: entidades, regra de conflito e rotas | ✅ | "Está certo, seguir" | No |
| Estrutura, decisões de dados e testes | ✅ | "Está certo, gerar o documento" | No |

---

## Suggested Requirements for /define

### Problem Statement (Draft)
Oferecer uma API backend que permita agendar serviços de barbearia sem conflito de horário por profissional, registrando o agendamento e disparando uma confirmação simulada por e-mail.

### Target Users (Draft)
| User | Pain Point |
|------|------------|
| Cliente | Marcar um horário sem risco de choque e receber confirmação |
| Barbeiro | Ter a agenda sem sobreposições |
| Desenvolvedor front-end (web/mobile) | Contrato HTTP claro e documentado (OpenAPI) |

### Success Criteria (Draft)
- [ ] Testes automatizados com pytest cobrindo a regra de conflito e as rotas principais
- [ ] Documentação OpenAPI/Swagger navegável
- [ ] README com instruções de instalação, execução e testes
- [ ] Dois agendamentos sobrepostos para o mesmo barbeiro retornam 409
- [ ] Criar um agendamento aciona a notificação simulada (log), sem bloquear a resposta

### Constraints Identified
- Python com FastAPI, SQLAlchemy e Pydantic
- SQLite local; sem dependências externas
- Sem autenticação; sem fusos horários
- Projeto de estudo/portfólio

### Out of Scope (Confirmed)
- Autenticação JWT e papéis
- E-mail real (SMTP)
- Pagamento, lembretes e reagendamento
- Docker, Alembic e CI
- Fusos horários

### Entidades e Rotas (Draft)
- Entidades: Cliente, Barbeiro, Serviço (duração e preço), Disponibilidade (janelas semanais por barbeiro), Agendamento (início/fim calculados pela duração; status).
- Rotas: CRUD básico de clientes, barbeiros e serviços; `POST/GET` de disponibilidade; `GET /barbeiros/{id}/horarios-livres?data=`; `POST/GET/DELETE` de agendamentos (cancelamento muda o status).

---

## Session Summary

| Metric | Value |
|--------|-------|
| Questions Asked | 4 (+ 1 de amostras) |
| Approaches Explored | 3 |
| Features Removed (YAGNI) | 5 |
| Validations Completed | 2 |
| Duration | Sessão única |

---

## Next Step

**Ready for:** `/define .claude/sdd/features/BRAINSTORM_BARBERSHOP_SCHEDULING_API.md`
