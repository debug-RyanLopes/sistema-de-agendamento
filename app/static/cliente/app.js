import {
  $,
  api,
  dataLocalHoje,
  elemento,
  falha,
  formatarDataHora,
  mensagem,
  preencherSelect,
  reais,
} from "/comum/util.js";

const CHAVE_AGENDAMENTO = "barbearia.ultimoAgendamento";

const estado = { escolha: null, ultima: null };

function lerGuardado() {
  try {
    return JSON.parse(localStorage.getItem(CHAVE_AGENDAMENTO));
  } catch {
    return null;
  }
}

function guardar(confirmacao) {
  try {
    if (confirmacao) localStorage.setItem(CHAVE_AGENDAMENTO, JSON.stringify(confirmacao));
    else localStorage.removeItem(CHAVE_AGENDAMENTO);
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

function cartaoBarbeiro(barbeiro) {
  const botoes = barbeiro.horarios.map((inicio) => {
    const botao = elemento("button", { type: "button", textContent: inicio.slice(11, 16) });
    botao.setAttribute("aria-pressed", "false");
    botao.addEventListener("click", () => escolher(barbeiro, inicio, botao));
    return botao;
  });
  return elemento(
    "article",
    { classe: "barbeiro" },
    elemento("h3", { textContent: barbeiro.nome }),
    elemento("div", { classe: "horarios", role: "group", "aria-label": `Horários de ${barbeiro.nome}` }, botoes),
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
  $("confirmacao").hidden = false;
  $("agendamento").hidden = true;
}

function voltarAoFormulario() {
  estado.ultima = null;
  guardar(null);
  $("confirmacao").hidden = true;
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
  const resposta = await api("POST", "/agendamentos", {
    nome: $("nome").value,
    email: $("email").value,
    telefone: $("telefone").value,
    barbeiro_id: estado.escolha.barbeiroId,
    servico_id: Number($("servico").value),
    inicio: estado.escolha.inicio,
  });
  if (!resposta.ok) {
    falha(resposta);
    await verBarbeiros();
    return;
  }
  guardar(resposta.dados);
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

function iniciar() {
  const hoje = dataLocalHoje();
  $("data").value = hoje;
  $("data").min = hoje;

  $("ver-barbeiros").addEventListener("click", verBarbeiros);
  $("servico").addEventListener("change", limparEscolha);
  $("data").addEventListener("change", limparEscolha);
  $("form-agendamento").addEventListener("submit", agendar);

  $("cancelar-agendamento").addEventListener("click", async () => {
    if (!estado.ultima || !confirm("Cancelar este agendamento?")) return;
    await cancelar(estado.ultima.id, estado.ultima.codigo_cancelamento);
  });
  $("novo-agendamento").addEventListener("click", voltarAoFormulario);

  $("form-cancelar-codigo").addEventListener("submit", async (evento) => {
    evento.preventDefault();
    const feito = await cancelar(Number($("codigo-id").value), $("codigo-valor").value.trim());
    if (feito) evento.target.reset();
  });

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

  const guardado = lerGuardado();
  if (guardado) mostrarConfirmacao(guardado);
}

iniciar();
