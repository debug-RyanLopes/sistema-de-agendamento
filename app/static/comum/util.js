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
    return { ok: resposta.ok, status: resposta.status, dados };
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

export const FUSO = "America/Manaus";

export function dataLocalHoje() {
  return new Date().toLocaleDateString("sv-SE", { timeZone: FUSO });
}

export function ultimoDiaDoMes(iso) {
  const [ano, mes] = iso.split("-").map(Number);
  const ultimo = new Date(Date.UTC(ano, mes, 0)).getUTCDate();
  return `${iso.slice(0, 8)}${String(ultimo).padStart(2, "0")}`;
}
