import {
  $,
  api,
  criarOpcao,
  elemento,
  falha,
  formatarDataHora,
  mensagem,
  preencherSelect,
  reais,
} from "/comum/util.js";

const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const INTERVALO_ATUALIZACAO_MS = 10000;

const NOME = { nome: "nome", rotulo: "Nome", tipo: "text", atributos: { minLength: 2, maxLength: 100 } };
const EMAIL = { nome: "email", rotulo: "E-mail", tipo: "email", atributos: {} };

const CADASTROS = [
  {
    id: "clientes",
    rota: "/clientes",
    titulo: "Clientes",
    singular: "cliente",
    campos: [NOME, EMAIL, { nome: "telefone", rotulo: "Telefone", tipo: "text", atributos: { minLength: 8, maxLength: 20 } }],
    colunas: [["Nome", (c) => c.nome], ["E-mail", (c) => c.email], ["Telefone", (c) => c.telefone]],
  },
  {
    id: "barbeiros",
    rota: "/barbeiros",
    titulo: "Barbeiros",
    singular: "barbeiro",
    campos: [NOME, EMAIL],
    colunas: [["Nome", (b) => b.nome], ["E-mail", (b) => b.email]],
  },
  {
    id: "servicos",
    rota: "/servicos",
    titulo: "Serviços",
    singular: "serviço",
    campos: [
      NOME,
      { nome: "duracao_minutos", rotulo: "Duração (min)", tipo: "number", numero: true, atributos: { min: 1, max: 480 } },
      { nome: "preco", rotulo: "Preço (R$)", tipo: "number", numero: true, atributos: { min: 0, step: "0.01" } },
    ],
    colunas: [["Nome", (s) => s.nome], ["Duração", (s) => `${s.duracao_minutos} min`], ["Preço", (s) => reais(s.preco)]],
  },
  {
    id: "produtos",
    rota: "/produtos",
    titulo: "Produtos",
    singular: "produto",
    campos: [
      NOME,
      { nome: "preco", rotulo: "Preço (R$)", tipo: "number", numero: true, atributos: { min: 0, step: "0.01" } },
      { nome: "estoque", rotulo: "Estoque", tipo: "number", numero: true, atributos: { min: 0, max: 100000 } },
    ],
    colunas: [["Nome", (p) => p.nome], ["Preço", (p) => reais(p.preco)], ["Estoque", (p) => String(p.estoque)]],
  },
];

const dados = { clientes: [], barbeiros: [], servicos: [], produtos: [] };
const estado = { agendamentos: [], janelaBarbeiroId: "" };

function nomePorId(lista, id) {
  const item = lista.find((entrada) => entrada.id === id);
  return item ? item.nome : `#${id}`;
}

function rotuloComStatus(item) {
  return item.ativo ? item.nome : `${item.nome} (inativo)`;
}

function selo(ativo, textoAtivo, textoInativo) {
  const classe = ativo ? "ativo" : "inativo";
  return elemento("span", { classe: `status ${classe}`, textContent: ativo ? textoAtivo : textoInativo });
}

function montarCadastro(cad) {
  const secao = $(`aba-${cad.id}`);
  const titulo = elemento("h2", { textContent: `Novo ${cad.singular}` });
  const campos = cad.campos.map((campo) =>
    elemento(
      "label",
      {},
      campo.rotulo,
      elemento("input", { name: campo.nome, type: campo.tipo, required: true, ...campo.atributos }),
    ),
  );
  const cancelarEdicaoBotao = elemento("button", { type: "button", textContent: "Cancelar edição", hidden: true });
  const salvar = elemento("button", { type: "submit", classe: "primario", textContent: "Salvar" });
  const formulario = elemento(
    "form",
    { classe: "grade-form formulario-cadastro" },
    campos,
    elemento("div", { classe: "botoes" }, salvar, cancelarEdicaoBotao),
  );
  const mostrarInativos = elemento("input", { type: "checkbox" });
  const barra = elemento("div", { classe: "barra" }, elemento("label", { classe: "inline" }, mostrarInativos, "Mostrar inativos"));
  const cabecalho = elemento(
    "tr",
    {},
    ["#", ...cad.colunas.map(([rotulo]) => rotulo), "Status", ""].map((texto) => elemento("th", { textContent: texto })),
  );
  const corpo = elemento("tbody");
  const tabela = elemento(
    "div",
    { classe: "tabela-rolagem" },
    elemento("table", {}, elemento("thead", {}, cabecalho), corpo),
  );

  cad.ui = { titulo, formulario, cancelarEdicaoBotao, mostrarInativos, corpo, editando: null };
  formulario.addEventListener("submit", (evento) => salvarCadastro(evento, cad));
  cancelarEdicaoBotao.addEventListener("click", () => sairDaEdicao(cad));
  mostrarInativos.addEventListener("change", () => renderizarTabela(cad));
  secao.append(titulo, formulario, barra, tabela);
}

function sairDaEdicao(cad) {
  cad.ui.editando = null;
  cad.ui.formulario.reset();
  cad.ui.titulo.textContent = `Novo ${cad.singular}`;
  cad.ui.cancelarEdicaoBotao.hidden = true;
}

function iniciarEdicao(cad, item) {
  cad.ui.editando = item.id;
  cad.campos.forEach((campo) => {
    cad.ui.formulario.elements[campo.nome].value = item[campo.nome];
  });
  cad.ui.titulo.textContent = `Editando ${cad.singular} #${item.id}`;
  cad.ui.cancelarEdicaoBotao.hidden = false;
  cad.ui.formulario.elements[cad.campos[0].nome].focus();
}

function corpoDoFormulario(cad) {
  const corpo = {};
  cad.campos.forEach((campo) => {
    const valor = cad.ui.formulario.elements[campo.nome].value;
    corpo[campo.nome] = campo.numero ? Number(valor) : valor;
  });
  return corpo;
}

async function salvarCadastro(evento, cad) {
  evento.preventDefault();
  const editando = cad.ui.editando;
  const resposta = editando
    ? await api("PUT", `${cad.rota}/${editando}`, corpoDoFormulario(cad))
    : await api("POST", cad.rota, corpoDoFormulario(cad));
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  sairDaEdicao(cad);
  await recarregarCadastros(cad);
  mensagem("sucesso", editando ? `${cad.singular} atualizado.` : `${cad.singular} cadastrado.`);
}

async function alternarAtivo(cad, item) {
  const resposta = await api("PATCH", `${cad.rota}/${item.id}/ativo`, { ativo: !item.ativo });
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  await recarregarCadastros(cad);
  mensagem("sucesso", `${cad.singular} ${item.ativo ? "desativado" : "reativado"}.`);
}

function renderizarTabela(cad) {
  const itens = dados[cad.id].filter((item) => item.ativo || cad.ui.mostrarInativos.checked);
  cad.ui.corpo.replaceChildren(
    ...itens.map((item) => {
      const linha = elemento("tr", { classe: item.ativo ? "" : "inativo" });
      linha.append(
        elemento("td", { textContent: String(item.id) }),
        ...cad.colunas.map(([, valor]) => elemento("td", { textContent: valor(item) })),
        elemento("td", {}, selo(item.ativo, "ativo", "inativo")),
        elemento(
          "td",
          {},
          elemento(
            "div",
            { classe: "acoes-linha" },
            elemento("button", { type: "button", classe: "pequeno", textContent: "Editar", aoClicar: () => iniciarEdicao(cad, item) }),
            elemento("button", {
              type: "button",
              classe: item.ativo ? "pequeno perigo" : "pequeno",
              textContent: item.ativo ? "Desativar" : "Reativar",
              aoClicar: () => alternarAtivo(cad, item),
            }),
          ),
        ),
      );
      return linha;
    }),
  );
}

async function carregarCadastro(cad) {
  const resposta = await api("GET", `${cad.rota}?incluir_inativos=true`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  dados[cad.id] = resposta.dados;
  renderizarTabela(cad);
}

function atualizarSelects() {
  preencherSelect($("filtro-barbeiro"), dados.barbeiros, rotuloComStatus, "Todos");
  preencherSelect($("filtro-cliente"), dados.clientes, rotuloComStatus, "Todos");
  const barbeirosAtivos = dados.barbeiros;
  preencherSelect($("janela-barbeiro"), barbeirosAtivos, rotuloComStatus, null);
  if (!estado.janelaBarbeiroId && barbeirosAtivos.length) estado.janelaBarbeiroId = String(barbeirosAtivos[0].id);
  $("janela-barbeiro").value = estado.janelaBarbeiroId;
}

async function recarregarCadastros(...afetados) {
  await Promise.all((afetados.length ? afetados : CADASTROS).map(carregarCadastro));
  atualizarSelects();
  renderizarAgendamentos();
  await carregarJanelas();
}

function montarJanelas() {
  const secao = $("aba-barbeiros");
  const seletor = elemento("select", { id: "janela-barbeiro" });
  const dia = elemento("select", { name: "dia_semana" });
  DIAS.forEach((nome, indice) => dia.append(criarOpcao(indice, nome)));
  const formulario = elemento(
    "form",
    { id: "form-janela", classe: "grade-form" },
    elemento("label", {}, "Dia da semana", dia),
    elemento("label", {}, "Das", elemento("input", { name: "hora_inicio", type: "time", value: "09:00", required: true })),
    elemento("label", {}, "Às", elemento("input", { name: "hora_fim", type: "time", value: "18:00", required: true })),
    elemento("button", { type: "submit", classe: "primario", textContent: "Adicionar janela" }),
  );
  const lista = elemento("ul", { id: "lista-janelas", classe: "lista-janelas" });
  secao.append(
    elemento(
      "div",
      { classe: "janelas-painel" },
      elemento("h2", { textContent: "Disponibilidade semanal" }),
      elemento("label", {}, "Barbeiro", seletor),
      lista,
      formulario,
    ),
  );
  seletor.addEventListener("change", () => {
    estado.janelaBarbeiroId = seletor.value;
    carregarJanelas();
  });
  formulario.addEventListener("submit", adicionarJanela);
}

async function carregarJanelas() {
  const lista = $("lista-janelas");
  lista.replaceChildren();
  const barbeiroId = estado.janelaBarbeiroId;
  if (!barbeiroId) return;
  const resposta = await api("GET", `/barbeiros/${barbeiroId}/disponibilidades`);
  if (!resposta.ok) return;
  if (!resposta.dados.length) {
    lista.append(elemento("li", { textContent: "Nenhuma janela cadastrada: o barbeiro não aparece para os clientes." }));
    return;
  }
  resposta.dados.forEach((janela) => {
    lista.append(
      elemento(
        "li",
        {},
        `${DIAS[janela.dia_semana]}: ${janela.hora_inicio.slice(0, 5)} - ${janela.hora_fim.slice(0, 5)}`,
        elemento("button", {
          type: "button",
          classe: "pequeno perigo",
          textContent: "Remover",
          aoClicar: () => removerJanela(janela.id),
        }),
      ),
    );
  });
}

async function adicionarJanela(evento) {
  evento.preventDefault();
  const formulario = evento.target;
  if (!estado.janelaBarbeiroId) {
    mensagem("aviso", "Cadastre um barbeiro primeiro.");
    return;
  }
  const resposta = await api("POST", `/barbeiros/${estado.janelaBarbeiroId}/disponibilidades`, {
    dia_semana: Number(formulario.elements.dia_semana.value),
    hora_inicio: `${formulario.elements.hora_inicio.value}:00`,
    hora_fim: `${formulario.elements.hora_fim.value}:00`,
  });
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  mensagem("sucesso", "Janela de disponibilidade adicionada.");
  await carregarJanelas();
}

async function removerJanela(janelaId) {
  const resposta = await api("DELETE", `/barbeiros/${estado.janelaBarbeiroId}/disponibilidades/${janelaId}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  mensagem("sucesso", "Janela removida.");
  await carregarJanelas();
}

function filtrosAtuais() {
  const filtros = new URLSearchParams();
  if ($("filtro-barbeiro").value) filtros.set("barbeiro_id", $("filtro-barbeiro").value);
  if ($("filtro-cliente").value) filtros.set("cliente_id", $("filtro-cliente").value);
  if ($("filtro-data").value) filtros.set("data", $("filtro-data").value);
  if ($("filtro-status").value) filtros.set("status", $("filtro-status").value);
  return filtros.toString();
}

async function carregarAgendamentos(evento) {
  if (evento) evento.preventDefault();
  const consulta = filtrosAtuais();
  const resposta = await api("GET", `/agendamentos${consulta ? `?${consulta}` : ""}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  estado.agendamentos = resposta.dados;
  if (referenciasDesconhecidas()) await recarregarCadastros();
  renderizarAgendamentos();
}

function referenciasDesconhecidas() {
  const conhecido = (lista, id) => lista.some((item) => item.id === id);
  return estado.agendamentos.some(
    (agendamento) =>
      !conhecido(dados.clientes, agendamento.cliente_id) ||
      !conhecido(dados.barbeiros, agendamento.barbeiro_id) ||
      !conhecido(dados.servicos, agendamento.servico_id),
  );
}

function renderizarAgendamentos() {
  const itens = estado.agendamentos;
  $("resumo-agendamentos").textContent = `${itens.length} agendamento(s)`;
  $("lista-agendamentos").replaceChildren(
    ...itens.map((agendamento) => {
      const linha = elemento("tr");
      linha.append(
        elemento("td", { textContent: String(agendamento.id) }),
        elemento("td", { textContent: formatarDataHora(agendamento.inicio) }),
        elemento("td", { textContent: agendamento.fim.slice(11, 16) }),
        elemento("td", { textContent: nomePorId(dados.clientes, agendamento.cliente_id) }),
        elemento("td", { textContent: nomePorId(dados.barbeiros, agendamento.barbeiro_id) }),
        elemento("td", { textContent: nomePorId(dados.servicos, agendamento.servico_id) }),
        elemento(
          "td",
          {},
          elemento("span", { classe: `status ${agendamento.status}`, textContent: agendamento.status }),
        ),
        elemento(
          "td",
          {},
          agendamento.status === "agendado"
            ? elemento("button", {
                type: "button",
                classe: "pequeno perigo",
                textContent: "Cancelar",
                aoClicar: () => cancelarAgendamento(agendamento.id),
              })
            : "",
        ),
      );
      return linha;
    }),
  );
}

async function cancelarAgendamento(id) {
  if (!confirm(`Cancelar o agendamento #${id}?`)) return;
  const resposta = await api("DELETE", `/agendamentos/${id}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  mensagem("sucesso", `Agendamento #${id} cancelado.`);
  await carregarAgendamentos();
}

function trocarAba(nome) {
  $("mensagem").hidden = true;
  document.querySelectorAll(".aba").forEach((aba) => aba.classList.toggle("ativa", aba.dataset.aba === nome));
  document.querySelectorAll(".painel").forEach((painel) => {
    painel.hidden = painel.id !== `aba-${nome}`;
  });
  if (nome === "agendamentos") carregarAgendamentos();
  const cadastro = CADASTROS.find((item) => item.id === nome);
  if (cadastro) recarregarCadastros(cadastro);
}

function agendamentosVisiveis() {
  return !$("aba-agendamentos").hidden && document.visibilityState === "visible";
}

async function iniciar() {
  CADASTROS.forEach(montarCadastro);
  montarJanelas();

  document.querySelectorAll(".aba").forEach((aba) => aba.addEventListener("click", () => trocarAba(aba.dataset.aba)));
  $("form-filtro").addEventListener("submit", carregarAgendamentos);
  $("limpar-filtro").addEventListener("click", () => {
    $("form-filtro").reset();
    carregarAgendamentos();
  });
  $("atualizar").addEventListener("click", () => carregarAgendamentos());
  setInterval(() => {
    if ($("auto-atualizar").checked && agendamentosVisiveis()) carregarAgendamentos();
  }, INTERVALO_ATUALIZACAO_MS);

  await recarregarCadastros();
  await carregarAgendamentos();
}

iniciar();
