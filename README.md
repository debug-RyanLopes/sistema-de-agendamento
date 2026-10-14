# Barbearia: agendamento com duas áreas (Cliente e Empresa)

Sistema de agendamento de barbearia em **FastAPI**, com duas aplicações web que rodam em **portas diferentes** e compartilham o mesmo banco, para simular os dois lados:

| Área | Porta | Quem usa | O que faz |
|------|-------|----------|-----------|
| **Cliente** | 8000 | Quem quer cortar o cabelo | Informa nome, e-mail e telefone, escolhe serviço e dia, vê os barbeiros disponíveis com seus horários livres, marca e recebe a confirmação, com botão para cancelar |
| **Empresa** | 8001 | A barbearia | Protegida por senha. Vê os agendamentos marcados e gerencia clientes, barbeiros (com a disponibilidade semanal), serviços e produtos |

Cada agendamento gera uma confirmação por e-mail **simulada** (registrada no log). Projeto de estudo/portfólio.

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2.0 (SQLite) · Pydantic v2 · pytest · HTML/CSS/JavaScript puros nas duas páginas (sem Node nem build)

## Como rodar

Requisitos: Python 3.10 ou superior (testado com 3.13) e, opcionalmente, o `make`.

```bash
make install   # cria o .venv e instala as dependências
make seed      # opcional: dados de exemplo
make run       # sobe as DUAS áreas ao mesmo tempo (Ctrl+C encerra as duas)
```

Depois abra:

- **Cliente:** http://127.0.0.1:8000/
- **Empresa:** http://127.0.0.1:8001/ (o navegador pede usuário e senha: usuário `admin`, senha `admin123` no `make`, **só para desenvolvimento**)

Para testar os dois lados juntos, abra as duas páginas em abas ou janelas separadas: marque um horário na área do cliente, atualize a área da empresa (ela também atualiza sozinha a cada 10 s) e cancele por qualquer um dos lados. A confirmação por e-mail simulada aparece no terminal onde o `make run` está rodando.

Sem o `make` (Windows no PowerShell, por exemplo):

```bash
python -m venv .venv
.venv\Scripts\activate          # Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt
$env:ADMIN_PASSWORD = "uma-senha"   # Linux/macOS: export ADMIN_PASSWORD=uma-senha
python -m scripts.dev
```

Outros alvos do `make`:

| Comando | O que faz |
|---------|-----------|
| `make run-cliente` / `make run-admin` | Sobe só uma das áreas (com recarga automática ao salvar) |
| `make test` / `make cov` | Roda os testes, com ou sem cobertura |
| `make lint` | Roda o `ruff` |
| `make clean` | Remove caches |

Dá para mudar portas e senha: `make run PORTA_CLIENTE=9000 PORTA_ADMIN=9001 ADMIN_PASSWORD=outra`. Rode `make` sem argumentos para ver a lista. O Swagger de cada área fica em `/docs` (na da empresa, depois da senha).

## Área do Cliente

1. Preencha nome, e-mail e telefone.
2. Escolha o serviço e o dia e clique em **Ver barbeiros disponíveis**: aparecem só os barbeiros ativos com horário livre, cada um com seus horários.
3. Escolha um horário e confirme. A tela mostra o número, o barbeiro, o horário, o valor e um **código de cancelamento**.
4. Se errou ou teve um imprevisto, clique em **Cancelar este agendamento**. Quem fechou a página pode cancelar depois com o número e o código, no bloco "Já tem um agendamento?".

O cliente é identificado pelo e-mail: se o e-mail já existe, o cadastro é reaproveitado **sem sobrescrever** nome e telefone. Só dá para cancelar um horário futuro. Código errado e agendamento inexistente recebem a mesma resposta (404), para não revelar quais números existem.

Rotas expostas pela área do cliente (e só elas):

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/servicos` | Serviços ativos |
| GET | `/disponibilidade?data=AAAA-MM-DD&servico_id=` | Barbeiros ativos com horários livres no dia |
| POST | `/agendamentos` | Marcar (nome, e-mail, telefone, barbeiro, serviço, início) |
| POST | `/agendamentos/{id}/cancelar` | Cancelar com o código |

## Área da Empresa

Uma única página com cinco seções:

- **Agendamentos:** lista com filtros (barbeiro, cliente, dia, status) e botão para cancelar.
- **Clientes, Barbeiros, Serviços, Produtos:** criar, editar e **ativar/desativar** (sem excluir, para preservar o histórico). Inativos ficam ocultos, com a opção "Mostrar inativos". Um barbeiro ou serviço inativo some da área do cliente e não recebe novos agendamentos.
- **Barbeiros → Disponibilidade semanal:** janelas de trabalho por dia da semana. Sem janela, o barbeiro não aparece para os clientes.

Produtos são um catálogo (nome, preço e estoque); não há venda nem baixa de estoque.

A empresa expõe as rotas de gestão (`/clientes`, `/barbeiros`, `/servicos`, `/produtos`, `/barbeiros/{id}/disponibilidades`, `/barbeiros/{id}/horarios-livres`, `/agendamentos`), todas com `PUT` para editar e `PATCH .../ativo` para ativar ou desativar nos cadastros. Veja o Swagger em `http://127.0.0.1:8001/docs`.

### Códigos de resposta

| Código | Quando |
|--------|--------|
| 201 | Cadastro ou agendamento criado |
| 401 | Área da empresa sem senha ou com senha errada |
| 404 | Recurso inexistente (ou código de cancelamento inválido) |
| 409 | O barbeiro já tem um agendamento que se sobrepõe ao horário pedido |
| 422 | Dados inválidos, recurso inativo, fora da disponibilidade, no passado ou cancelamento de horário que já passou |

Intervalos que apenas se encostam são permitidos. Agendamentos cancelados não bloqueiam o horário.

## Configuração

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `ADMIN_PASSWORD` | (obrigatória) | Senha da área da empresa. Sem ela a área **não sobe** |
| `DATABASE_URL` | `sqlite:///./barbearia.db` | Conexão com o banco |
| `SLOT_MINUTES` | `15` | Granularidade dos horários livres |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `HOST`, `PORTA_CLIENTE`, `PORTA_ADMIN` | `127.0.0.1`, `8000`, `8001` | Endereço e portas do `make run` |

## Banco de dados

O SQLite fica em `barbearia.db`. Ao iniciar, cada área cria as tabelas que faltam e aplica uma **migração leve** (`app/database.py`) que acrescenta, sem apagar dados, as colunas `ativo` e `codigo_cancelamento` em bancos criados pela versão anterior. Os dois processos escrevem no mesmo arquivo; a checagem de conflito e a gravação acontecem na mesma transação (`BEGIN IMMEDIATE`), então duas requisições simultâneas para o mesmo horário, mesmo vindas das duas áreas, resultam em um 201 e o resto 409.

## Arquitetura

```text
app/main_cliente.py   app/main_admin.py      duas aplicações FastAPI (fábricas criar_app)
app/aplicacao.py                              fábrica comum: erros, banco, arquivos estáticos
app/routers/          rotas HTTP finas        publico.py (cliente) · cadastros.py · agendamentos.py · disponibilidades.py
app/services/         regras de negócio       sem dependência de HTTP
app/repositories/     acesso a dados          SQLAlchemy
app/seguranca.py      senha Basic da empresa
app/static/           cliente/ · admin/ · comum/
scripts/              dev.py (sobe as duas áreas) · seed.py
```

- As regras ficam nos services e levantam exceções de domínio, que a fábrica converte em 404/409/422.
- A confirmação roda em `BackgroundTasks` depois do commit; se falhar, o erro vai para o log e a resposta continua `201`.
- Relógio e notificador são injetados (`Depends`), o que deixa os testes determinísticos.
- Cada porta serve a própria página na mesma origem, então não há CORS.

A especificação da primeira versão está em `.claude/sdd/archive/BARBERSHOP_SCHEDULING_API/` (BRAINSTORM, DEFINE, DESIGN, BUILD_REPORT e SHIPPED). As duas áreas, a gestão de cadastros e o cancelamento pelo cliente foram acrescentados depois dela e ainda não passaram pelo ciclo SDD.

## Testes

```bash
make test
make cov    # cobertura do pacote app
```

Inclui testes de serviço, de API das duas áreas, de senha, de migração e um teste de **concorrência real** (cliente e empresa disputando o mesmo horário contra um arquivo SQLite compartilhado). As páginas foram verificadas manualmente num navegador automatizado, fora do repositório.

## Limitações conhecidas

- A senha da empresa usa HTTP Basic sobre HTTP puro: serve para desenvolvimento local, não para produção. Não há usuários nem JWT.
- A área do cliente não exige login: quem sabe o número e o código cancela aquele agendamento.
- Horários em hora local, sem fuso horário; disponibilidade semanal sem folgas ou feriados por data; um serviço por agendamento.
- Produtos não são vendidos nem baixam estoque; não há notificação de cancelamento.
- E-mail apenas simulado (log); o log contém nome e e-mail do cliente.
- SQLite compartilhado por dois processos serve para desenvolvimento. Em produção, use PostgreSQL com `SELECT ... FOR UPDATE` ou uma constraint de exclusão no lugar do `BEGIN IMMEDIATE`.
- No console do Windows, acentos do log podem aparecer errados; defina `PYTHONUTF8=1`.
