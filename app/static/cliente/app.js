import {
  $,
  api,
  aplicarMascaraDeTelefone,
  carregarConfiguracao,
  dataLocalHoje,
  elemento,
  falha,
  formatarDataHora,
  mensagem,
  ocupado,
  reais,
  ultimoDiaDoMes,
  validarCampo,
  validarEmail,
  validarNome,
  validarTelefone,
} from "/comum/util.js";

const CHAVE_AGENDAMENTO = "barbearia.ultimoAgendamento";
const CHAVE_DADOS = "barbearia.meusDados";

const estado = { escolha: null, ultima: null, token: null, servicos: [], duracao: 0, validadores: [] };

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

// --- serviços (um ou vários) -----------------------------------------------------------------

function servicosEscolhidos() {
  return [...document.querySelectorAll("#servicos input:checked")].map((caixa) => Number(caixa.value));
}

function atualizarResumoDeServicos() {
  const ids = servicosEscolhidos();
  const escolhidos = estado.servicos.filter((s) => ids.includes(s.id));
  const duracao = escolhidos.reduce((total, s) => total + s.duracao_minutos, 0);
  const preco = escolhidos.reduce((total, s) => total + Number(s.preco), 0);
  estado.duracao = duracao;
  $("resumo-servicos").textContent = escolhidos.length
    ? `${escolhidos.map((s) => s.nome).join(" + ")}: ${duracao} min, ${reais(preco)}`
    : "Nenhum serviço selecionado.";
  limparEscolha();
  $("barbeiros").replaceChildren();
}

function montarServicos(servicos) {
  estado.servicos = servicos;
  $("servicos").replaceChildren(
    ...servicos.map((s) =>
      elemento(
        "label",
        { classe: "servico-opcao" },
        elemento("input", { type: "checkbox", name: "servico", value: String(s.id) }),
        elemento("span", {}, s.nome, elemento("small", { textContent: `${s.duracao_minutos} min · ${reais(s.preco)}` })),
      ),
    ),
  );
  $("servicos").addEventListener("change", atualizarResumoDeServicos);
}

function parametrosDeServicos(ids) {
  return ids.map((id) => `servico_ids=${id}`).join("&");
}

function horaFim(inicio, minutos) {
  const [h, m] = inicio.slice(11, 16).split(":").map(Number);
  const total = h * 60 + m + minutos;
  return `${String(Math.floor(total / 60) % 24).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}

// --- escolha de barbeiro e horário -------------------------------------------------------------

function limparEscolha() {
  estado.escolha = null;
  $("resumo").textContent = "Nenhum horário selecionado.";
  $("confirmar").disabled = true;
}

function escolher(barbeiro, inicio, botao) {
  estado.escolha = { barbeiroId: barbeiro.id, barbeiroNome: barbeiro.nome, inicio };
  document.querySelectorAll("#barbeiros button").forEach((outro) => outro.setAttribute("aria-pressed", String(outro === botao)));
  $("resumo").textContent = `${barbeiro.nome} em ${formatarDataHora(inicio)} (até ${horaFim(inicio, estado.duracao)})`;
  $("confirmar").disabled = false;
}

function botoesDeHorario(horarios, duracao, aoEscolher) {
  return horarios.map((inicio) => {
    const botao = elemento("button", { type: "button", textContent: `${inicio.slice(11, 16)} – ${horaFim(inicio, duracao)}` });
    botao.setAttribute("aria-pressed", "false");
    botao.addEventListener("click", () => aoEscolher(inicio, botao));
    return botao;
  });
}

function cartaoBarbeiro(barbeiro, duracao, extra = "") {
  return elemento(
    "article",
    { classe: `barbeiro ${extra}`.trim() },
    elemento("h3", { textContent: barbeiro.nome }),
    elemento(
      "div",
      { classe: "horarios", role: "group", "aria-label": `Horários de ${barbeiro.nome}` },
      botoesDeHorario(barbeiro.horarios, duracao, (inicio, botao) => escolher(barbeiro, inicio, botao)),
    ),
  );
}

async function verBarbeiros() {
  limparEscolha();
  const lista = $("barbeiros");
  lista.replaceChildren();
  const ids = servicosEscolhidos();
  if (!ids.length) {
    mensagem("aviso", "Marque pelo menos um serviço.");
    return;
  }
  if (!$("data").reportValidity()) return;
  const resposta = await api("GET", `/disponibilidade?data=${$("data").value}&${parametrosDeServicos(ids)}`);
  if (!resposta.ok) {
    falha(resposta);
    return;
  }
  $("mensagem").hidden = true;
  const { barbeiros, duracao_minutos: duracao } = resposta.dados;
  estado.duracao = duracao;
  $("ajuda-barbeiros").textContent = barbeiros.length
    ? `${barbeiros.length} barbeiro(s) com horários livres para ${duracao} min. Escolha um horário.`
    : "Nenhum barbeiro com horário livre nesse dia. Tente outra data.";
  if (barbeiros.length > 1) {
    const horarios = [...new Set(barbeiros.flatMap((b) => b.horarios))].sort();
    lista.append(cartaoBarbeiro({ id: null, nome: "Qualquer barbeiro", horarios }, duracao, "qualquer"));
  }
  barbeiros.forEach((barbeiro) => lista.append(cartaoBarbeiro(barbeiro, duracao)));
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
  $("ajuda-barbeiros").textContent = "Escolha os serviços e o dia para ver quem está disponível.";
}

function dadosValidos() {
  return estado.validadores.map((validar) => validar()).every(Boolean);
}

async function agendar(evento) {
  evento.preventDefault();
  if (!dadosValidos()) {
    mensagem("aviso", "Corrija os campos destacados antes de confirmar.");
    $("form-agendamento").reportValidity();
    return;
  }
  if (!estado.escolha) {
    mensagem("aviso", "Escolha um horário antes de confirmar.");
    return;
  }
  const liberar = ocupado($("confirmar"), "Confirmando...");
  const dados = { nome: $("nome").value.trim(), email: $("email").value.trim(), telefone: $("telefone").value };
  const resposta = await api("POST", "/agendamentos", {
    ...dados,
    barbeiro_id: estado.escolha.barbeiroId,
    servico_ids: servicosEscolhidos(),
    inicio: estado.escolha.inicio,
  });
  liberar();
  if (!resposta.ok) {
    falha(resposta);
    await verBarbeiros();
    return;
  }
  guardar(CHAVE_DADOS, $("lembrar").checked ? dados : null);
  guardar(CHAVE_AGENDAMENTO, resposta.dados);
  $("mensagem").hidden = true;
  mostrarConfirmacao(resposta.dados);
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

// --- remarcar ---------------------------------------------------------------------------------

async function verHorariosParaRemarcar() {
  const ultima = estado.ultima;
  const lista = $("remarcar-horarios");
  lista.replaceChildren();
  const ids = ultima?.servico_ids?.length ? ultima.servico_ids : null;
  if (!ids) {
    mensagem("aviso", "Não foi possível identificar os serviços; cancele e marque de novo.");
    return;
  }
  const data = $("remarcar-data").value;
  if (!data) return;
  const resposta = await api("GET", `/disponibilidade?data=${data}&${parametrosDeServicos(ids)}`);
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
    ...botoesDeHorario(barbeiro.horarios, resposta.dados.duracao_minutos, async (inicio, botao) => {
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
      guardar(CHAVE_AGENDAMENTO, remarcado.dados);
      mostrarConfirmacao(remarcado.dados);
      mensagem("sucesso", `Agendamento #${ultima.id} remarcado para ${formatarDataHora(inicio)}.`);
    }),
  );
}

// --- meus agendamentos (link mágico) ------------------------------------------------------------

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

// --- inicialização -------------------------------------------------------------------------------

async function iniciar() {
  await carregarConfiguracao();
  const hoje = dataLocalHoje();
  for (const id of ["data", "remarcar-data"]) {
    $(id).value = hoje;
    $(id).min = hoje;
    $(id).max = ultimoDiaDoMes(hoje);
  }

  aplicarMascaraDeTelefone($("telefone"));
  estado.validadores = [
    validarCampo($("nome"), validarNome),
    validarCampo($("email"), validarEmail),
    validarCampo($("telefone"), validarTelefone),
  ];
  validarCampo($("link-email"), validarEmail);

  const dadosGuardados = lerGuardado(CHAVE_DADOS);
  if (dadosGuardados) {
    $("nome").value = dadosGuardados.nome ?? "";
    $("email").value = dadosGuardados.email ?? "";
    $("telefone").value = dadosGuardados.telefone ?? "";
  }

  $("ver-barbeiros").addEventListener("click", verBarbeiros);
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
    if (validarEmail($("link-email").value)) {
      evento.target.reportValidity();
      return;
    }
    const botao = evento.target.querySelector("button");
    const liberar = ocupado(botao, "Enviando...");
    const resposta = await api("POST", "/meus-agendamentos/solicitar", { email: $("link-email").value.trim() });
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
    montarServicos(resposta.dados);
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
