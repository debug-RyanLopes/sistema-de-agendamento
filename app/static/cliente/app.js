import {
  $,
  api,
  carregarConfiguracao,
  dataLocalHoje,
  elemento,
  falha,
  formatarDataHora,
  mensagem,
  ocupado,
  preencherSelect,
  reais,
  ultimoDiaDoMes,
} from "/comum/util.js";

const CHAVE_AGENDAMENTO = "barbearia.ultimoAgendamento";
const CHAVE_DADOS = "barbearia.meusDados";

const estado = { escolha: null, ultima: null, token: null, remarcarEscolha: null };

function lerGuardado(chave) {
  try {
    return JSON.parse(localStorage.getItem(chave));
  } catch {
    return null;
  }
}

function guardar(chave, valor) {
  try {
    if (valor) localStorage.setItem(chave, JSON.stringify(valor));
    else localStorage.removeItem(chave);
  } catch {
    /* armazenamento indisponível: a confirmação continua visível na página */
  }
}

function limparEscolha() {
  estado.escolha = null;
  $("resumo").textContent = "Nenhum horário selecionado.";
  $("confirmar").disabled = true;
}

function escolher(barbeiro, inicio, botao) {
  estado.escolha = { barbeiroId: barbeiro.id, barbeiroNome: barbeiro.nome, inicio };
  document.querySelectorAll("#barbeiros button").forEach((outro) => outro.setAttribute("aria-pressed", String(outro === botao)));
  $("resumo").textContent = `${barbeiro.nome} em ${formatarDataHora(inicio)}`;
  $("confirmar").disabled = false;
}

function botoesDeHorario(horarios, aoEscolher) {
  return horarios.map((inicio) => {
    const botao = elemento("button", { type: "button", textContent: inicio.slice(11, 16) });
    botao.setAttribute("aria-pressed", "false");
    botao.addEventListener("click", () => aoEscolher(inicio, botao));
    return botao;
  });
}

function cartaoBarbeiro(barbeiro, extra = "") {
  return elemento(
    "article",
    { classe: `barbeiro ${extra}`.trim() },
    elemento("h3", { textContent: barbeiro.nome }),
    elemento(
      "div",
      { classe: "horarios", role: "group", "aria-label": `Horários de ${barbeiro.nome}` },
      botoesDeHorario(barbeiro.horarios, (inicio, botao) => escolher(barbeiro, inicio, botao)),
    ),
  );
}

async function verBarbeiros() {
  limparEscolha();
  const lista = $("barbeiros");
  lista.replaceChildren();
  if (!$("servico").reportValidity() || !$("data").reportValidity()) return;
  const resposta = await api("GET", `/disponibilidade?data=${$("data").value}&servico_id=${$("servico").value}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  const { barbeiros } = resposta.dados;
  $("ajuda-barbeiros").textContent = barbeiros.length
    ? `${barbeiros.length} barbeiro(s) com horários livres. Escolha um horário.`
    : "Nenhum barbeiro com horário livre nesse dia. Tente outra data.";
  if (barbeiros.length > 1) {
    const horarios = [...new Set(barbeiros.flatMap((b) => b.horarios))].sort();
    lista.append(cartaoBarbeiro({ id: null, nome: "Qualquer barbeiro", horarios }, "qualquer"));
  }
  barbeiros.forEach((barbeiro) => lista.append(cartaoBarbeiro(barbeiro)));
}

function mostrarConfirmacao(confirmacao) {
  estado.ultima = confirmacao;
  $("conf-id").textContent = `#${confirmacao.id}`;
  $("conf-barbeiro").textContent = confirmacao.barbeiro;
  $("conf-servico").textContent = confirmacao.servico;
  $("conf-quando").textContent = `${formatarDataHora(confirmacao.inicio)} às ${confirmacao.fim.slice(11, 16)}`;
  $("conf-preco").textContent = reais(confirmacao.preco);
  $("conf-codigo").textContent = confirmacao.codigo_cancelamento;
  $("conf-ics").href = `/agendamentos/${confirmacao.id}/ics?codigo=${encodeURIComponent(confirmacao.codigo_cancelamento)}`;
  $("remarcar").hidden = true;
  $("remarcar-horarios").replaceChildren();
  $("confirmacao").hidden = false;
  $("agendamento").hidden = true;
  $("meus-agendamentos").hidden = true;
}

function voltarAoFormulario() {
  estado.ultima = null;
  guardar(CHAVE_AGENDAMENTO, null);
  $("confirmacao").hidden = true;
  $("meus-agendamentos").hidden = true;
  $("agendamento").hidden = false;
  limparEscolha();
  $("barbeiros").replaceChildren();
  $("ajuda-barbeiros").textContent = "Escolha o serviço e o dia para ver quem está disponível.";
}

async function agendar(evento) {
  evento.preventDefault();
  if (!estado.escolha) {
    mensagem("aviso", "Escolha um horário antes de confirmar.");
    return;
  }
  const liberar = ocupado($("confirmar"), "Confirmando...");
  const dados = { nome: $("nome").value, email: $("email").value, telefone: $("telefone").value };
  const resposta = await api("POST", "/agendamentos", {
    ...dados,
    barbeiro_id: estado.escolha.barbeiroId,
    servico_id: Number($("servico").value),
    inicio: estado.escolha.inicio,
  });
  liberar();
  if (!resposta.ok) {
    falha(resposta);
    await verBarbeiros();
    return;
  }
  guardar(CHAVE_DADOS, $("lembrar").checked ? dados : null);
  const confirmacao = { ...resposta.dados, servico_id: Number($("servico").value) };
  guardar(CHAVE_AGENDAMENTO, confirmacao);
  $("mensagem").hidden = true;
  mostrarConfirmacao(confirmacao);
}

async function cancelar(id, codigo) {
  const resposta = await api("POST", `/agendamentos/${id}/cancelar`, { codigo });
  if (!resposta.ok) {
    falha(resposta);
    if ((resposta.status === 404 || resposta.status === 422) && estado.ultima?.id === id) {
      voltarAoFormulario();
    }
    return false;
  }
  if (estado.ultima?.id === id) voltarAoFormulario();
  mensagem("sucesso", `Agendamento #${id} cancelado. O horário voltou a ficar livre.`);
  return true;
}

// --- remarcar -------------------------------------------------------------------------

async function verHorariosParaRemarcar() {
  const ultima = estado.ultima;
  const lista = $("remarcar-horarios");
  lista.replaceChildren();
  estado.remarcarEscolha = null;
  if (!ultima?.servico_id) {
    mensagem("aviso", "Não foi possível identificar o serviço; cancele e marque de novo.");
    return;
  }
  const data = $("remarcar-data").value;
  if (!data) return;
  const resposta = await api("GET", `/disponibilidade?data=${data}&servico_id=${ultima.servico_id}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  const barbeiro = resposta.dados.barbeiros.find((b) => b.nome === ultima.barbeiro);
  if (!barbeiro) {
    lista.append(elemento("p", { classe: "ajuda", textContent: `${ultima.barbeiro} não tem horário livre nesse dia.` }));
    return;
  }
  lista.append(
    ...botoesDeHorario(barbeiro.horarios, async (inicio, botao) => {
      if (!confirm(`Remarcar para ${formatarDataHora(inicio)}?`)) return;
      const liberar = ocupado(botao);
      const remarcado = await api("POST", `/agendamentos/${ultima.id}/reagendar`, {
        codigo: ultima.codigo_cancelamento,
        inicio,
      });
      liberar();
      if (!remarcado.ok) {
        falha(remarcado);
        return;
      }
      const confirmacao = { ...remarcado.dados, servico_id: ultima.servico_id };
      guardar(CHAVE_AGENDAMENTO, confirmacao);
      mostrarConfirmacao(confirmacao);
      mensagem("sucesso", `Agendamento #${ultima.id} remarcado para ${formatarDataHora(inicio)}.`);
    }),
  );
}

// --- meus agendamentos (link mágico) ----------------------------------------------------

function linhaMeuAgendamento(item) {
  const descricao = `${formatarDataHora(item.inicio)} - ${item.servico} com ${item.barbeiro}`;
  const botao = elemento("button", {
    type: "button",
    classe: "pequeno perigo",
    textContent: "Cancelar",
    aoClicar: async () => {
      if (!confirm(`Cancelar o agendamento #${item.id}?`)) return;
      if (await cancelar(item.id, item.codigo_cancelamento)) await carregarMeusAgendamentos();
    },
  });
  return elemento(
    "li",
    {},
    elemento("div", {}, elemento("strong", { textContent: `#${item.id} ` }), descricao,
      elemento("div", { classe: "codigo-pequeno", textContent: `código ${item.codigo_cancelamento ?? "-"}` })),
    botao,
  );
}

async function carregarMeusAgendamentos() {
  const resposta = await api("GET", `/meus-agendamentos?token=${encodeURIComponent(estado.token)}`);
  if (!resposta.ok) {
    falha(resposta);
    estado.token = null;
    return;
  }
  $("meus-email").textContent = `Agendamentos futuros de ${resposta.dados.email}`;
  const itens = resposta.dados.agendamentos;
  $("meus-lista").replaceChildren(
    ...(itens.length ? itens.map(linhaMeuAgendamento) : [elemento("li", { textContent: "Nenhum agendamento futuro." })]),
  );
  $("meus-apagar").disabled = itens.length > 0;
  $("meus-agendamentos").hidden = false;
  $("confirmacao").hidden = true;
  $("agendamento").hidden = true;
}

async function apagarMeusDados() {
  if (!confirm("Apagar seus dados pessoais do cadastro? Esta ação não pode ser desfeita.")) return;
  const resposta = await api("POST", `/meus-dados/exclusao?token=${encodeURIComponent(estado.token)}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  guardar(CHAVE_DADOS, null);
  guardar(CHAVE_AGENDAMENTO, null);
  estado.token = null;
  voltarAoFormulario();
  mensagem("sucesso", "Seus dados pessoais foram apagados.");
}

// --- inicialização ----------------------------------------------------------------------

async function iniciar() {
  await carregarConfiguracao();
  const hoje = dataLocalHoje();
  for (const id of ["data", "remarcar-data"]) {
    $(id).value = hoje;
    $(id).min = hoje;
    $(id).max = ultimoDiaDoMes(hoje);
  }

  const dadosGuardados = lerGuardado(CHAVE_DADOS);
  if (dadosGuardados) {
    $("nome").value = dadosGuardados.nome ?? "";
    $("email").value = dadosGuardados.email ?? "";
    $("telefone").value = dadosGuardados.telefone ?? "";
  }

  $("ver-barbeiros").addEventListener("click", verBarbeiros);
  $("servico").addEventListener("change", limparEscolha);
  $("data").addEventListener("change", limparEscolha);
  $("form-agendamento").addEventListener("submit", agendar);

  $("cancelar-agendamento").addEventListener("click", async () => {
    if (!estado.ultima || !confirm("Cancelar este agendamento?")) return;
    await cancelar(estado.ultima.id, estado.ultima.codigo_cancelamento);
  });
  $("novo-agendamento").addEventListener("click", voltarAoFormulario);
  $("remarcar-abrir").addEventListener("click", () => {
    $("remarcar").hidden = !$("remarcar").hidden;
    if (!$("remarcar").hidden) verHorariosParaRemarcar();
  });
  $("remarcar-ver").addEventListener("click", verHorariosParaRemarcar);
  $("remarcar-data").addEventListener("change", verHorariosParaRemarcar);

  $("form-cancelar-codigo").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const feito = await cancelar(Number($("codigo-id").value), $("codigo-valor").value.trim());
    if (feito) evento.target.reset();
  });

  $("form-link").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const botao = evento.target.querySelector("button");
    const liberar = ocupado(botao, "Enviando...");
    const resposta = await api("POST", "/meus-agendamentos/solicitar", { email: $("link-email").value });
    liberar();
    if (!resposta.ok) {
      falha(resposta);
      return;
    }
    mensagem("sucesso", "Se o e-mail estiver cadastrado, o link chega em instantes. Ele vale por 30 minutos.");
    evento.target.reset();
  });

  $("meus-fechar").addEventListener("click", voltarAoFormulario);
  $("meus-apagar").addEventListener("click", apagarMeusDados);

  api("GET", "/servicos").then((resposta) => {
    if (!resposta.ok) {
      falha(resposta);
      return;
    }
    preencherSelect(
      $("servico"),
      resposta.dados,
      (s) => `${s.nome} - ${s.duracao_minutos} min - ${reais(s.preco)}`,
      "Selecione...",
    );
  });

  const token = new URLSearchParams(location.search).get("token");
  if (token) {
    estado.token = token;
    history.replaceState(null, "", location.pathname);
    await carregarMeusAgendamentos();
    return;
  }
  const guardado = lerGuardado(CHAVE_AGENDAMENTO);
  if (guardado) mostrarConfirmacao(guardado);
}

iniciar();
