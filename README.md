# API de Agendamento de Barbearia

API backend em **FastAPI** para gerenciar agendamentos de barbearia. Cadastra clientes, barbeiros, serviços e a disponibilidade semanal de cada barbeiro, e cria agendamentos **sem conflito de horário**. Cada agendamento criado dispara uma confirmação por e-mail **simulada** (registrada no log).

Projeto de estudo/portfólio. Pode servir de backend para uma aplicação web ou mobile.

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2.0 (SQLite) · Pydantic v2 · pytest

## Como rodar

Requisitos: Python 3.10 ou superior (testado com 3.13).

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
pytest
```

Com o `make` instalado, o mesmo fluxo é:

```bash
make install   # cria o .venv e instala as dependências
make run       # sobe a API (recarrega ao salvar arquivos)
make test      # roda os testes
```

Outros alvos: `make seed` (dados de exemplo), `make cov` (cobertura), `make lint` (ruff) e `make clean`. Dá para mudar o endereço, por exemplo `make run PORT=9000` ou `make run HOST=0.0.0.0`. Rode `make` sem argumentos para ver a lista.

A API sobe em `http://127.0.0.1:8000`. A documentação interativa (Swagger) fica em **`/docs`** e o ReDoc em `/redoc`. O banco `barbearia.db` é criado automaticamente na primeira execução.

### Front-end de teste

Com a API rodando, abra **`http://127.0.0.1:8000/app/`** (a raiz `/` redireciona para lá). É uma página simples, em HTML e JavaScript puros servida pela própria API, sem Node nem etapa de build:

- **Agendar**: escolha cliente, barbeiro, serviço e data, veja os horários livres, clique em um e confirme. Há também uma área "Testar erros do servidor" que envia um horário digitado à mão, útil para ver os erros 409 (conflito) e 422 (fora da janela ou no passado).
- **Agendamentos**: lista com filtro por barbeiro e data, e botão para cancelar.
- **Cadastros**: formulários de cliente, barbeiro, serviço e disponibilidade, e o botão **Criar dados de exemplo**, que dispensa o `make seed`.

A confirmação por e-mail simulada continua indo para o log, ou seja, para o terminal onde a API está rodando. O tema claro ou escuro segue a configuração do seu sistema.

Para popular com dados de exemplo (1 cliente, 2 barbeiros, 3 serviços e janelas de segunda a sábado, 09:00-18:00):

```bash
python -m scripts.seed
```

### Cobertura de testes

```bash
pytest --cov=app --cov-report=term-missing
pytest --cov=app.services.agendamento_service --cov-fail-under=85
```

## Rotas

| Método | Rota | Descrição |
|--------|------|-----------|
| POST/GET | `/clientes`, `/clientes/{id}` | Cadastrar e consultar clientes |
| POST/GET | `/barbeiros`, `/barbeiros/{id}` | Cadastrar e consultar barbeiros |
| POST/GET | `/servicos`, `/servicos/{id}` | Cadastrar e consultar serviços (duração e preço) |
| POST/GET | `/barbeiros/{id}/disponibilidades` | Janelas semanais de trabalho (`dia_semana`: 0 = segunda ... 6 = domingo) |
| GET | `/barbeiros/{id}/horarios-livres?data=AAAA-MM-DD&servico_id=` | Horários livres em slots de 15 min |
| POST | `/agendamentos` | Criar agendamento |
| GET | `/agendamentos?barbeiro_id=&cliente_id=&data=` | Listar com filtros |
| GET | `/agendamentos/{id}` | Consultar um agendamento |
| DELETE | `/agendamentos/{id}` | Cancelar (muda o status para `cancelado` e libera o horário) |

### Códigos de resposta

| Código | Quando |
|--------|--------|
| 201 | Cadastro ou agendamento criado |
| 404 | Cliente, barbeiro, serviço ou agendamento inexistente |
| 409 | O barbeiro já tem um agendamento que se sobrepõe ao horário pedido |
| 422 | Dados inválidos, horário fora da disponibilidade do barbeiro ou no passado |

Intervalos que apenas se encostam (o fim de um é o início do outro) são permitidos. Agendamentos cancelados não bloqueiam o horário.

## Exemplo

```bash
curl -X POST http://127.0.0.1:8000/agendamentos \
  -H "Content-Type: application/json" \
  -d '{"cliente_id": 1, "barbeiro_id": 1, "servico_id": 1, "inicio": "2030-01-07T10:00:00"}'
```

Resposta `201`:

```json
{
  "id": 1,
  "cliente_id": 1,
  "barbeiro_id": 1,
  "servico_id": 1,
  "inicio": "2030-01-07T10:00:00",
  "fim": "2030-01-07T10:30:00",
  "status": "agendado"
}
```

O `fim` é calculado pela duração do serviço. No log da API aparece a confirmação simulada:

```text
INFO:notificacoes:E-mail para carlos@exemplo.com: Olá, Carlos Silva! Seu horário com João Barbeiro para Corte de cabelo está confirmado em 07/01/2030 10:00 (R$ 45.00).
```

## Configuração

Variáveis de ambiente (todas opcionais):

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `DATABASE_URL` | `sqlite:///./barbearia.db` | Conexão com o banco |
| `SLOT_MINUTES` | `15` | Granularidade dos horários livres |
| `LOG_LEVEL` | `INFO` | Nível de log |

## Arquitetura

```text
routers/      rotas HTTP (finas)            →  app/routers/
services/     regras de negócio             →  app/services/
repositories/ acesso a dados (SQLAlchemy)   →  app/repositories/
models.py · schemas.py · errors.py · config.py · database.py
```

- A regra de conflito fica em `app/services/agendamento_service.py` e não conhece HTTP: levanta exceções de domínio que `app/main.py` converte em 404/409/422.
- A checagem de sobreposição e a gravação acontecem na mesma transação (`BEGIN IMMEDIATE` no SQLite), então duas requisições simultâneas para o mesmo horário resultam em um 201 e um 409.
- A confirmação roda em `BackgroundTasks` depois do commit. Se o envio falhar, o erro vai para o log e a resposta continua `201`.
- O relógio e o notificador são injetados (`Depends`), o que permite testes determinísticos.

A especificação completa está em `.claude/sdd/archive/BARBERSHOP_SCHEDULING_API/` (BRAINSTORM, DEFINE, DESIGN, BUILD_REPORT e SHIPPED). O front-end de teste (`app/static/`) foi adicionado depois dessa especificação.

## Limitações conhecidas

- Sem autenticação: qualquer cliente da API pode criar e cancelar agendamentos.
- CORS não está configurado: o front-end de teste funciona porque é servido pela mesma origem da API. Um front-end separado (outra porta ou domínio) precisaria do `CORSMiddleware`.
- O front-end de teste não tem testes automatizados de interface no repositório; ele foi verificado manualmente com um navegador automatizado, fora do projeto.
- Horários em hora local, sem fuso horário.
- Disponibilidade semanal recorrente, sem folgas ou feriados por data.
- Um serviço por agendamento.
- E-mail apenas simulado (log); o log contém nome e e-mail do cliente.
- No console do Windows, acentos do log podem aparecer errados; defina `PYTHONUTF8=1` para corrigir.
- Para PostgreSQL no futuro, troque o `BEGIN IMMEDIATE` por `SELECT ... FOR UPDATE` ou uma constraint de exclusão.
