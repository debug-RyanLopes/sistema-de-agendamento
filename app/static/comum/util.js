export const $ = (id) => document.getElementById(id);

export async function api(metodo, caminho, corpo) {
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
    return { ok: resposta.ok, status: resposta.status, dados, cabecalhos: resposta.headers };
  } catch {
    return { ok: false, status: 0, dados: { detail: "Não foi possível falar com a API. Ela está rodando?" } };
  }
}

export function detalhe(dados) {
  if (!dados || dados.detail === undefined) return "erro desconhecido";
  if (Array.isArray(dados.detail)) {
    return dados.detail.map((erro) => `${erro.loc.slice(1).join(".")}: ${erro.msg}`).join("; ");
  }
  return dados.detail;
}

export function mensagem(tipo, texto) {
  const caixa = $("mensagem");
  caixa.className = `mensagem ${tipo}`;
  caixa.textContent = texto;
  caixa.hidden = false;
}

export function falha(resposta) {
  const prefixo = resposta.status ? `Erro ${resposta.status}: ` : "";
  mensagem("erro", `${prefixo}${detalhe(resposta.dados)}`);
}

export function formatarData(iso) {
  return `${iso.slice(8, 10)}/${iso.slice(5, 7)}/${iso.slice(0, 4)}`;
}

export function formatarDataHora(iso) {
  return `${formatarData(iso)} ${iso.slice(11, 16)}`;
}

export function formatarTelefone(valor) {
  const digitos = String(valor).replace(/\D/g, "");
  if (digitos.length === 11) return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 7)}-${digitos.slice(7)}`;
  if (digitos.length === 10) return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 6)}-${digitos.slice(6)}`;
  return String(valor);
}

export function reais(valor) {
  return `R$ ${Number(valor).toFixed(2).replace(".", ",")}`;
}

export function criarOpcao(valor, texto) {
  const opcao = document.createElement("option");
  opcao.value = valor;
  opcao.textContent = texto;
  return opcao;
}

export function preencherSelect(select, itens, rotulo, vazio) {
  const anterior = select.value;
  select.replaceChildren();
  if (vazio) select.append(criarOpcao("", vazio));
  itens.forEach((item) => select.append(criarOpcao(item.id, rotulo(item))));
  if ([...select.options].some((opcao) => opcao.value === anterior)) select.value = anterior;
}

export function elemento(tag, propriedades = {}, ...filhos) {
  const no = document.createElement(tag);
  Object.entries(propriedades).forEach(([chave, valor]) => {
    if (chave === "classe") no.className = valor;
    else if (chave === "aoClicar") no.addEventListener("click", valor);
    else if (chave in no) no[chave] = valor;
    else no.setAttribute(chave, valor);
  });
  filhos.flat().forEach((filho) => no.append(filho));
  return no;
}

// Fuso e grade de horários vêm do servidor (GET /configuracao); estes são só o padrão
// até a resposta chegar.
export const configuracao = { fuso: "America/Manaus", slot_minutos: 15, intervalo_minutos: 0 };

export async function carregarConfiguracao() {
  const resposta = await api("GET", "/configuracao");
  if (resposta.ok) Object.assign(configuracao, resposta.dados);
  document.querySelectorAll("[data-fuso]").forEach((no) => {
    no.textContent = descreverFuso(configuracao.fuso);
  });
  return configuracao;
}

export function descreverFuso(fuso) {
  try {
    const partes = new Intl.DateTimeFormat("pt-BR", { timeZone: fuso, timeZoneName: "shortOffset" }).formatToParts(new Date());
    const nome = partes.find((parte) => parte.type === "timeZoneName")?.value ?? "";
    return `${fuso.split("/").pop().replace("_", " ")} (${nome})`;
  } catch {
    return fuso;
  }
}

export function dataLocalHoje() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: configuracao.fuso });
}

export function agoraLocalIso() {
  // "AAAA-MM-DDTHH:MM" no fuso da barbearia, para comparar com os horários da API.
  const partes = new Intl.DateTimeFormat("sv-SE", {
    timeZone: configuracao.fuso, hourCycle: "h23",
    year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
  }).format(new Date());
  return partes.replace(" ", "T");
}

export function ultimoDiaDoMes(iso) {
  const [ano, mes] = iso.split("-").map(Number);
  const ultimo = new Date(Date.UTC(ano, mes, 0)).getUTCDate();
  return `${iso.slice(0, 8)}${String(ultimo).padStart(2, "0")}`;
}

export const STATUS_ROTULO = {
  agendado: "agendado",
  cancelado: "cancelado",
  concluido: "concluído",
  nao_compareceu: "faltou",
};

export function ocupado(botao, texto) {
  // Evita duplo clique: desabilita enquanto a requisição está em andamento.
  const original = botao.textContent;
  botao.disabled = true;
  if (texto) botao.textContent = texto;
  return () => {
    botao.disabled = false;
    botao.textContent = original;
  };
}

// --- validação no navegador (o servidor valida de novo; aqui é só para avisar antes) --------

export const REGEX_EMAIL = /^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$/;

export function validarEmail(valor) {
  const texto = String(valor).trim();
  if (!texto) return "Informe o e-mail.";
  if (!REGEX_EMAIL.test(texto)) return "E-mail inválido. Ex.: nome@exemplo.com";
  return "";
}

export function validarTelefone(valor) {
  const digitos = String(valor).replace(/\D/g, "");
  if (!digitos) return "Informe o telefone com DDD.";
  if (digitos.startsWith("0") || (digitos.length !== 10 && digitos.length !== 11)) {
    return "Informe o telefone com DDD. Ex.: (92) 91234-5678";
  }
  if (digitos.length === 11 && digitos[2] !== "9") return "Celular com 11 dígitos deve ter 9 depois do DDD.";
  if (digitos.length === 10 && !"2345".includes(digitos[2])) return "Telefone fixo deve começar com 2, 3, 4 ou 5 depois do DDD.";
  return "";
}

export function validarNome(valor, maximo = 120) {
  const texto = String(valor).trim();
  if (texto.length < 2) return "Informe o nome (pelo menos 2 letras).";
  if (texto.length > maximo) return `O nome pode ter no máximo ${maximo} caracteres.`;
  return "";
}

export function mascararTelefone(valor) {
  const digitos = String(valor).replace(/\D/g, "").slice(0, 11);
  if (digitos.length <= 2) return digitos;
  if (digitos.length <= 6) return `(${digitos.slice(0, 2)}) ${digitos.slice(2)}`;
  if (digitos.length <= 10) return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 6)}-${digitos.slice(6)}`;
  return `(${digitos.slice(0, 2)}) ${digitos.slice(2, 7)}-${digitos.slice(7)}`;
}

function caixaDeErro(campo) {
  let caixa = campo.parentElement.querySelector(".erro-campo");
  if (!caixa) {
    caixa = document.createElement("small");
    caixa.className = "erro-campo";
    caixa.setAttribute("aria-live", "polite");
    campo.parentElement.append(caixa);
  }
  return caixa;
}

// Liga a validação a um campo: mostra a mensagem embaixo dele e bloqueia o envio do formulário.
export function validarCampo(campo, validador) {
  const aplicar = () => {
    const erro = validador(campo.value);
    campo.setCustomValidity(erro);
    campo.classList.toggle("invalido", Boolean(erro) && campo.value !== "");
    caixaDeErro(campo).textContent = campo.value === "" ? "" : erro;
    return !erro;
  };
  campo.addEventListener("input", aplicar);
  campo.addEventListener("blur", aplicar);
  campo.addEventListener("invalid", () => {
    caixaDeErro(campo).textContent = campo.validationMessage;
  });
  return aplicar;
}

export function aplicarMascaraDeTelefone(campo) {
  campo.addEventListener("input", () => {
    const posicaoFim = campo.selectionEnd === campo.value.length;
    campo.value = mascararTelefone(campo.value);
    if (posicaoFim) campo.setSelectionRange(campo.value.length, campo.value.length);
  });
}
