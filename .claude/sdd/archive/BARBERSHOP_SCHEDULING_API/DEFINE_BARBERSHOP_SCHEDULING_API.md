# DEFINE: Barbershop Scheduling API

> API backend em FastAPI que gerencia agendamentos de barbearia, impede conflito de horário por barbeiro e dispara uma confirmação simulada por e-mail.

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | BARBERSHOP_SCHEDULING_API |
| **Date** | 2026-10-06 |
| **Author** | define-agent |
| **Status** | ✅ Shipped |
| **Clarity Score** | 14/15 |

---

## Problem Statement

Clientes de barbearia e barbeiros não têm um backend que registre agendamentos e garanta que dois atendimentos não ocupem o mesmo barbeiro no mesmo horário, o que causa choque de agenda e falta de confirmação ao cliente. Este projeto de estudo/portfólio entrega essa API para servir de base a um front-end web ou mobile.

---

## Target Users

| User | Role | Pain Point |
|------|------|------------|
| Cliente | Quem agenda um serviço | Marcar um horário sem risco de choque e receber confirmação com os dados do atendimento |
| Barbeiro | Prestador de serviço | Ter a agenda sem sobreposições e com janelas de trabalho respeitadas |
| Desenvolvedor front-end (web/mobile) | Consumidor da API | Contrato HTTP claro, com erros previsíveis e documentados (OpenAPI) |

---

## Goals

| Priority | Goal |
|----------|------|
| **MUST** | Cadastrar e consultar clientes, barbeiros e serviços (com duração e preço) |
| **MUST** | Cadastrar a disponibilidade semanal de cada barbeiro e consultar horários livres por data |
| **MUST** | Criar agendamento validando conflito (409) e disponibilidade/passado (422), com checagem e gravação na mesma transação |
| **MUST** | Disparar notificação de confirmação simulada (log) sem bloquear a resposta |
| **MUST** | Testes automatizados com pytest, documentação OpenAPI navegável e README |
| **SHOULD** | Cancelar agendamento (muda o status e libera o horário) e listar agendamentos com filtros simples |
| **COULD** | Dados de exemplo (seed) para demonstrar a API rapidamente |

---

## Success Criteria

- [ ] Dois agendamentos com intervalos sobrepostos para o mesmo barbeiro: o segundo retorna 409 em 100% dos casos de teste (sobreposição parcial, total e contida)
- [ ] Cobertura de testes de pelo menos 85% no serviço de agendamento (regra de conflito e disponibilidade)
- [ ] Todas as rotas aparecem no Swagger (`/docs`) com schemas de entrada, saída e códigos de erro (200/201/404/409/422)
- [ ] `POST /agendamentos` responde em menos de 300 ms no SQLite local, sem esperar a notificação
- [ ] Um desenvolvedor novo roda a API e os testes seguindo só o README, em até 5 comandos
- [ ] Cada agendamento criado gera exatamente 1 registro de log de confirmação com cliente, barbeiro, serviço e horário

---

## Acceptance Tests

| ID | Scenario | Given | When | Then |
|----|----------|-------|------|------|
| AT-001 | Criação com sucesso | Barbeiro com disponibilidade seg 09:00-18:00 e serviço de 30 min | `POST /agendamentos` na segunda às 10:00 | 201, agendamento com fim 10:30, status ativo, e 1 log de confirmação |
| AT-002 | Conflito: sobreposição parcial | Agendamento do barbeiro das 10:00 às 10:30 | Novo agendamento às 10:15 (30 min) para o mesmo barbeiro | 409 e nenhum registro novo gravado |
| AT-003 | Intervalo encostado permitido | Agendamento das 10:00 às 10:30 | Novo agendamento às 10:30 para o mesmo barbeiro | 201 |
| AT-004 | Fora da disponibilidade | Barbeiro disponível seg 09:00-18:00 | Agendamento na segunda às 18:00 (serviço de 30 min) ou no domingo | 422 |
| AT-005 | Horário no passado | Data/hora anterior ao momento atual | `POST /agendamentos` | 422 |
| AT-006 | Cancelamento libera horário | Agendamento ativo às 10:00 | `DELETE /agendamentos/{id}` e novo agendamento no mesmo horário | Status vira cancelado e o novo agendamento retorna 201 |
| AT-007 | Recurso inexistente | Barbeiro ou cliente com id inexistente | `POST /agendamentos` | 404 |
| AT-008 | Horários livres | Barbeiro com agendamento 10:00-10:30 na segunda | `GET /barbeiros/{id}/horarios-livres?data=` com `servico_id` | Lista sem slots que sobreponham 10:00-10:30 |
| AT-009 | Resposta não depende da notificação | Serviço de notificação lento ou com falha | `POST /agendamentos` | 201 mesmo assim; a falha é registrada em log |

---

## Out of Scope

Explicitamente fora desta feature:

- Autenticação JWT e papéis (cliente/barbeiro/admin)
- E-mail real via SMTP
- Pagamento, lembretes e reagendamento
- Docker, migrations Alembic e CI
- Suporte a fusos horários
- Front-end (web/mobile) e deploy

---

## Constraints

| Type | Constraint | Impact |
|------|------------|--------|
| Technical | Python com FastAPI, SQLAlchemy e Pydantic; SQLite local | Sem dependências externas; trocar de banco depois exige só mudar a URL |
| Technical | Sem autenticação e sem fusos (`datetime` local) | Qualquer cliente da API pode criar dados; o contrato assume um único fuso |
| Technical | Estrutura em camadas (routers, services, repositories) | Regra de conflito isolada no serviço e testável sem HTTP |
| Resource | Projeto individual de estudo/portfólio | Escopo enxuto; priorizar clareza e testes |

---

## Technical Context

| Aspect | Value | Notes |
|--------|-------|-------|
| **Deployment Location** | `app/` (código) e `tests/` na raiz do projeto | Projeto Python único; workspace vazio (greenfield) |
| **KB Domains** | python, pydantic, testing | `python/clean-architecture`, `pydantic` (validators e schemas), `testing` (pytest, fixtures, integration-tests) |
| **IaC Impact** | None | SQLite local, sem infraestrutura |

**Why This Matters:**

- **Location** → o Design cria `app/` e `tests/` sem ambiguidade
- **KB Domains** → o Design consulta padrões de camadas, validação e testes
- **IaC Impact** → nenhum; sem planejamento de infraestrutura

---

## Assumptions

| ID | Assumption | If Wrong, Impact | Validated? |
|----|------------|------------------|------------|
| A-001 | Agendamentos são de um serviço por vez, com início e fim contínuos (`fim = início + duração`) | Combos de serviços exigiriam um modelo de itens de agendamento | [ ] |
| A-002 | A disponibilidade é semanal recorrente (dia da semana, hora de início e fim), sem exceções por data | Folgas e feriados exigiriam uma tabela de exceções | [ ] |
| A-003 | Horários livres são calculados em slots alinhados a 15 minutos | Outra granularidade muda o cálculo de `horarios-livres` e os testes | [ ] |
| A-004 | Um agendamento deve caber inteiro dentro de uma janela de disponibilidade | Atendimentos que cruzam janelas precisariam de regra extra | [ ] |
| A-005 | O SQLite local suporta a checagem e gravação na mesma transação com concorrência baixa | Alta concorrência exigiria constraint ou bloqueio no banco | [ ] |
| A-006 | O texto do e-mail de confirmação inclui cliente, barbeiro, serviço, data/hora e preço, em português | Outro conteúdo muda só o `NotificationService` | [ ] |

**Note:** A-003 e A-006 são decisões de design de baixo risco e podem ser fechadas no `/design`.

---

## Clarity Score Breakdown

| Element | Score (0-3) | Notes |
|---------|-------------|-------|
| Problem | 3 | Claro, específico e com impacto definido |
| Users | 3 | Três personas com dor definida |
| Goals | 3 | MoSCoW completo e alinhado ao brainstorm |
| Success | 3 | Critérios com números (409, 85%, 300 ms, 1 log) e 9 testes de aceitação |
| Scope | 2 | Exclusões explícitas, mas granularidade de slots e exceções de agenda ainda são suposições |
| **Total** | **14/15** | |

**Minimum to proceed: 12/15**

---

## Open Questions

None - ready for Design. As suposições A-003 e A-006 podem ser fechadas no Design.

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-10-06 | define-agent | Initial version, extraído de BRAINSTORM_BARBERSHOP_SCHEDULING_API.md |
| 1.1 | 2026-10-06 | ship-agent | Shipped and archived |

---

## Next Step

**Shipped:** arquivado em `.claude/sdd/archive/BARBERSHOP_SCHEDULING_API/`
