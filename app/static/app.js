const DIAS = ["Segunda", "Terça", "Quarta", "Quinta", "Sexta", "Sábado", "Domingo"];

const estado = { clientes: [], barbeiros: [], servicos: [], horarioEscolhido: null };

const $ = (id) => document.getElementById(id);

async function api(metodo, caminho, corpo) {
  try {
    const resposta = await fetch(caminho, {
      method: metodo,
      headers: corpo ? { "Content-Type": "application/json" } : {},
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
    let dados = null;
    try {
      dados = await resposta.json();
    } catch {
      dados = null;
    }
    return { ok: resposta.ok, status: resposta.status, dados };
  } catch {
    return { ok: false, status: 0, dados: { detail: "Não foi possível falar com a API. Ela está rodando?" } };
  }
}

function detalhe(dados) {
  if (!dados || dados.detail === undefined) return "erro desconhecido";
  if (Array.isArray(dados.detail)) {
    return dados.detail.map((erro) => `${erro.loc.slice(1).join(".")}: ${erro.msg}`).join("; ");
  }
  return dados.detail;
}

function mensagem(tipo, texto) {
  const caixa = $("mensagem");
  caixa.className = `mensagem ${tipo}`;
  caixa.textContent = texto;
  caixa.hidden = false;
}

function falha(resposta) {
  const prefixo = resposta.status ? `Erro ${resposta.status}: ` : "";
  mensagem("erro", `${prefixo}${detalhe(resposta.dados)}`);
}

function formatarDataHora(iso) {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)} ${iso.slice(11, 16)}`;
}

function criarOpcao(valor, texto) {
  const opcao = document.createElement("option");
  opcao.value = valor;
  opcao.textContent = texto;
  return opcao;
}

function preencherSelect(select, itens, rotulo, vazio) {
  const anterior = select.value;
  select.replaceChildren();
  if (vazio) select.append(criarOpcao("", vazio));
  itens.forEach((item) => select.append(criarOpcao(item.id, rotulo(item))));
  if ([...select.options].some((opcao) => opcao.value === anterior)) select.value = anterior;
}

function nomePorId(lista, id) {
  const item = lista.find((entrada) => entrada.id === id);
  return item ? item.nome : `#${id}`;
}

async function carregarListas() {
  const [clientes, barbeiros, servicos] = await Promise.all([
    api("GET", "/clientes"),
    api("GET", "/barbeiros"),
    api("GET", "/servicos"),
  ]);
  if (!clientes.ok || !barbeiros.ok || !servicos.ok) {
    falha([clientes, barbeiros, servicos].find((resposta) => !resposta.ok));
    return;
  }
  estado.clientes = clientes.dados;
  estado.barbeiros = barbeiros.dados;
  estado.servicos = servicos.dados;

  preencherSelect($("agendar-cliente"), estado.clientes, (c) => c.nome, "Selecione...");
  preencherSelect($("agendar-barbeiro"), estado.barbeiros, (b) => b.nome, "Selecione...");
  preencherSelect(
    $("agendar-servico"),
    estado.servicos,
    (s) => `${s.nome} - ${s.duracao_minutos} min - R$ ${s.preco.toFixed(2)}`,
    "Selecione...",
  );
  preencherSelect($("filtro-barbeiro"), estado.barbeiros, (b) => b.nome, "Todos");
  preencherSelect($("janela-barbeiro"), estado.barbeiros, (b) => b.nome, null);
  await carregarJanelas();
}

async function carregarJanelas() {
  const lista = $("lista-janelas");
  lista.replaceChildren();
  const barbeiroId = $("janela-barbeiro").value;
  if (!barbeiroId) return;
  const resposta = await api("GET", `/barbeiros/${barbeiroId}/disponibilidades`);
  if (!resposta.ok) return;
  resposta.dados.forEach((janela) => {
    const item = document.createElement("li");
    item.textContent = `${DIAS[janela.dia_semana]}: ${janela.hora_inicio.slice(0, 5)} - ${janela.hora_fim.slice(0, 5)}`;
    lista.append(item);
  });
}

function limparHorarioEscolhido() {
  estado.horarioEscolhido = null;
  $("horario-escolhido").textContent = "Nenhum horário selecionado.";
  $("confirmar").disabled = true;
}

function escolherHorario(iso, botao) {
  estado.horarioEscolhido = iso;
  document.querySelectorAll("#horarios button").forEach((outro) => outro.setAttribute("aria-pressed", String(outro === botao)));
  $("horario-escolhido").textContent = `Horário selecionado: ${formatarDataHora(iso)}`;
  $("confirmar").disabled = false;
}

async function verHorarios(evento) {
  if (evento) evento.preventDefault();
  limparHorarioEscolhido();
  const grade = $("horarios");
  grade.replaceChildren();
  const barbeiroId = $("agendar-barbeiro").value;
  const servicoId = $("agendar-servico").value;
  const data = $("agendar-data").value;
  if (!barbeiroId || !servicoId || !data) {
    mensagem("aviso", "Escolha barbeiro, serviço e data. Sem dados? Use a aba Cadastros.");
    return;
  }
  const resposta = await api("GET", `/barbeiros/${barbeiroId}/horarios-livres?data=${data}&servico_id=${servicoId}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  const horarios = resposta.dados.horarios;
  $("horarios-ajuda").textContent = horarios.length
    ? `${horarios.length} horários livres em ${data.split("-").reverse().join("/")}.`
    : "Nenhum horário livre nesse dia (o barbeiro pode não ter janela cadastrada ou já estar lotado).";
  horarios.forEach((iso) => {
    const botao = document.createElement("button");
    botao.type = "button";
    botao.textContent = iso.slice(11, 16);
    botao.setAttribute("aria-pressed", "false");
    botao.addEventListener("click", () => escolherHorario(iso, botao));
    grade.append(botao);
  });
}

function corpoAgendamento(inicio) {
  return {
    cliente_id: Number($("agendar-cliente").value),
    barbeiro_id: Number($("agendar-barbeiro").value),
    servico_id: Number($("agendar-servico").value),
    inicio,
  };
}

async function criarAgendamento(inicio) {
  if (!$("agendar-cliente").value || !$("agendar-barbeiro").value || !$("agendar-servico").value) {
    mensagem("aviso", "Escolha cliente, barbeiro e serviço antes de agendar.");
    return;
  }
  const resposta = await api("POST", "/agendamentos", corpoAgendamento(inicio));
  if (!resposta.ok) {
    falha(resposta);
    if ($("agendar-data").value) await verHorarios();
    return;
  }
  const agendamento = resposta.dados;
  mensagem(
    "sucesso",
    `Agendamento #${agendamento.id} criado: ${formatarDataHora(agendamento.inicio)} até ${agendamento.fim.slice(11, 16)}. ` +
      "A confirmação por e-mail (simulada) foi registrada no log do servidor.",
  );
  if ($("agendar-data").value) await verHorarios();
  await carregarAgendamentos();
}

async function carregarAgendamentos(evento) {
  if (evento) evento.preventDefault();
  const filtros = new URLSearchParams();
  if ($("filtro-barbeiro").value) filtros.set("barbeiro_id", $("filtro-barbeiro").value);
  if ($("filtro-data").value) filtros.set("data", $("filtro-data").value);
  const consulta = filtros.toString();
  const resposta = await api("GET", `/agendamentos${consulta ? `?${consulta}` : ""}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  const corpo = $("lista-agendamentos");
  corpo.replaceChildren();
  $("sem-agendamentos").hidden = resposta.dados.length > 0;
  resposta.dados.forEach((agendamento) => corpo.append(linhaAgendamento(agendamento)));
}

function celula(texto) {
  const td = document.createElement("td");
  td.textContent = texto;
  return td;
}

function linhaAgendamento(agendamento) {
  const linha = document.createElement("tr");
  linha.append(
    celula(agendamento.id),
    celula(formatarDataHora(agendamento.inicio)),
    celula(agendamento.fim.slice(11, 16)),
    celula(nomePorId(estado.clientes, agendamento.cliente_id)),
    celula(nomePorId(estado.barbeiros, agendamento.barbeiro_id)),
    celula(nomePorId(estado.servicos, agendamento.servico_id)),
  );
  const status = document.createElement("td");
  const selo = document.createElement("span");
  selo.className = `status ${agendamento.status}`;
  selo.textContent = agendamento.status;
  status.append(selo);
  const acao = document.createElement("td");
  if (agendamento.status === "agendado") {
    const cancelar = document.createElement("button");
    cancelar.type = "button";
    cancelar.textContent = "Cancelar";
    cancelar.addEventListener("click", () => cancelarAgendamento(agendamento.id));
    acao.append(cancelar);
  }
  linha.append(status, acao);
  return linha;
}

async function cancelarAgendamento(id) {
  const resposta = await api("DELETE", `/agendamentos/${id}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  mensagem("sucesso", `Agendamento #${id} cancelado. O horário voltou a ficar livre.`);
  await carregarAgendamentos();
  if ($("agendar-data").value && $("agendar-barbeiro").value && $("agendar-servico").value) await verHorarios();
}

async function cadastrar(evento, caminho, montarCorpo, rotulo) {
  evento.preventDefault();
  const formulario = evento.target;
  const resposta = await api("POST", caminho(formulario), montarCorpo(new FormData(formulario)));
  if (!resposta.ok) {
    falha(resposta);
    return false;
  }
  formulario.reset();
  await carregarListas();
  mensagem("sucesso", `${rotulo} cadastrado.`);
  return true;
}

function horaCompleta(valor) {
  return valor.length === 5 ? `${valor}:00` : valor;
}

async function criarDadosExemplo() {
  if (estado.barbeiros.length && !confirm("Já existem barbeiros cadastrados. Criar os dados de exemplo mesmo assim?")) return;
  const cliente = await api("POST", "/clientes", { nome: "Carlos Silva", email: "carlos@exemplo.com", telefone: "11987654321" });
  const servicos = [
    { nome: "Corte de cabelo", duracao_minutos: 30, preco: 45 },
    { nome: "Barba", duracao_minutos: 20, preco: 30 },
    { nome: "Corte + barba", duracao_minutos: 60, preco: 70 },
  ];
  const barbeiros = [
    { nome: "João Barbeiro", email: "joao@barbearia.com" },
    { nome: "Pedro Navalha", email: "pedro@barbearia.com" },
  ];
  const respostas = [cliente];
  for (const servico of servicos) respostas.push(await api("POST", "/servicos", servico));
  for (const barbeiro of barbeiros) {
    const criado = await api("POST", "/barbeiros", barbeiro);
    respostas.push(criado);
    if (!criado.ok) continue;
    for (let dia = 0; dia <= 5; dia += 1) {
      respostas.push(
        await api("POST", `/barbeiros/${criado.dados.id}/disponibilidades`, { dia_semana: dia, hora_inicio: "09:00:00", hora_fim: "18:00:00" }),
      );
    }
  }
  await carregarListas();
  const erro = respostas.find((resposta) => !resposta.ok);
  if (erro) falha(erro);
  else mensagem("sucesso", "Dados de exemplo criados. Vá para Agendar e escolha uma data de segunda a sábado.");
}

function trocarAba(nome) {
  document.querySelectorAll(".aba").forEach((aba) => aba.classList.toggle("ativa", aba.dataset.aba === nome));
  document.querySelectorAll(".painel").forEach((painel) => {
    painel.hidden = painel.id !== `aba-${nome}`;
  });
  if (nome === "agendamentos") carregarAgendamentos();
}

function iniciar() {
  const hoje = new Date().toLocaleDateString("sv-SE");
  $("agendar-data").value = hoje;
  $("agendar-data").min = hoje;
  preencherSelect($("janela-dia"), DIAS.map((nome, indice) => ({ id: indice, nome })), (dia) => dia.nome, null);

  document.querySelectorAll(".aba").forEach((aba) => aba.addEventListener("click", () => trocarAba(aba.dataset.aba)));
  $("form-horarios").addEventListener("submit", verHorarios);
  $("agendar-barbeiro").addEventListener("change", limparHorarioEscolhido);
  $("agendar-servico").addEventListener("change", limparHorarioEscolhido);
  $("agendar-data").addEventListener("change", limparHorarioEscolhido);
  $("confirmar").addEventListener("click", () => criarAgendamento(estado.horarioEscolhido));
  $("form-manual").addEventListener("submit", (evento) => {
    evento.preventDefault();
    criarAgendamento(`${$("manual-inicio").value}:00`);
  });
  $("form-filtro").addEventListener("submit", carregarAgendamentos);
  $("limpar-filtro").addEventListener("click", () => {
    $("filtro-barbeiro").value = "";
    $("filtro-data").value = "";
    carregarAgendamentos();
  });
  $("criar-exemplo").addEventListener("click", criarDadosExemplo);
  $("janela-barbeiro").addEventListener("change", carregarJanelas);

  $("form-cliente").addEventListener("submit", (e) =>
    cadastrar(e, () => "/clientes", (dados) => Object.fromEntries(dados), "Cliente"),
  );
  $("form-barbeiro").addEventListener("submit", (e) =>
    cadastrar(e, () => "/barbeiros", (dados) => Object.fromEntries(dados), "Barbeiro"),
  );
  $("form-servico").addEventListener("submit", (e) =>
    cadastrar(
      e,
      () => "/servicos",
      (dados) => ({ nome: dados.get("nome"), duracao_minutos: Number(dados.get("duracao_minutos")), preco: Number(dados.get("preco")) }),
      "Serviço",
    ),
  );
  $("form-janela").addEventListener("submit", (e) =>
    cadastrar(
      e,
      (formulario) => `/barbeiros/${formulario.elements.barbeiro.value}/disponibilidades`,
      (dados) => ({
        dia_semana: Number(dados.get("dia_semana")),
        hora_inicio: horaCompleta(dados.get("hora_inicio")),
        hora_fim: horaCompleta(dados.get("hora_fim")),
      }),
      "Janela de disponibilidade",
    ),
  );

  carregarListas();
}

iniciar();
