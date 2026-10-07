# DESIGN: Barbershop Scheduling API

> Design técnico de uma API FastAPI em camadas que agenda serviços de barbearia sem conflito de horário e dispara uma confirmação simulada.

## Metadata

| Attribute | Value |
|-----------|-------|
| **Feature** | BARBERSHOP_SCHEDULING_API |
| **Date** | 2026-10-06 |
| **Author** | design-agent |
| **DEFINE** | [DEFINE_BARBERSHOP_SCHEDULING_API.md](./DEFINE_BARBERSHOP_SCHEDULING_API.md) |
| **Status** | ✅ Shipped |

---

## Architecture Overview

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        BARBERSHOP SCHEDULING API                      │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Cliente HTTP (web/mobile/Swagger)                                    │
│        │                                                              │
│        ▼                                                              │
│  ┌───────────┐   Pydantic (schemas.py): valida entrada, 422          │
│  │ routers/  │──────────────────────────────────────────────┐        │
│  └─────┬─────┘                                              │        │
│        │ chama                                              │        │
│        ▼                                                    │        │
│  ┌──────────────────────────────┐   BackgroundTasks         │        │
│  │ services/                    │──────────────┐            │        │
│  │  agendamento_service  ◄──────┼─ regra de    │            │        │
│  │  disponibilidade_service     │  conflito    ▼            │        │
│  │  cadastro_service            │      ┌────────────────┐   │        │
│  └─────┬────────────────────────┘      │ notificacao_   │   │        │
│        │ usa                           │ service        │   │        │
│        ▼                               │ (Protocol +    │   │        │
│  ┌──────────────┐                      │  LogNotifier)  │   │        │
│  │ repositories/│                      └───────┬────────┘   │        │
│  └─────┬────────┘                              ▼            │        │
│        ▼                                   [ logging ]      │        │
│  ┌──────────────┐                                           │        │
│  │ models.py    │ SQLAlchemy 2.0 ──► SQLite (BEGIN IMMEDIATE)        │
│  └──────────────┘                                                    │
│                                                                       │
│  errors.py: exceções de domínio ──► handlers em main.py ──► 404/409/422│
└──────────────────────────────────────────────────────────────────────┘

Dependências (sem ciclos):  routers → services → repositories → models
                            services → notificacao_service (Protocol)
                            errors.py e config.py não importam nenhuma camada
```

---

## Components

| Component | Purpose | Technology |
|-----------|---------|------------|
| `routers/` | Rotas HTTP, status codes e docs OpenAPI; sem regra de negócio | FastAPI `APIRouter` |
| `schemas.py` | Contratos de entrada/saída e validação de campos | Pydantic v2 (validators `Annotated`) |
| `services/agendamento_service.py` | Regra central: calcula `fim`, valida passado, disponibilidade e conflito; grava e cancela | Python puro + repositories |
| `services/disponibilidade_service.py` | Janelas semanais e cálculo de horários livres em slots de 15 min | Python puro |
| `services/cadastro_service.py` | CRUD de clientes, barbeiros e serviços | Python puro |
| `services/notificacao_service.py` | `Notificador` (Protocol) e `LogNotificador` que escreve a confirmação no log | `logging` |
| `repositories/` | Acesso a dados e consulta de sobreposição | SQLAlchemy 2.0 `Session` |
| `models.py` | Tabelas `clientes`, `barbeiros`, `servicos`, `disponibilidades`, `agendamentos` | SQLAlchemy ORM |
| `database.py` | Engine SQLite, `SessionLocal`, `BEGIN IMMEDIATE` | SQLAlchemy |
| `errors.py` | Exceções de domínio (`ConflitoHorarioError` etc.) | Python |
| `dependencies.py` | `get_db`, `get_agora` (relógio injetável), `get_notificador` | FastAPI `Depends` |
| `config.py` | `DATABASE_URL`, `SLOT_MINUTES` | dataclass imutável |

---

## Key Decisions

### Decision 1: Checagem de conflito e gravação em uma transação `BEGIN IMMEDIATE`

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-10-06 |

**Context:** A regra central (409) pode falhar se duas requisições checam ao mesmo tempo e ambas gravam. O SQLite abre transações em modo diferido por padrão, então a leitura não bloqueia o outro escritor.

**Choice:** Abrir cada transação com `BEGIN IMMEDIATE` (receita documentada do SQLAlchemy para pysqlite). A consulta de sobreposição e o `INSERT` rodam dentro da mesma transação, e o `commit` acontece uma única vez, no fim do caso de uso.

**Rationale:** O segundo escritor espera o primeiro terminar e então enxerga o agendamento já gravado. Atende a suposição A-005 sem constraint de exclusão, que o SQLite não tem.

**Alternatives Rejected:**
1. Checar e gravar em transações separadas - rejeitado porque deixa a janela de corrida aberta.
2. Constraint única por `(barbeiro_id, inicio)` - rejeitado porque não detecta sobreposição parcial.
3. Lock em memória no processo - rejeitado porque não protege vários workers.

**Consequences:**
- Escritas ficam serializadas no SQLite (aceitável para o MVP).
- Trocar para PostgreSQL depois exigirá `SELECT ... FOR UPDATE` ou constraint de exclusão.

---

### Decision 2: Relógio injetável para a regra "no passado"

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-10-06 |

**Context:** AT-005 exige 422 para horários no passado, e os demais testes precisam de datas futuras fixas.

**Choice:** O serviço recebe `agora: datetime` pelo parâmetro. A dependência `get_agora` devolve `datetime.now()` em produção, e os testes a substituem com `app.dependency_overrides`.

**Rationale:** Testes determinísticos, sem congelar o relógio global nem depender da data de execução.

**Alternatives Rejected:**
1. `freezegun` - rejeitado por adicionar dependência para algo que um parâmetro resolve.
2. Datas "relativas a hoje" nos testes - rejeitado porque quebram em fins de semana e viradas de dia.

**Consequences:**
- A assinatura dos casos de uso ganha um parâmetro.
- A regra de passado fica testável em unidade.

---

### Decision 3: Exceções de domínio mapeadas para HTTP em um único lugar

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-10-06 |

**Context:** O contrato pede 404, 409 e 422 previsíveis para o front-end, e os services não devem conhecer HTTP.

**Choice:** Os services levantam `RecursoNaoEncontradoError`, `ConflitoHorarioError`, `ForaDaDisponibilidadeError` e `HorarioPassadoError`. Handlers registrados em `main.py` os convertem em respostas `{"detail": "..."}` com o código correto.

**Rationale:** A camada de serviço permanece testável sem HTTP, e o mapeamento fica numa tabela só.

**Alternatives Rejected:**
1. `HTTPException` dentro dos services - rejeitado porque acopla regra de negócio ao framework.
2. Retornar códigos de erro em tuplas - rejeitado por ser frágil e pouco idiomático.

**Consequences:**
- Um arquivo extra (`errors.py`).
- Rotas ficam finas.

---

### Decision 4: Notificação atrás de um Protocol, executada em `BackgroundTasks`

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-10-06 |

**Context:** A confirmação não pode atrasar nem derrubar o 201 (AT-009), e SMTP real fica para depois.

**Choice:** `Notificador` é um `Protocol` com `enviar_confirmacao(dados)`. O router agenda a chamada em `BackgroundTasks` depois do commit, passando um dataclass `DadosConfirmacao` (valores simples, sem objetos ORM). Exceções do notificador são capturadas e logadas.

**Rationale:** O dataclass evita acessar objetos ORM fora da sessão, e o Protocol permite trocar por SMTP sem tocar nos services.

**Alternatives Rejected:**
1. Chamar o notificador dentro da transação - rejeitado porque uma falha reverteria um agendamento válido.
2. Fila externa (Celery) - rejeitado por exagero para o MVP.

**Consequences:**
- A confirmação só sai se o commit tiver sucesso.
- Em caso de falha do notificador, o agendamento permanece e o erro vai para o log.

---

### Decision 5: Slots de 15 minutos e e-mail em português (fecha A-003 e A-006)

| Attribute | Value |
|-----------|-------|
| **Status** | Accepted |
| **Date** | 2026-10-06 |

**Context:** O DEFINE deixou a granularidade e o texto do e-mail como suposições.

**Choice:** `SLOT_MINUTES = 15` em `config.py`. O e-mail traz cliente, barbeiro, serviço, data/hora e preço, em português.

**Rationale:** Valores configuráveis cobrem o MVP e não prendem o contrato.

**Alternatives Rejected:**
1. Slots iguais à duração do serviço - rejeitado porque deixa buracos na agenda.

**Consequences:**
- `horarios-livres` retorna inícios múltiplos de 15 minutos dentro das janelas.

---

## File Manifest

| # | File | Action | Purpose | Agent | Dependencies |
|---|------|--------|---------|-------|--------------|
| 1 | `requirements.txt` | Create | fastapi, uvicorn, sqlalchemy, pytest, httpx, pytest-cov | (general) | None |
| 2 | `pytest.ini` | Create | testpaths, marcadores e opções de cobertura | (general) | None |
| 3 | `app/__init__.py` | Create | Pacote | (general) | None |
| 4 | `app/config.py` | Create | Configuração imutável (`DATABASE_URL`, `SLOT_MINUTES`) | @python-developer | None |
| 5 | `app/errors.py` | Create | Exceções de domínio | @python-developer | None |
| 6 | `app/database.py` | Create | Engine, `SessionLocal`, `BEGIN IMMEDIATE` | @fastapi-developer | 4 |
| 7 | `app/models.py` | Create | Modelos SQLAlchemy | @python-developer | 6 |
| 8 | `app/schemas.py` | Create | Schemas Pydantic e tipos validados | @python-developer | None |
| 9 | `app/repositories/__init__.py` | Create | Pacote | (general) | None |
| 10 | `app/repositories/cadastros.py` | Create | Acesso a clientes, barbeiros e serviços | @python-developer | 7 |
| 11 | `app/repositories/disponibilidades.py` | Create | Acesso a janelas semanais | @python-developer | 7 |
| 12 | `app/repositories/agendamentos.py` | Create | CRUD e consulta de sobreposição | @python-developer | 7 |
| 13 | `app/services/__init__.py` | Create | Pacote | (general) | None |
| 14 | `app/services/notificacao_service.py` | Create | `Notificador`, `LogNotificador`, `DadosConfirmacao` | @python-developer | None |
| 15 | `app/services/cadastro_service.py` | Create | CRUD de cadastros | @python-developer | 5, 10 |
| 16 | `app/services/disponibilidade_service.py` | Create | Janelas e horários livres | @python-developer | 4, 5, 11, 12 |
| 17 | `app/services/agendamento_service.py` | Create | Criar e cancelar agendamento com todas as regras | @python-developer | 5, 11, 12, 14 |
| 18 | `app/dependencies.py` | Create | `get_db`, `get_agora`, `get_notificador` | @fastapi-developer | 6, 14 |
| 19 | `app/routers/__init__.py` | Create | Pacote | (general) | None |
| 20 | `app/routers/clientes.py` | Create | Rotas de clientes | @fastapi-developer | 8, 15, 18 |
| 21 | `app/routers/barbeiros.py` | Create | Rotas de barbeiros | @fastapi-developer | 8, 15, 18 |
| 22 | `app/routers/servicos.py` | Create | Rotas de serviços | @fastapi-developer | 8, 15, 18 |
| 23 | `app/routers/disponibilidades.py` | Create | Janelas e `horarios-livres` | @fastapi-developer | 8, 16, 18 |
| 24 | `app/routers/agendamentos.py` | Create | Criar, listar, consultar e cancelar | @fastapi-developer | 8, 17, 18 |
| 25 | `app/main.py` | Create | App, routers, handlers de erro, `create_all` no startup | @fastapi-developer | 7, 19-24 |
| 26 | `scripts/seed.py` | Create | Dados de exemplo (COULD) | @python-developer | 7, 15 |
| 27 | `tests/conftest.py` | Create | Engine em memória, `client`, relógio fixo, notificador falso | @test-generator | 25 |
| 28 | `tests/test_agendamento_service.py` | Create | Unitários da regra de conflito, passado e disponibilidade | @test-generator | 17, 27 |
| 29 | `tests/test_disponibilidade_service.py` | Create | Unitários dos slots | @test-generator | 16, 27 |
| 30 | `tests/test_api_cadastros.py` | Create | Rotas de cadastro, 404 e 422 | @test-generator | 25, 27 |
| 31 | `tests/test_api_agendamentos.py` | Create | AT-001 a AT-007 e AT-009 pela API | @test-generator | 25, 27 |
| 32 | `tests/test_api_horarios_livres.py` | Create | AT-008 | @test-generator | 25, 27 |
| 33 | `README.md` | Create | Instalação, execução, testes e rotas | @code-documenter | 25 |

**Total Files:** 33

---

## Agent Assignment Rationale

> Agentes descobertos em `agents/**/*.md` do plugin; o Build invoca os especialistas indicados.

| Agent | Files Assigned | Why This Agent |
|-------|----------------|----------------|
| @fastapi-developer | 6, 18, 20-25 | Rotas, injeção de dependências, sessão do banco, handlers de erro e `main.py` em FastAPI |
| @python-developer | 4, 5, 7, 8, 10-12, 14-17, 26 | Código Python com camadas, dataclasses e type hints; casa com `python/clean-architecture` |
| @test-generator | 27-32 | Gera testes pytest, fixtures e integração com `TestClient`; `@fastapi-developer` revisa os overrides de dependência |
| @code-documenter | 33 | Especialista em README e docs de API |
| (general) | 1-3, 9, 13, 19 | Arquivos de configuração e `__init__.py` vazios, sem especialista dedicado |

**Agent Discovery:**
- Scanned: `agents/**/*.md` do plugin AgentSpec
- Matched by: tipo de arquivo (`.py`, testes, README), palavras-chave e domínio do KB (python, pydantic, testing)
- `@fastapi-developer` é um agente do projeto (`.claude/agents/fastapi-developer.md`), criado para cobrir rotas e camada HTTP.

---

## Code Patterns

### Pattern 1: Regra de conflito e criação (service)

```python
# app/services/agendamento_service.py (KB: python/clean-architecture)
from datetime import datetime, timedelta

from app.errors import (
    ConflitoHorarioError,
    ForaDaDisponibilidadeError,
    HorarioPassadoError,
    RecursoNaoEncontradoError,
)
from app.models import Agendamento, StatusAgendamento


def criar_agendamento(db, dados, agora: datetime) -> Agendamento:
    cliente = db.cadastros.obter_cliente(dados.cliente_id)
    barbeiro = db.cadastros.obter_barbeiro(dados.barbeiro_id)
    servico = db.cadastros.obter_servico(dados.servico_id)
    if not (cliente and barbeiro and servico):
        raise RecursoNaoEncontradoError("cliente, barbeiro ou serviço não encontrado")

    inicio = dados.inicio
    fim = inicio + timedelta(minutes=servico.duracao_minutos)

    if inicio <= agora:
        raise HorarioPassadoError("horário no passado")
    if not db.disponibilidades.cobre(barbeiro.id, inicio, fim):
        raise ForaDaDisponibilidadeError("fora da disponibilidade do barbeiro")
    if db.agendamentos.existe_sobreposicao(barbeiro.id, inicio, fim):
        raise ConflitoHorarioError("barbeiro já tem agendamento nesse horário")

    agendamento = Agendamento(
        cliente_id=cliente.id, barbeiro_id=barbeiro.id, servico_id=servico.id,
        inicio=inicio, fim=fim, status=StatusAgendamento.AGENDADO,
    )
    db.agendamentos.adicionar(agendamento)
    return agendamento
```

### Pattern 2: Consulta de sobreposição (repository)

```python
# app/repositories/agendamentos.py
from sqlalchemy import select

from app.models import Agendamento, StatusAgendamento


def existe_sobreposicao(session, barbeiro_id: int, inicio, fim) -> bool:
    # novo.inicio < existente.fim  e  novo.fim > existente.inicio
    # (fim == inicio fica de fora: intervalos encostados são permitidos)
    consulta = select(Agendamento.id).where(
        Agendamento.barbeiro_id == barbeiro_id,
        Agendamento.status == StatusAgendamento.AGENDADO,
        Agendamento.inicio < fim,
        Agendamento.fim > inicio,
    ).limit(1)
    return session.execute(consulta).first() is not None
```

### Pattern 3: SQLite com `BEGIN IMMEDIATE`

```python
# app/database.py
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from app.config import CONFIG

engine = create_engine(CONFIG.database_url, connect_args={"check_same_thread": False})


@event.listens_for(engine, "connect")
def _sem_begin_automatico(dbapi_connection, _record):
    dbapi_connection.isolation_level = None  # pysqlite não emite BEGIN sozinho


@event.listens_for(engine, "begin")
def _begin_immediate(conn):
    conn.exec_driver_sql("BEGIN IMMEDIATE")


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
```

### Pattern 4: Schemas com validação (KB: pydantic/custom-validators)

```python
# app/schemas.py
from datetime import datetime
from typing import Annotated
import re

from pydantic import AfterValidator, BaseModel, Field, field_validator


def _validar_email(v: str) -> str:
    v = v.strip().lower()
    if not re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", v):
        raise ValueError(f"e-mail inválido: {v}")
    return v


Email = Annotated[str, AfterValidator(_validar_email)]


class ClienteIn(BaseModel):
    nome: str = Field(min_length=2, max_length=100)
    email: Email
    telefone: str = Field(min_length=8, max_length=20)


class AgendamentoIn(BaseModel):
    cliente_id: int
    barbeiro_id: int
    servico_id: int
    inicio: datetime

    @field_validator("inicio")
    @classmethod
    def sem_fuso(cls, v: datetime) -> datetime:
        if v.tzinfo is not None:
            raise ValueError("use horário local, sem fuso")
        return v
```

### Pattern 5: Notificação e router

```python
# app/services/notificacao_service.py
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

log = logging.getLogger("notificacoes")


@dataclass(frozen=True)
class DadosConfirmacao:
    email: str
    cliente: str
    barbeiro: str
    servico: str
    inicio: datetime
    preco: float


class Notificador(Protocol):
    def enviar_confirmacao(self, dados: DadosConfirmacao) -> None: ...


class LogNotificador:
    def enviar_confirmacao(self, dados: DadosConfirmacao) -> None:
        log.info(
            "E-mail para %s: Olá, %s! Seu horário com %s para %s está confirmado em %s (R$ %.2f).",
            dados.email, dados.cliente, dados.barbeiro, dados.servico,
            dados.inicio.strftime("%d/%m/%Y %H:%M"), dados.preco,
        )


def enviar_sem_falhar(notificador: Notificador, dados: DadosConfirmacao) -> None:
    try:
        notificador.enviar_confirmacao(dados)
    except Exception:
        log.exception("falha ao enviar confirmação")
```

```python
# app/routers/agendamentos.py
@router.post("", response_model=AgendamentoOut, status_code=201)
def criar(dados: AgendamentoIn, tarefas: BackgroundTasks, db=Depends(get_db),
          agora=Depends(get_agora), notificador=Depends(get_notificador)):
    agendamento, confirmacao = agendamento_service.criar(db, dados, agora)
    tarefas.add_task(enviar_sem_falhar, notificador, confirmacao)
    return agendamento
```

### Pattern 6: Handlers de erro

```python
# app/main.py
ERROS_HTTP = {
    RecursoNaoEncontradoError: 404,
    ConflitoHorarioError: 409,
    ForaDaDisponibilidadeError: 422,
    HorarioPassadoError: 422,
}

for tipo, status in ERROS_HTTP.items():
    def _handler(request, exc, status=status):
        return JSONResponse(status_code=status, content={"detail": str(exc)})
    app.add_exception_handler(tipo, _handler)
```

### Pattern 7: Fixtures de teste (KB: testing/integration-tests)

```python
# tests/conftest.py
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.dependencies import get_agora, get_db, get_notificador
from app.main import app
from app.models import Base

AGORA_FIXO = datetime(2030, 1, 1, 8, 0)  # terça-feira; 2030-01-07 é segunda


class NotificadorFalso:
    def __init__(self):
        self.enviados = []

    def enviar_confirmacao(self, dados):
        self.enviados.append(dados)


@pytest.fixture
def notificador():
    return NotificadorFalso()


@pytest.fixture
def client(notificador):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    Base.metadata.create_all(engine)
    Sessao = sessionmaker(bind=engine, expire_on_commit=False)

    def _db():
        with Sessao() as sessao:
            yield sessao

    app.dependency_overrides[get_db] = _db
    app.dependency_overrides[get_agora] = lambda: AGORA_FIXO
    app.dependency_overrides[get_notificador] = lambda: notificador
    yield TestClient(app)
    app.dependency_overrides.clear()
```

### Pattern 8: Configuração

```yaml
# Valores em app/config.py (dataclass imutável, lidos de variáveis de ambiente)
DATABASE_URL: "sqlite:///./barbearia.db"
SLOT_MINUTES: 15
```

---

## Data Flow

```text
1. Cliente envia POST /agendamentos {cliente_id, barbeiro_id, servico_id, inicio}
   │
   ▼
2. Pydantic valida tipos, formato e ausência de fuso (falha → 422)
   │
   ▼
3. Transação abre com BEGIN IMMEDIATE (get_db)
   │
   ▼
4. service: carrega cliente/barbeiro/serviço (ausente → 404)
   calcula fim = inicio + duração
   valida passado (422) → disponibilidade (422) → sobreposição (409)
   │
   ▼
5. repository grava o agendamento e a transação faz commit
   │
   ▼
6. Resposta 201 sai com o agendamento
   │
   ▼
7. BackgroundTasks executa o notificador: 1 linha de log com a confirmação
   (falha no envio é logada e não altera a resposta)
```

---

## Integration Points

| External System | Integration Type | Authentication |
|-----------------|-----------------|----------------|
| SQLite (arquivo local) | SQLAlchemy 2.0 | Nenhuma |
| E-mail (simulado) | `Notificador` com log | Nenhuma (SMTP real fora do escopo) |

---

## Testing Strategy

| Test Type | Scope | Files | Tools | Coverage Goal |
|-----------|-------|-------|-------|---------------|
| Unit | Regra de conflito, passado, disponibilidade e slots | `tests/test_agendamento_service.py`, `tests/test_disponibilidade_service.py` | pytest + SQLite em memória | 85% em `agendamento_service.py` |
| Integration | Rotas, códigos 201/404/409/422 e notificação | `tests/test_api_cadastros.py`, `tests/test_api_agendamentos.py`, `tests/test_api_horarios_livres.py` | pytest + `TestClient` + overrides | Todos os caminhos dos AT |
| E2E | Swagger e README | Manual | `uvicorn` + `/docs` | Subir a API só com o README |

**Cobertura dos testes de aceitação:**

| AT | Verificado em |
|----|---------------|
| AT-001 | `test_api_agendamentos.py::test_cria_agendamento` (201, `fim` = 10:30, 1 item em `notificador.enviados`) |
| AT-002 | `test_agendamento_service.py` e `test_api_agendamentos.py` (parcial, total e contida → 409; nada gravado) |
| AT-003 | `test_agendamento_service.py::test_intervalo_encostado_permitido` |
| AT-004 | `test_api_agendamentos.py` (18:00 e domingo → 422) |
| AT-005 | `test_agendamento_service.py` (relógio fixo → 422) |
| AT-006 | `test_api_agendamentos.py::test_cancelar_libera_horario` |
| AT-007 | `test_api_agendamentos.py` (ids inexistentes → 404) |
| AT-008 | `test_api_horarios_livres.py` |
| AT-009 | `test_api_agendamentos.py` com notificador que levanta exceção; a resposta segue 201 |

**Comando de cobertura:** `pytest --cov=app.services.agendamento_service --cov-fail-under=85`

---

## Error Handling

| Error Type | Handling Strategy | Retry? |
|------------|-------------------|--------|
| Entrada inválida (tipo, e-mail, fuso) | Pydantic → 422 com detalhes por campo | No |
| Recurso inexistente | `RecursoNaoEncontradoError` → 404 | No |
| Sobreposição de horário | `ConflitoHorarioError` → 409, nada gravado | No (o cliente escolhe outro horário) |
| Fora da disponibilidade ou no passado | `ForaDaDisponibilidadeError`/`HorarioPassadoError` → 422 | No |
| Falha no notificador | Capturada e logada em `enviar_sem_falhar`; resposta segue 201 | No (retentativa fica para SMTP real) |
| Banco ocupado (lock do `BEGIN IMMEDIATE`) | Espera pelo timeout padrão do pysqlite; se estourar, erro 500 | Sim, pelo cliente |

---

## Configuration

| Config Key | Type | Default | Description |
|------------|------|---------|-------------|
| `DATABASE_URL` | string | `sqlite:///./barbearia.db` | Conexão do banco |
| `SLOT_MINUTES` | int | `15` | Granularidade dos horários livres |
| `LOG_LEVEL` | string | `INFO` | Nível de log, inclusive das notificações |

---

## Security Considerations

- Sem autenticação no MVP: qualquer cliente cria e cancela agendamentos; documentar no README como limitação conhecida.
- Consultas via ORM parametrizado, sem SQL montado por texto, o que evita injeção.
- Validação de tamanho de campos e e-mail em Pydantic.
- O log de confirmação contém e-mail e nome do cliente (dados pessoais); em produção, mascarar ou usar SMTP real.

---

## Observability

| Aspect | Implementation |
|--------|----------------|
| Logging | Módulo `logging` padrão; logger `notificacoes` para confirmações e falhas |
| Metrics | N/A no MVP |
| Tracing | N/A no MVP |

---

## Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-10-06 | design-agent | Initial version, a partir de DEFINE_BARBERSHOP_SCHEDULING_API.md |
| 1.1 | 2026-10-06 | ship-agent | Shipped and archived |

---

## Next Step

**Shipped:** arquivado em `.claude/sdd/archive/BARBERSHOP_SCHEDULING_API/`
