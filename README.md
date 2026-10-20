# Barbearia: sistema de agendamento com duas áreas (Cliente e Empresa)

![CI](https://github.com/debug-RyanLopes/sistema-de-agendamento/actions/workflows/ci.yml/badge.svg)
![Licença MIT](https://img.shields.io/badge/licen%C3%A7a-MIT-blue)

Sistema de agendamento para barbearias, feito com **FastAPI** e **SQLite**. São duas aplicações web independentes, em **portas diferentes**, que compartilham o mesmo banco para simular os dois lados do negócio:

| Área | Porta | Quem usa | O que faz |
|------|-------|----------|-----------|
| **Cliente** | 8000 | Quem quer cortar o cabelo | Informa nome, e-mail e telefone, escolhe serviço e dia, vê os barbeiros disponíveis com seus horários livres, marca, recebe a confirmação e pode cancelar |
| **Empresa** | 8001 | A barbearia | Protegida por senha. Vê os agendamentos e gerencia clientes, barbeiros (com disponibilidade semanal), serviços e produtos |

Cada agendamento dispara uma confirmação por e-mail **simulada** (aparece no log do terminal). Projeto de estudo, criado para portfólio.

## Telas

### Área do Cliente

![Cliente escolhendo serviço, dia, barbeiro e horário](docs/01-cliente-agendamento.png)

*O cliente informa seus dados, escolhe o serviço e o dia e vê só os barbeiros com horário livre.*

![Confirmação do agendamento com código de cancelamento](docs/02-cliente-confirmacao.png)

*Confirmação com número, valor e o código que permite cancelar depois.*

No celular (layout responsivo):

![Formulário no celular](docs/10-cliente-mobile-dados.png) ![Horários no celular](docs/11-cliente-mobile-horarios.png)

*A mesma página se adapta à tela do celular, sem rolagem horizontal.*

### Área da Empresa

![Painel de agendamentos com filtros e paginação](docs/03-empresa-agendamentos.png)

*Agendamentos com filtros, status e paginação.*

![Cadastro de barbeiros](docs/04-empresa-barbeiros.png)

*Barbeiros: criar, editar e ativar/desativar.*

![Confirmação ao desativar um barbeiro, com o impacto nos agendamentos futuros](docs/05-empresa-desativar-barbeiro.png)

*Antes de desativar um barbeiro, o sistema mostra quantos agendamentos futuros serão afetados.*

![Disponibilidade semanal do barbeiro](docs/06-empresa-horarios.png)

*Disponibilidade semanal de cada barbeiro.*

![Cadastro de produtos](docs/07-empresa-produtos.png) ![Cadastro de serviços](docs/08-empresa-servicos.png)

*Produtos e serviços, com preços em reais.*

### API

![Documentação interativa (Swagger) da área da empresa](docs/09-empresa-swagger.png)

*Documentação gerada automaticamente em `/docs`.*

## O que este projeto demonstra

- **API REST em camadas** (routers → services → repositories → models), com regras de negócio sem dependência de HTTP.
- **Regra central sem conflito de horário:** um barbeiro nunca fica com dois agendamentos sobrepostos, mesmo com cliente e empresa disputando o mesmo horário em processos diferentes (teste de concorrência real).
- **Duas aplicações a partir do mesmo código**, cada uma expondo só as rotas do seu lado. A área do cliente tem apenas 4 rotas.
- **Segurança básica:** área da empresa atrás de senha, falha fechada (sem senha configurada ela não sobe), cancelamento do cliente por código aleatório, sem revelar quais agendamentos existem.
- **Migração leve e idempotente** do banco, sem apagar dados.
- **Front-end em HTML, CSS e JavaScript puros**, sem Node nem etapa de build, com tema claro/escuro e layout responsivo.
- **Testes automatizados:** 264 testes de API e serviços (cobertura de 99% do pacote `app`) e 20 testes de navegador com Playwright, que sobem as duas áreas de verdade. Lint com `ruff`.
- **Dinheiro com `Decimal`**, nunca `float`: preços trafegam como texto (`"45.00"`) e são somados sem erro de arredondamento.
- **Fuso de Manaus (UTC-4):** todos os horários do sistema são de Manaus, independentemente de onde o servidor ou o navegador estejam.

## Stack

Python 3.13 · FastAPI · SQLAlchemy 2 (SQLite) · Pydantic v2 · pytest · Playwright · ruff · HTML/CSS/JavaScript puros

## Como rodar

**Requisito:** Python 3.10 ou superior (testado com 3.13). O `make` é opcional.

### Com `make` (Linux, macOS ou Windows com make instalado)

```bash
git clone https://github.com/debug-RyanLopes/sistema-de-agendamento.git
cd sistema-de-agendamento

make install   # cria o .venv e instala as dependências (requirements-dev.txt)
make seed      # recomendado: cria dados de exemplo
make run       # sobe as DUAS áreas ao mesmo tempo (Ctrl+C encerra as duas)
```

### Sem `make` (Windows PowerShell)

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
python -m scripts.seed
$env:ADMIN_PASSWORD = "admin123"
python -m scripts.dev
```

### Sem `make` (Linux/macOS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
python -m scripts.seed
export ADMIN_PASSWORD=admin123
python -m scripts.dev
```

### Acessos

| Área | URL | Credenciais |
|------|-----|-------------|
| Cliente | http://127.0.0.1:8000/ | nenhuma |
| Empresa | http://127.0.0.1:8001/ | usuário `admin`, senha `admin123` (o navegador abre uma janela pedindo) |
| Documentação interativa (Swagger) | `/docs` em cada porta | a da empresa também pede a senha |

A senha `admin123` é o padrão do `make` e serve **apenas para desenvolvimento local**. Para trocar: `make run ADMIN_PASSWORD=outra` ou defina a variável de ambiente `ADMIN_PASSWORD`.

## Roteiro de avaliação (cerca de 5 minutos)

Com `make seed` e `make run` já executados:

1. Abra a **área do Cliente** (porta 8000) e a **área da Empresa** (porta 8001) em duas abas ou janelas.
2. No **Cliente**, preencha nome, e-mail e telefone, escolha um serviço e um dia (o seed cria disponibilidade de **segunda a sábado, das 9h às 18h**; domingo não tem atendimento) e clique em *Ver barbeiros disponíveis*.
3. Escolha um barbeiro e um horário e confirme. Anote o **número** e o **código de cancelamento** exibidos.
4. Na **Empresa**, aba *Agendamentos*: o agendamento aparece (a lista atualiza sozinha a cada 10 s). Veja também o cliente criado na aba *Clientes*.
5. Tente marcar **o mesmo horário** de novo, com o mesmo barbeiro: ele já não aparece como livre. Esse é o controle de conflito.
6. Na **Empresa**, aba *Barbeiros*, desative um barbeiro. Volte ao **Cliente** e busque de novo: ele some da lista.
7. No **Cliente**, clique em *Cancelar este agendamento*. O horário volta a ficar livre.
8. Abra o Swagger da empresa (`http://127.0.0.1:8001/docs`) para ver todas as rotas, e o da área do cliente (`http://127.0.0.1:8000/docs`) para ver que ela expõe só quatro.
9. Observe o terminal do `make run`: a confirmação de e-mail simulada é registrada ali.

Rodar os testes:

```bash
make test     # 264 testes de API e serviços (rápidos, sem navegador)
make cov      # com relatório de cobertura
make lint     # ruff
make e2e      # 20 testes de navegador (precisa do Google Chrome instalado)
```

## Comandos úteis

| Comando | O que faz |
|---------|-----------|
| `make install` | Cria o `.venv` e instala as dependências |
| `make seed` | Cria dados de exemplo (1 cliente, 2 barbeiros, 3 serviços, 2 produtos). Não faz nada se o banco já tem barbeiros |
| `make run` | Sobe cliente e empresa juntos |
| `make run-cliente` / `make run-admin` | Sobe só uma das áreas, com recarga automática ao salvar |
| `make test` / `make cov` | Testes de API e serviços, com ou sem cobertura |
| `make e2e` | Testes de navegador (Playwright + Chrome): sobem as duas áreas em portas livres com um banco temporário |
| `make lint` | Roda o `ruff` |
| `make clean` | Remove caches |

Para mudar portas ou senha: `make run PORTA_CLIENTE=9000 PORTA_ADMIN=9001 ADMIN_PASSWORD=outra`. Rode `make` sem argumentos para ver a lista.

### Começar do zero

O banco é o arquivo `barbearia.db` na raiz, criado na primeira execução e ignorado pelo Git. Para recomeçar, pare o servidor, apague o arquivo e rode `make seed` de novo.

## Área do Cliente

1. Preencha nome, e-mail e telefone.
2. Escolha o serviço e o dia: aparecem só os barbeiros ativos com horário livre, cada um com seus horários.
3. Escolha um horário e confirme. A tela mostra o número, o barbeiro, o horário, o valor e um **código de cancelamento**.
4. Para cancelar, use o botão da confirmação. Quem fechou a página cancela depois com o número e o código, no bloco "Já tem um agendamento?".

**Datas:** o cliente só enxerga de **hoje até o último dia do mês corrente** (em 15 de janeiro, até 31 de janeiro). O limite vale no navegador e é imposto também pelo servidor (422). Os horários só podem começar em múltiplos do `SLOT_MINUTES` (10:00, 10:15, 10:30...), o que impede a agenda de ser fragmentada.

O telefone é validado (DDD + número, com ou sem máscara, como `(92) 91234-5678`) e guardado só com os dígitos.

O cliente é identificado pelo e-mail: se o e-mail já existe, o cadastro é reaproveitado **sem sobrescrever** nome e telefone. Só dá para cancelar um horário futuro. Código errado e agendamento inexistente recebem a mesma resposta (404).

| Método | Rota | Descrição |
|--------|------|-----------|
| GET | `/servicos` | Serviços ativos |
| GET | `/disponibilidade?data=AAAA-MM-DD&servico_id=` | Barbeiros ativos com horários livres no dia |
| POST | `/agendamentos` | Marcar (nome, e-mail, telefone, barbeiro, serviço, início) |
| POST | `/agendamentos/{id}/cancelar` | Cancelar com o código |

## Área da Empresa

Uma página com cinco seções:

- **Agendamentos:** lista com filtros (barbeiro, cliente, dia, status) e botão para cancelar.
- **Clientes, Barbeiros, Serviços e Produtos:** criar, editar e **ativar/desativar** (sem excluir, para preservar o histórico). Inativos ficam ocultos, com a opção "Mostrar inativos". Barbeiro ou serviço inativo some da área do cliente e não recebe novos agendamentos.
- **Desativar barbeiro:** abre uma confirmação com o impacto: tempo na empresa, atendimentos já realizados, quantidade e valor dos agendamentos futuros, o próximo atendimento e a lista dos clientes afetados. Os agendamentos futuros **não são cancelados automaticamente**; a empresa decide o que fazer. A mesma informação está em `GET /barbeiros/{id}/impacto-desativacao`.
- **Barbeiros → Disponibilidade semanal:** janelas de trabalho por dia da semana. Sem janela, o barbeiro não aparece para os clientes.

O e-mail de cliente é **único** (409 ao repetir, sem diferenciar maiúsculas). Produtos são um catálogo (nome, preço e estoque); não há venda nem baixa de estoque. As rotas de gestão estão no Swagger da porta 8001.

`GET /agendamentos` é **paginado**: devolve `{itens, total, limite, deslocamento}`, com `limite` padrão 50 e máximo 200, e aceita `desde=AAAA-MM-DD`. A página da empresa mostra 25 por vez, só de hoje em diante por padrão, com botões Anterior e Próxima. Um índice em `agendamentos.inicio` mantém a consulta rápida mesmo com muitos registros.

### Códigos de resposta da API

| Código | Quando |
|--------|--------|
| 201 | Cadastro ou agendamento criado |
| 401 | Área da empresa sem senha ou com senha errada |
| 404 | Recurso inexistente (ou código de cancelamento inválido) |
| 409 | O barbeiro já tem um agendamento que se sobrepõe ao horário pedido, ou o e-mail do cliente já está cadastrado |
| 422 | Dados inválidos, preço com mais de 2 casas, horário fora da grade de slots, recurso inativo, fora da disponibilidade, no passado, data fora da janela do mês (área do cliente) ou cancelamento de horário que já passou |

Valores em dinheiro são enviados e devolvidos como texto com 2 casas (`"45.00"`).

Intervalos que apenas se encostam são permitidos. Agendamentos cancelados não bloqueiam o horário.

## Testes

```bash
make test   # API e serviços, sem navegador
make cov    # cobertura do pacote app
make e2e    # navegador (Playwright + Google Chrome)
```

Inclui testes de serviço, de API das duas áreas, de senha, de migração e um teste de **concorrência real** (cliente e empresa disputando o mesmo horário contra um arquivo SQLite compartilhado). Os testes de navegador (`tests/e2e/`) sobem as duas áreas com um banco temporário e exercitam as páginas de verdade: marcar e cancelar, janela de datas, cadastros, preço decimal, e-mail duplicado e a confirmação de desativação de barbeiro. Eles usam o Chrome instalado (ou o Chromium do Playwright, com `playwright install chromium`) e são ignorados pelo `make test`.

## Configuração

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `ADMIN_PASSWORD` | (obrigatória) | Senha da área da empresa. Sem ela a área **não sobe** |
| `DATABASE_URL` | `sqlite:///./barbearia.db` | Conexão com o banco |
| `SLOT_MINUTES` | `15` | Granularidade dos horários: só se marca em múltiplos dele |
| `TIMEZONE` | `America/Manaus` | Fuso usado para "agora" (o pacote `tzdata` garante o fuso no Windows) |
| `LOG_LEVEL` | `INFO` | Nível de log |
| `HOST`, `PORTA_CLIENTE`, `PORTA_ADMIN` | `127.0.0.1`, `8000`, `8001` | Endereço e portas do `make run` |

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
tests/                serviços, APIs, senha, migração e concorrência
```

Decisões de projeto:

- As regras ficam nos services e levantam exceções de domínio, que uma fábrica comum converte em 404/409/422.
- A checagem de conflito e a gravação acontecem **na mesma transação** (`BEGIN IMMEDIATE` no SQLite). Por isso duas requisições simultâneas para o mesmo horário, mesmo vindas das duas áreas, resultam em um 201 e o resto 409. Há um teste para isso.
- A confirmação roda em `BackgroundTasks` depois do commit; se falhar, o erro vai para o log e a resposta continua `201`.
- Relógio e notificador são injetados (`Depends`), o que deixa os testes determinísticos.
- Cada porta serve a própria página na mesma origem, então não há CORS.
- No banco, o `ativo` substitui a exclusão, e uma migração leve (`app/database.py`) acrescenta colunas novas a bancos antigos sem perder dados.

## Limitações conhecidas

Este é um projeto de estudo, não um produto pronto para produção:

- A senha da empresa usa HTTP Basic sobre HTTP puro: serve para desenvolvimento local. Não há usuários nem JWT, e não há HTTPS.
- A área do cliente não exige login: quem sabe o número e o código cancela aquele agendamento.
- Todos os horários são de Manaus, sem suporte a outros fusos; sem folgas ou feriados por data; um serviço por agendamento.
- Barbeiros cadastrados antes da coluna de data de cadastro aparecem como "tempo na empresa não registrado".
- Produtos não são vendidos nem baixam estoque; não há notificação de cancelamento.
- E-mail apenas simulado (log); o log contém nome e e-mail do cliente.
- SQLite compartilhado por dois processos serve para desenvolvimento. Em produção, o caminho seria PostgreSQL com `SELECT ... FOR UPDATE` ou uma constraint de exclusão no lugar do `BEGIN IMMEDIATE`.
- Os testes de navegador rodam só no Chrome/Chromium; Firefox e Safari não foram testados.
- O SQLite guarda preços como número real e os converte para `Decimal` na leitura (exato para 2 casas); um banco de produção usaria `NUMERIC`.
- No console do Windows, acentos do log podem aparecer errados; defina `PYTHONUTF8=1`.

## Como o projeto foi desenvolvido

A primeira versão (API única) seguiu um fluxo de especificação em fases (brainstorm, requisitos, design, construção e entrega). Os documentos estão em `.claude/sdd/archive/BARBERSHOP_SCHEDULING_API/`. A separação em duas áreas, a gestão de cadastros e o cancelamento pelo cliente foram acrescentados depois e ainda não passaram por esse ciclo.

## Licença

[MIT](LICENSE): você pode usar, copiar e modificar o código, mantendo o aviso de copyright.
