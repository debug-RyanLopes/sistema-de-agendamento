import {
  $,
  STATUS_ROTULO,
  agoraLocalIso,
  api,
  carregarConfiguracao,
  criarOpcao,
  dataLocalHoje,
  elemento,
  falha,
  formatarData,
  formatarDataHora,
  formatarTelefone,
  mensagem,
  preencherSelect,
  reais,
} from "/comum/util.js";

const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];
const INTERVALO_ATUALIZACAO_MS = 10000;
const ITENS_POR_PAGINA = 25;
const CADASTROS_POR_PAGINA = 25;

const NOME = { nome: "nome", rotulo: "Nome", tipo: "text", atributos: { minLength: 2, maxLength: 100 } };
const EMAIL = { nome: "email", rotulo: "E-mail", tipo: "email", atributos: {} };

const CADASTROS = [
  {
    id: "clientes",
    rota: "/clientes",
    titulo: "Clientes",
    singular: "cliente",
    campos: [NOME, EMAIL, { nome: "telefone", rotulo: "Telefone", tipo: "text", atributos: { minLength: 10, maxLength: 20, placeholder: "(92) 91234-5678" } }],
    colunas: [["Nome", (c) => c.nome], ["E-mail", (c) => c.email], ["Telefone", (c) => formatarTelefone(c.telefone)]],
    busca: true,
    anonimizar: true,
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
      { nome: "preco", rotulo: "Preço (R$)", tipo: "number", dinheiro: true, atributos: { min: 0, step: "0.01" } },
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
      { nome: "preco", rotulo: "Preço (R$)", tipo: "number", dinheiro: true, atributos: { min: 0, step: "0.01" } },
      { nome: "estoque", rotulo: "Estoque", tipo: "number", numero: true, atributos: { min: 0, max: 100000 } },
    ],
    colunas: [["Nome", (p) => p.nome], ["Preço", (p) => reais(p.preco)], ["Estoque", (p) => String(p.estoque)]],
  },
];

const dados = { clientes: [], barbeiros: [], servicos: [], produtos: [] };
const estado = {
  usuario: null,
  agendamentos: [],
  total: 0,
  deslocamento: 0,
  janelaBarbeiroId: "",
  clienteFiltroId: null,
  agendaData: null,
};

const dono = () => estado.usuario?.papel === "dono";

function nomePorId(lista, id) {
  const item = lista.find((entrada) => entrada.id === id);
  return item ? item.nome : `#${id}`;
}

function rotuloComStatus(item) {
  return item.ativo ? item.nome : `${item.nome} (inativo)`;
}

function selo(texto, classe) {
  return elemento("span", { classe: `status ${classe}`, textContent: texto });
}

// --- cadastros ---------------------------------------------------------------------------

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
  const busca = elemento("input", { type: "search", placeholder: "Buscar por nome, e-mail ou telefone", "aria-label": "Buscar" });
  const barra = elemento(
    "div",
    { classe: "barra-busca" },
    cad.busca ? elemento("label", {}, "Buscar", busca) : "",
    elemento("label", { classe: "inline" }, mostrarInativos, "Mostrar inativos"),
  );
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
  const anterior = elemento("button", { type: "button", classe: "pequeno", textContent: "Anterior" });
  const proxima = elemento("button", { type: "button", classe: "pequeno", textContent: "Próxima" });
  const info = elemento("span", { classe: "ajuda" });
  const paginacao = elemento("div", { classe: "paginacao" }, anterior, info, proxima);

  cad.ui = { titulo, formulario, cancelarEdicaoBotao, mostrarInativos, busca, corpo, info, anterior, proxima, editando: null, deslocamento: 0, total: 0 };
  formulario.addEventListener("submit", (evento) => salvarCadastro(evento, cad));
  cancelarEdicaoBotao.addEventListener("click", () => sairDaEdicao(cad));
  mostrarInativos.addEventListener("change", () => carregarCadastro(cad, { primeiraPagina: true }));
  let temporizador = null;
  busca.addEventListener("input", () => {
    clearTimeout(temporizador);
    temporizador = setTimeout(() => carregarCadastro(cad, { primeiraPagina: true }), 300);
  });
  anterior.addEventListener("click", () => {
    cad.ui.deslocamento = Math.max(0, cad.ui.deslocamento - CADASTROS_POR_PAGINA);
    carregarCadastro(cad);
  });
  proxima.addEventListener("click", () => {
    cad.ui.deslocamento += CADASTROS_POR_PAGINA;
    carregarCadastro(cad);
  });
  secao.append(titulo, formulario, barra, paginacao, tabela);
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
    if (campo.dinheiro) corpo[campo.nome] = valor.replace(",", ".");
    else corpo[campo.nome] = campo.numero ? Number(valor) : valor;
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

function tempoNaEmpresa(dias) {
  if (dias === null) return "não registrado";
  if (dias < 1) return "cadastrado hoje";
  if (dias < 60) return `${dias} ${dias === 1 ? "dia" : "dias"}`;
  const meses = Math.floor(dias / 30.44);
  if (meses < 24) return `${meses} meses`;
  const anos = Math.floor(meses / 12);
  const restante = meses % 12;
  const textoAnos = `${anos} anos`;
  return restante ? `${textoAnos} e ${restante} ${restante === 1 ? "mês" : "meses"}` : textoAnos;
}

function resumoDoImpacto(impacto) {
  const linhas = [
    ["Tempo na empresa", tempoNaEmpresa(impacto.dias_na_empresa)],
    ["Atendimentos já realizados", String(impacto.atendimentos_realizados)],
    ["Faltas de clientes", String(impacto.faltas ?? 0)],
    ["Agendamentos futuros", String(impacto.total_futuros)],
  ];
  if (impacto.total_futuros) {
    linhas.push(["Valor agendado", reais(impacto.valor_futuro)]);
    linhas.push(["Próximo atendimento", formatarDataHora(impacto.proximo_atendimento)]);
  }
  const caixa = elemento(
    "dl",
    { classe: "resumo-impacto" },
    ...linhas.map(([rotulo, valor]) => elemento("div", {}, elemento("dt", { textContent: rotulo }), elemento("dd", { textContent: valor }))),
  );
  const partes = [caixa];
  if (impacto.total_futuros) {
    partes.push(
      elemento("p", {
        classe: "aviso-impacto",
        textContent:
          "Os agendamentos abaixo continuam marcados. Desativar não os cancela: avise os clientes " +
          "ou cancele-os na aba Agendamentos.",
      }),
      elemento(
        "ul",
        { classe: "lista-impacto" },
        ...impacto.agendamentos_futuros.map((a) =>
          elemento("li", { textContent: `${formatarDataHora(a.inicio)} - ${a.cliente} (${a.servico})` }),
        ),
      ),
    );
  }
  return partes;
}

function confirmarDesativacao(impacto) {
  const dialogo = $("dialogo-desativar");
  $("dialogo-titulo").textContent = `Desativar ${impacto.nome}?`;
  $("dialogo-corpo").replaceChildren(...resumoDoImpacto(impacto));
  return new Promise((resolver) => {
    dialogo.addEventListener("close", () => resolver(dialogo.returnValue === "confirmar"), { once: true });
    dialogo.returnValue = "voltar";
    dialogo.showModal();
  });
}

async function alternarAtivo(cad, item) {
  if (cad.id === "barbeiros" && item.ativo) {
    const impacto = await api("GET", `/barbeiros/${item.id}/impacto-desativacao`);
    if (!impacto.ok) {
      falha(impacto);
      return;
    }
    if (!(await confirmarDesativacao(impacto.dados))) return;
  }
  const resposta = await api("PATCH", `${cad.rota}/${item.id}/ativo`, { ativo: !item.ativo });
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  await recarregarCadastros(cad);
  mensagem("sucesso", `${cad.singular} ${item.ativo ? "desativado" : "reativado"}.`);
}

async function anonimizarCliente(cad, item) {
  if (!confirm(`Apagar os dados pessoais de ${item.nome}? O histórico de agendamentos é mantido, mas nome, e-mail e telefone são removidos para sempre.`)) return;
  const resposta = await api("POST", `${cad.rota}/${item.id}/anonimizar`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  await recarregarCadastros(cad);
  mensagem("sucesso", "Dados pessoais apagados.");
}

function renderizarTabela(cad) {
  const itens = cad.ui.pagina ?? [];
  cad.ui.corpo.replaceChildren(
    ...itens.map((item) => {
      const linha = elemento("tr", { classe: item.ativo ? "" : "inativo" });
      const acoes = [
        elemento("button", { type: "button", classe: "pequeno", textContent: "Editar", aoClicar: () => iniciarEdicao(cad, item), disabled: Boolean(item.anonimizado_em) }),
        elemento("button", {
          type: "button",
          classe: item.ativo ? "pequeno perigo" : "pequeno",
          textContent: item.ativo ? "Desativar" : "Reativar",
          aoClicar: () => alternarAtivo(cad, item),
          disabled: Boolean(item.anonimizado_em),
        }),
      ];
      if (cad.anonimizar && !item.anonimizado_em) {
        acoes.push(elemento("button", { type: "button", classe: "pequeno perigo", textContent: "Apagar dados", aoClicar: () => anonimizarCliente(cad, item) }));
      }
      linha.append(
        elemento("td", { textContent: String(item.id) }),
        ...cad.colunas.map(([, valor]) => elemento("td", { textContent: valor(item) })),
        elemento("td", {}, item.anonimizado_em ? selo("dados apagados", "inativo") : selo(item.ativo ? "ativo" : "inativo", item.ativo ? "ativo" : "inativo")),
        elemento("td", {}, elemento("div", { classe: "acoes-linha" }, ...acoes)),
      );
      return linha;
    }),
  );
  const primeiro = cad.ui.total ? cad.ui.deslocamento + 1 : 0;
  const ultimo = cad.ui.deslocamento + itens.length;
  cad.ui.info.textContent = cad.ui.total ? `Mostrando ${primeiro}–${ultimo} de ${cad.ui.total}` : "Nenhum registro";
  cad.ui.anterior.disabled = cad.ui.deslocamento === 0;
  cad.ui.proxima.disabled = ultimo >= cad.ui.total;
}

async function carregarCadastro(cad, { primeiraPagina = false } = {}) {
  if (primeiraPagina) cad.ui.deslocamento = 0;
  const parametros = new URLSearchParams({ limite: String(CADASTROS_POR_PAGINA), deslocamento: String(cad.ui.deslocamento), ordem: "recentes" });
  if (cad.ui.mostrarInativos.checked) parametros.set("incluir_inativos", "true");
  if (cad.busca && cad.ui.busca.value.trim()) parametros.set("busca", cad.ui.busca.value.trim());
  const resposta = await api("GET", `${cad.rota}?${parametros}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  cad.ui.pagina = resposta.dados;
  cad.ui.total = Number(resposta.cabecalhos?.get("x-total-count") ?? resposta.dados.length);
  renderizarTabela(cad);
}

async function carregarReferencias() {
  // Listas completas (sem paginação) para nomes em tabelas e seletores; clientes são buscados sob demanda.
  for (const chave of ["barbeiros", "servicos", "produtos"]) {
    const resposta = await api("GET", `/${chave}?incluir_inativos=true`);
    if (resposta.ok) dados[chave] = resposta.dados;
  }
}

function atualizarSelects() {
  preencherSelect($("filtro-barbeiro"), dados.barbeiros, rotuloComStatus, "Todos");
  const seletorJanela = $("janela-barbeiro");
  if (seletorJanela) {
    preencherSelect(seletorJanela, dados.barbeiros, rotuloComStatus, null);
    if (!estado.janelaBarbeiroId && dados.barbeiros.length) estado.janelaBarbeiroId = String(dados.barbeiros[0].id);
    seletorJanela.value = estado.janelaBarbeiroId;
  }
  const seletorBloqueio = $("bloqueio-barbeiro");
  if (seletorBloqueio) preencherSelect(seletorBloqueio, dados.barbeiros.filter((b) => b.ativo), (b) => b.nome, "Toda a barbearia");
  const seletorVenda = document.querySelector("#aba-vendas select[name=produto_id]");
  if (seletorVenda) preencherSelect(seletorVenda, dados.produtos.filter((p) => p.ativo), (p) => `${p.nome} (${p.estoque} em estoque)`, "Selecione...");
  const seletorUsuario = $("usuario-barbeiro");
  if (seletorUsuario) preencherSelect(seletorUsuario, dados.barbeiros.filter((b) => b.ativo), (b) => b.nome, "Nenhum (dono)");
}

async function recarregarCadastros(...afetados) {
  await carregarReferencias();
  await Promise.all((afetados.length ? afetados : CADASTROS.filter((cad) => !$(`aba-${cad.id}`).hidden)).map((cad) => carregarCadastro(cad)));
  atualizarSelects();
  renderizarAgendamentos();
  if (dono()) await carregarJanelas();
}

// --- disponibilidade semanal --------------------------------------------------------------

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
      elemento("p", { classe: "ajuda", textContent: "Janelas que se encostam (9-12 e 12-18) valem como uma só. Folgas e feriados ficam na aba Bloqueios." }),
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
  if (!lista) return;
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
        elemento("button", { type: "button", classe: "pequeno perigo", textContent: "Remover", aoClicar: () => removerJanela(janela.id) }),
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

// --- agendamentos (tabela) -----------------------------------------------------------------

async function sugerirClientes(texto) {
  const lista = $("lista-clientes");
  if (texto.trim().length < 2) {
    lista.replaceChildren();
    return;
  }
  const resposta = await api("GET", `/clientes?busca=${encodeURIComponent(texto.trim())}&incluir_inativos=true&limite=15`);
  if (!resposta.ok) return;
  dados.clientes = [...dados.clientes, ...resposta.dados.filter((c) => !dados.clientes.some((d) => d.id === c.id))];
  lista.replaceChildren(...resposta.dados.map((c) => criarOpcao(`${c.nome} <${c.email}>`, `#${c.id}`)));
}

function clienteFiltrado() {
  const texto = $("filtro-cliente").value.trim();
  if (!texto) return null;
  const direto = texto.match(/^#?(\d+)$/);
  if (direto) return Number(direto[1]);
  const porEmail = texto.match(/<([^>]+)>/);
  const achado = dados.clientes.find((c) => (porEmail ? c.email === porEmail[1] : c.nome === texto || c.email === texto));
  return achado ? achado.id : null;
}

function filtrosAtuais() {
  const filtros = new URLSearchParams();
  if ($("filtro-barbeiro").value) filtros.set("barbeiro_id", $("filtro-barbeiro").value);
  const clienteId = clienteFiltrado();
  if (clienteId) filtros.set("cliente_id", String(clienteId));
  if ($("filtro-data").value) filtros.set("data", $("filtro-data").value);
  if ($("filtro-status").value) filtros.set("status", $("filtro-status").value);
  if ($("filtro-futuros").checked) filtros.set("desde", dataLocalHoje());
  return filtros.toString();
}

async function carregarAgendamentos(evento, { primeiraPagina = false } = {}) {
  if (evento) evento.preventDefault();
  if (primeiraPagina) estado.deslocamento = 0;
  const filtros = new URLSearchParams(filtrosAtuais());
  filtros.set("limite", String(ITENS_POR_PAGINA));
  filtros.set("deslocamento", String(estado.deslocamento));
  const resposta = await api("GET", `/agendamentos?${filtros}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  if (!resposta.dados.itens.length && estado.deslocamento > 0) {
    estado.deslocamento = Math.max(0, (Math.ceil(resposta.dados.total / ITENS_POR_PAGINA) - 1) * ITENS_POR_PAGINA);
    await carregarAgendamentos();
    return;
  }
  estado.agendamentos = resposta.dados.itens;
  estado.total = resposta.dados.total;
  await completarNomesDeClientes(estado.agendamentos);
  renderizarAgendamentos();
}

async function completarNomesDeClientes(itens) {
  const faltantes = [...new Set(itens.map((a) => a.cliente_id))].filter((id) => !dados.clientes.some((c) => c.id === id));
  const buscados = await Promise.all(faltantes.map((id) => api("GET", `/clientes/${id}`)));
  buscados.forEach((resposta) => {
    if (resposta.ok) dados.clientes.push(resposta.dados);
  });
}

function pedirNovoHorario(agendamento) {
  const dialogo = $("dialogo-remarcar");
  $("remarcar-data").value = agendamento.inicio.slice(0, 10);
  $("remarcar-hora").value = agendamento.inicio.slice(11, 16);
  return new Promise((resolver) => {
    dialogo.addEventListener(
      "close",
      () => resolver(dialogo.returnValue === "confirmar" ? `${$("remarcar-data").value}T${$("remarcar-hora").value}:00` : null),
      { once: true },
    );
    dialogo.returnValue = "voltar";
    dialogo.showModal();
  });
}

async function remarcarAgendamento(agendamento) {
  const novoInicio = await pedirNovoHorario(agendamento);
  if (!novoInicio) return;
  const resposta = await api("POST", `/agendamentos/${agendamento.id}/reagendar`, { inicio: novoInicio });
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  mensagem("sucesso", `Agendamento #${agendamento.id} remarcado para ${formatarDataHora(novoInicio)}.`);
  await carregarAgendamentos();
}

async function mudarStatus(agendamento, status) {
  const resposta = await api("PATCH", `/agendamentos/${agendamento.id}/status`, { status });
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  mensagem("sucesso", `Agendamento #${agendamento.id} marcado como ${STATUS_ROTULO[status]}.`);
  await carregarAgendamentos();
}

function acoesDoAgendamento(agendamento) {
  if (agendamento.status !== "agendado") return [];
  const passou = agendamento.inicio.slice(0, 16) <= agoraLocalIso();
  if (passou) {
    return [
      elemento("button", { type: "button", classe: "pequeno", textContent: "Concluído", aoClicar: () => mudarStatus(agendamento, "concluido") }),
      elemento("button", { type: "button", classe: "pequeno perigo", textContent: "Faltou", aoClicar: () => mudarStatus(agendamento, "nao_compareceu") }),
    ];
  }
  return [
    elemento("button", { type: "button", classe: "pequeno", textContent: "Remarcar", aoClicar: () => remarcarAgendamento(agendamento) }),
    elemento("button", { type: "button", classe: "pequeno perigo", textContent: "Cancelar", aoClicar: () => cancelarAgendamento(agendamento.id) }),
  ];
}

function renderizarAgendamentos() {
  const itens = estado.agendamentos;
  const primeiro = estado.total ? estado.deslocamento + 1 : 0;
  const ultimo = estado.deslocamento + itens.length;
  $("pag-info").textContent = estado.total ? `Mostrando ${primeiro}–${ultimo} de ${estado.total}` : "Nenhum agendamento";
  $("pag-anterior").disabled = estado.deslocamento === 0;
  $("pag-proxima").disabled = ultimo >= estado.total;
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
        elemento("td", { textContent: agendamento.origem ?? "-" }),
        elemento("td", {}, selo(STATUS_ROTULO[agendamento.status] ?? agendamento.status, agendamento.status)),
        elemento("td", {}, elemento("div", { classe: "acoes-linha" }, ...acoesDoAgendamento(agendamento))),
      );
      return linha;
    }),
  );
}

async function cancelarAgendamento(id) {
  const motivo = prompt(`Cancelar o agendamento #${id}? Informe o motivo (opcional):`);
  if (motivo === null) return;
  const parametro = motivo.trim() ? `?motivo=${encodeURIComponent(motivo.trim())}` : "";
  const resposta = await api("DELETE", `/agendamentos/${id}${parametro}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  mensagem("sucesso", `Agendamento #${id} cancelado. O cliente recebe o aviso por e-mail.`);
  await carregarAgendamentos();
}

function exportarCsv() {
  window.open(`/relatorios/agendamentos.csv?${filtrosAtuais()}`, "_blank");
}

// --- agenda do dia -----------------------------------------------------------------------

async function carregarAgenda() {
  const data = estado.agendaData ?? dataLocalHoje();
  estado.agendaData = data;
  $("agenda-data").value = data;
  const [agendamentos, bloqueios] = await Promise.all([
    api("GET", `/agendamentos?data=${data}&limite=200`),
    api("GET", `/bloqueios?desde=${data}`),
  ]);
  if (!agendamentos.ok) {
    falha(agendamentos);
    return;
  }
  const itens = agendamentos.dados.itens;
  await completarNomesDeClientes(itens);
  const doDia = bloqueios.ok ? bloqueios.dados.filter((b) => b.data === data) : [];
  const barbeiros = dono() ? dados.barbeiros.filter((b) => b.ativo) : dados.barbeiros.filter((b) => b.id === estado.usuario.barbeiro_id);
  $("agenda-info").textContent = `${itens.filter((a) => a.status === "agendado").length} agendamento(s) ativos em ${formatarData(data)}`;
  $("agenda-colunas").replaceChildren(
    ...barbeiros.map((barbeiro) => {
      const coluna = elemento("div", { classe: "agenda-coluna" }, elemento("h3", { textContent: barbeiro.nome }));
      doDia
        .filter((b) => b.barbeiro_id === null || b.barbeiro_id === barbeiro.id)
        .forEach((b) =>
          coluna.append(
            elemento("div", { classe: "agenda-item bloqueio" },
              b.hora_inicio ? `${b.hora_inicio.slice(0, 5)} - ${b.hora_fim.slice(0, 5)}` : "Dia inteiro",
              elemento("small", { textContent: b.motivo ?? (b.barbeiro_id === null ? "barbearia fechada" : "folga") })),
          ),
        );
      const proprios = itens.filter((a) => a.barbeiro_id === barbeiro.id);
      if (!proprios.length && !coluna.querySelector(".bloqueio")) coluna.append(elemento("p", { classe: "janela", textContent: "Sem agendamentos." }));
      proprios.forEach((a) =>
        coluna.append(
          elemento(
            "div",
            { classe: `agenda-item ${a.status}` },
            `${a.inicio.slice(11, 16)} - ${a.fim.slice(11, 16)} ${nomePorId(dados.clientes, a.cliente_id)}`,
            elemento("small", { textContent: `${nomePorId(dados.servicos, a.servico_id)} · ${STATUS_ROTULO[a.status] ?? a.status}` }),
          ),
        ),
      );
      return coluna;
    }),
  );
}

function mudarDiaDaAgenda(dias) {
  const atual = new Date(`${estado.agendaData ?? dataLocalHoje()}T12:00:00Z`);
  atual.setUTCDate(atual.getUTCDate() + dias);
  estado.agendaData = atual.toISOString().slice(0, 10);
  carregarAgenda();
}

// --- bloqueios -----------------------------------------------------------------------------

function montarBloqueios() {
  const secao = $("aba-bloqueios");
  const barbeiro = elemento("select", { id: "bloqueio-barbeiro", name: "barbeiro_id" });
  const diaInteiro = elemento("input", { type: "checkbox", name: "dia_inteiro", checked: true });
  const horaInicio = elemento("input", { name: "hora_inicio", type: "time", value: "12:00", disabled: true });
  const horaFim = elemento("input", { name: "hora_fim", type: "time", value: "13:00", disabled: true });
  diaInteiro.addEventListener("change", () => {
    horaInicio.disabled = diaInteiro.checked;
    horaFim.disabled = diaInteiro.checked;
  });
  const formulario = elemento(
    "form",
    { id: "form-bloqueio", classe: "grade-form" },
    elemento("label", {}, "Quem", barbeiro),
    elemento("label", {}, "Data", elemento("input", { name: "data", type: "date", required: true, value: dataLocalHoje() })),
    elemento("label", { classe: "inline" }, diaInteiro, "Dia inteiro"),
    elemento("label", {}, "Das", horaInicio),
    elemento("label", {}, "Às", horaFim),
    elemento("label", {}, "Motivo", elemento("input", { name: "motivo", maxLength: 100, placeholder: "Feriado, folga, consulta médica..." })),
    elemento("button", { type: "submit", classe: "primario", textContent: "Adicionar bloqueio" }),
  );
  const lista = elemento("ul", { id: "lista-bloqueios", classe: "lista-janelas" });
  secao.append(
    elemento("h2", { textContent: "Folgas, feriados e bloqueios pontuais" }),
    elemento("p", { classe: "ajuda", textContent: "Um bloqueio tira o horário da agenda sem mexer na disponibilidade semanal. Sem barbeiro, vale para toda a barbearia." }),
    dono() ? formulario : "",
    elemento("h2", { textContent: "Próximos bloqueios" }),
    lista,
  );
  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const f = formulario.elements;
    const resposta = await api("POST", "/bloqueios", {
      barbeiro_id: f.barbeiro_id.value ? Number(f.barbeiro_id.value) : null,
      data: f.data.value,
      hora_inicio: diaInteiro.checked ? null : `${horaInicio.value}:00`,
      hora_fim: diaInteiro.checked ? null : `${horaFim.value}:00`,
      motivo: f.motivo.value.trim() || null,
    });
    if (!resposta.ok) {
      falha(resposta);
      return;
    }
    mensagem("sucesso", "Bloqueio adicionado.");
    await carregarBloqueios();
  });
}

async function carregarBloqueios() {
  const lista = $("lista-bloqueios");
  lista.replaceChildren();
  const resposta = await api("GET", `/bloqueios?desde=${dataLocalHoje()}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  if (!resposta.dados.length) {
    lista.append(elemento("li", { textContent: "Nenhum bloqueio futuro." }));
    return;
  }
  resposta.dados.forEach((b) => {
    const quem = b.barbeiro_id === null ? "Toda a barbearia" : nomePorId(dados.barbeiros, b.barbeiro_id);
    const quando = b.hora_inicio ? `${b.hora_inicio.slice(0, 5)} - ${b.hora_fim.slice(0, 5)}` : "dia inteiro";
    lista.append(
      elemento(
        "li",
        {},
        `${formatarData(b.data)} · ${quem} · ${quando}${b.motivo ? ` · ${b.motivo}` : ""}`,
        dono()
          ? elemento("button", {
              type: "button",
              classe: "pequeno perigo",
              textContent: "Remover",
              aoClicar: async () => {
                const removido = await api("DELETE", `/bloqueios/${b.id}`);
                if (!removido.ok) {
                  falha(removido);
                  return;
                }
                await carregarBloqueios();
              },
            })
          : "",
      ),
    );
  });
}

// --- vendas --------------------------------------------------------------------------------

function montarVendas() {
  const secao = $("aba-vendas");
  const linhas = elemento("div", { classe: "linhas-venda" });
  const total = elemento("p", { classe: "total-venda", textContent: "Total: R$ 0,00" });
  const observacao = elemento("input", { name: "observacao", maxLength: 200, placeholder: "Opcional" });

  function novaLinha() {
    const produto = elemento("select", { name: "produto_id", required: true });
    preencherSelect(produto, dados.produtos.filter((p) => p.ativo), (p) => `${p.nome} (${p.estoque} em estoque)`, "Selecione...");
    const quantidade = elemento("input", { name: "quantidade", type: "number", min: 1, max: 1000, value: 1, required: true });
    const linha = elemento(
      "div",
      { classe: "linha-venda" },
      elemento("label", {}, "Produto", produto),
      elemento("label", {}, "Qtd.", quantidade),
      elemento("button", { type: "button", classe: "pequeno", textContent: "Remover", aoClicar: () => { linha.remove(); atualizarTotal(); } }),
    );
    produto.addEventListener("change", atualizarTotal);
    quantidade.addEventListener("input", atualizarTotal);
    linhas.append(linha);
  }

  function itens() {
    return [...linhas.querySelectorAll(".linha-venda")]
      .map((linha) => ({ produto_id: Number(linha.querySelector("select").value), quantidade: Number(linha.querySelector("input").value) }))
      .filter((item) => item.produto_id);
  }

  function atualizarTotal() {
    const soma = itens().reduce((acumulado, item) => {
      const produto = dados.produtos.find((p) => p.id === item.produto_id);
      return acumulado + (produto ? Number(produto.preco) * item.quantidade : 0);
    }, 0);
    total.textContent = `Total: ${reais(soma)}`;
  }

  const formulario = elemento(
    "form",
    { id: "form-venda" },
    linhas,
    elemento("div", { classe: "barra" },
      elemento("button", { type: "button", classe: "pequeno", textContent: "+ Produto", aoClicar: novaLinha }),
      elemento("label", {}, "Observação", observacao)),
    total,
    elemento("button", { type: "submit", classe: "primario", textContent: "Registrar venda" }),
  );
  const tabela = elemento("tbody", { id: "lista-vendas" });
  secao.append(
    elemento("h2", { textContent: "Nova venda" }),
    elemento("p", { classe: "ajuda", textContent: "A venda baixa o estoque dos produtos. Se faltar estoque de algum item, nada é gravado." }),
    formulario,
    elemento("h2", { textContent: "Vendas recentes" }),
    elemento("div", { classe: "tabela-rolagem" },
      elemento("table", {},
        elemento("thead", {}, elemento("tr", {}, ...["#", "Quando", "Itens", "Total", "Observação"].map((t) => elemento("th", { textContent: t })))),
        tabela)),
  );
  novaLinha();
  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const resposta = await api("POST", "/vendas", { itens: itens(), observacao: observacao.value.trim() || null });
    if (!resposta.ok) {
      falha(resposta);
      return;
    }
    mensagem("sucesso", `Venda #${resposta.dados.id} registrada: ${reais(resposta.dados.total)}.`);
    linhas.replaceChildren();
    observacao.value = "";
    await carregarReferencias();
    atualizarSelects();
    novaLinha();
    atualizarTotal();
    await carregarVendas();
  });
}

async function carregarVendas() {
  const resposta = await api("GET", "/vendas?limite=50");
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  $("lista-vendas").replaceChildren(
    ...resposta.dados.map((venda) =>
      elemento(
        "tr",
        {},
        elemento("td", { textContent: String(venda.id) }),
        elemento("td", { textContent: formatarDataHora(venda.criado_em) }),
        elemento("td", { textContent: venda.itens.map((i) => `${i.quantidade}x ${nomePorId(dados.produtos, i.produto_id)}`).join(", ") }),
        elemento("td", { textContent: reais(venda.total) }),
        elemento("td", { textContent: venda.observacao ?? "" }),
      ),
    ),
  );
}

// --- relatórios ----------------------------------------------------------------------------

function montarRelatorios() {
  const secao = $("aba-relatorios");
  const hoje = dataLocalHoje();
  const desde = elemento("input", { id: "relatorio-desde", type: "date", value: `${hoje.slice(0, 8)}01`, required: true });
  const ate = elemento("input", { id: "relatorio-ate", type: "date", value: hoje, required: true });
  const formulario = elemento(
    "form",
    { id: "form-relatorio", classe: "grade-form" },
    elemento("label", {}, "De", desde),
    elemento("label", {}, "Até", ate),
    elemento("button", { type: "submit", classe: "primario", textContent: "Calcular" }),
  );
  secao.append(
    elemento("h2", { textContent: "Ocupação e receita" }),
    formulario,
    elemento("dl", { id: "cartoes-resumo", classe: "cartoes-resumo" }),
    elemento("div", { classe: "tabela-rolagem" },
      elemento("table", {},
        elemento("thead", {}, elemento("tr", {}, ...["Barbeiro", "Agendados", "Concluídos", "Faltas", "Cancelados", "Receita", "Ocupação"].map((t) => elemento("th", { textContent: t })))),
        elemento("tbody", { id: "lista-relatorio" }))),
  );
  formulario.addEventListener("submit", (evento) => {
    evento.preventDefault();
    carregarRelatorio();
  });
}

function cartaoResumo(rotulo, valor) {
  return elemento("div", { classe: "cartao-resumo" }, elemento("dt", { textContent: rotulo }), elemento("dd", { textContent: valor }));
}

async function carregarRelatorio() {
  const resposta = await api("GET", `/relatorios/resumo?desde=${$("relatorio-desde").value}&ate=${$("relatorio-ate").value}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  const r = resposta.dados;
  const ocupados = r.barbeiros.reduce((s, b) => s + b.minutos_ocupados, 0);
  const disponiveis = r.barbeiros.reduce((s, b) => s + b.minutos_disponiveis, 0);
  $("cartoes-resumo").replaceChildren(
    cartaoResumo("Agendamentos", String(r.total_agendamentos)),
    cartaoResumo("Receita de serviços", reais(r.receita)),
    cartaoResumo("Receita de produtos", reais(r.receita_produtos)),
    cartaoResumo("Ocupação geral", disponiveis ? `${Math.round((ocupados / disponiveis) * 100)}%` : "-"),
  );
  $("lista-relatorio").replaceChildren(
    ...r.barbeiros.map((b) =>
      elemento(
        "tr",
        {},
        elemento("td", { textContent: b.nome }),
        elemento("td", { textContent: String(b.agendados) }),
        elemento("td", { textContent: String(b.concluidos) }),
        elemento("td", { textContent: String(b.faltas) }),
        elemento("td", { textContent: String(b.cancelados) }),
        elemento("td", { textContent: reais(b.receita) }),
        elemento("td", { textContent: `${Math.round(b.ocupacao * 100)}%` }),
      ),
    ),
  );
}

// --- usuários ------------------------------------------------------------------------------

function montarUsuarios() {
  const secao = $("aba-usuarios");
  const papel = elemento("select", { name: "papel" }, criarOpcao("barbeiro", "Barbeiro (vê só a própria agenda)"), criarOpcao("dono", "Dono (acesso total)"));
  const barbeiro = elemento("select", { id: "usuario-barbeiro", name: "barbeiro_id" });
  const formulario = elemento(
    "form",
    { id: "form-usuario", classe: "grade-form" },
    elemento("label", {}, "Nome", elemento("input", { name: "nome", required: true, minLength: 2, maxLength: 100 })),
    elemento("label", {}, "Login", elemento("input", { name: "login", required: true, minLength: 2, maxLength: 100, pattern: "[a-z0-9._@-]+", autocomplete: "off" })),
    elemento("label", {}, "Senha (mín. 8)", elemento("input", { name: "senha", type: "password", required: true, minLength: 8, autocomplete: "new-password" })),
    elemento("label", {}, "Papel", papel),
    elemento("label", {}, "Barbeiro vinculado", barbeiro),
    elemento("button", { type: "submit", classe: "primario", textContent: "Criar usuário" }),
  );
  secao.append(
    elemento("h2", { textContent: "Novo usuário" }),
    formulario,
    elemento("h2", { textContent: "Usuários" }),
    elemento("div", { classe: "tabela-rolagem" },
      elemento("table", {},
        elemento("thead", {}, elemento("tr", {}, ...["#", "Nome", "Login", "Papel", "Barbeiro", "Status", ""].map((t) => elemento("th", { textContent: t })))),
        elemento("tbody", { id: "lista-usuarios" }))),
  );
  formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const f = formulario.elements;
    const resposta = await api("POST", "/usuarios", {
      nome: f.nome.value,
      login: f.login.value,
      senha: f.senha.value,
      papel: f.papel.value,
      barbeiro_id: f.barbeiro_id.value ? Number(f.barbeiro_id.value) : null,
    });
    if (!resposta.ok) {
      falha(resposta);
      return;
    }
    formulario.reset();
    mensagem("sucesso", `Usuário ${resposta.dados.login} criado.`);
    await carregarUsuarios();
  });
}

async function carregarUsuarios() {
  const resposta = await api("GET", "/usuarios");
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  $("lista-usuarios").replaceChildren(
    ...resposta.dados.map((u) =>
      elemento(
        "tr",
        { classe: u.ativo ? "" : "inativo" },
        elemento("td", { textContent: String(u.id) }),
        elemento("td", { textContent: u.nome }),
        elemento("td", { textContent: u.login }),
        elemento("td", { textContent: u.papel }),
        elemento("td", { textContent: u.barbeiro_id ? nomePorId(dados.barbeiros, u.barbeiro_id) : "-" }),
        elemento("td", {}, selo(u.ativo ? "ativo" : "inativo", u.ativo ? "ativo" : "inativo")),
        elemento("td", {}, elemento("div", { classe: "acoes-linha" },
          elemento("button", {
            type: "button", classe: "pequeno", textContent: "Trocar senha",
            aoClicar: async () => {
              const senha = prompt(`Nova senha para ${u.login} (mínimo 8 caracteres):`);
              if (!senha) return;
              const trocada = await api("PUT", `/usuarios/${u.id}/senha`, { senha });
              if (!trocada.ok) falha(trocada);
              else mensagem("sucesso", `Senha de ${u.login} alterada.`);
            },
          }),
          elemento("button", {
            type: "button", classe: u.ativo ? "pequeno perigo" : "pequeno", textContent: u.ativo ? "Desativar" : "Reativar",
            disabled: u.id === estado.usuario.id,
            aoClicar: async () => {
              const alterado = await api("PATCH", `/usuarios/${u.id}/ativo`, { ativo: !u.ativo });
              if (!alterado.ok) falha(alterado);
              else await carregarUsuarios();
            },
          }))),
      ),
    ),
  );
}

// --- navegação ----------------------------------------------------------------------------

const CARREGADORES = {
  agendamentos: () => carregarAgendamentos(),
  agenda: () => carregarAgenda(),
  bloqueios: () => carregarBloqueios(),
  vendas: () => carregarVendas(),
  relatorios: () => carregarRelatorio(),
  usuarios: () => carregarUsuarios(),
};

function trocarAba(nome) {
  $("mensagem").hidden = true;
  document.querySelectorAll(".aba").forEach((aba) => aba.classList.toggle("ativa", aba.dataset.aba === nome));
  document.querySelectorAll(".painel").forEach((painel) => {
    painel.hidden = painel.id !== `aba-${nome}`;
  });
  const cadastro = CADASTROS.find((item) => item.id === nome);
  if (cadastro) recarregarCadastros(cadastro);
  else CARREGADORES[nome]?.();
}

function agendamentosVisiveis() {
  return !$("aba-agendamentos").hidden && document.visibilityState === "visible";
}

async function iniciar() {
  const eu = await api("GET", "/auth/eu");
  if (!eu.ok) {
    location.href = "/entrar";
    return;
  }
  estado.usuario = eu.dados;
  $("usuario-atual").textContent = `${eu.dados.nome} (${eu.dados.papel})`;
  $("sair").addEventListener("click", async () => {
    await api("POST", "/auth/logout");
    location.href = "/entrar";
  });
  await carregarConfiguracao();

  if (!dono()) document.querySelectorAll("[data-dono]").forEach((aba) => aba.remove());

  if (dono()) {
    CADASTROS.forEach(montarCadastro);
    montarJanelas();
    montarVendas();
    montarRelatorios();
    montarUsuarios();
  }
  montarBloqueios();

  document.querySelectorAll(".aba").forEach((aba) => aba.addEventListener("click", () => trocarAba(aba.dataset.aba)));
  $("form-filtro").addEventListener("submit", (evento) => carregarAgendamentos(evento, { primeiraPagina: true }));
  $("limpar-filtro").addEventListener("click", () => {
    $("form-filtro").reset();
    carregarAgendamentos(null, { primeiraPagina: true });
  });
  $("exportar-csv").addEventListener("click", exportarCsv);
  $("filtro-cliente").addEventListener("input", (evento) => sugerirClientes(evento.target.value));
  $("pag-anterior").addEventListener("click", () => {
    estado.deslocamento = Math.max(0, estado.deslocamento - ITENS_POR_PAGINA);
    carregarAgendamentos();
  });
  $("pag-proxima").addEventListener("click", () => {
    estado.deslocamento += ITENS_POR_PAGINA;
    carregarAgendamentos();
  });
  $("atualizar").addEventListener("click", () => carregarAgendamentos());
  $("agenda-data").addEventListener("change", (evento) => {
    estado.agendaData = evento.target.value;
    carregarAgenda();
  });
  $("agenda-hoje").addEventListener("click", () => {
    estado.agendaData = dataLocalHoje();
    carregarAgenda();
  });
  $("agenda-anterior").addEventListener("click", () => mudarDiaDaAgenda(-1));
  $("agenda-proximo").addEventListener("click", () => mudarDiaDaAgenda(1));
  setInterval(() => {
    if ($("auto-atualizar").checked && agendamentosVisiveis()) carregarAgendamentos();
  }, INTERVALO_ATUALIZACAO_MS);

  await carregarReferencias();
  atualizarSelects();
  if (!dono()) {
    $("filtro-barbeiro").value = String(estado.usuario.barbeiro_id);
    $("filtro-barbeiro").disabled = true;
  }
  await carregarAgendamentos();
}

iniciar();
