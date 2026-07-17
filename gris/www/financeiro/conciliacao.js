// Conciliação: comparar transações de Sistema x Planilha, vincular e categorizar.
(function () {
  const API = 'gris.api.financeiro.conciliacao';
  let sistemaAtual = null; // objeto da transação de sistema selecionada
  let candidatos = [];
  let candidatoAtual = null; // name do candidato de planilha selecionado

  function parseNumber(v) {
    const n = typeof v === 'number' ? v : parseFloat(v || 0);
    return Number.isFinite(n) ? n : 0;
  }

  function fmtMoney(v) {
    return parseNumber(v).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
  }

  function fmtData(v) {
    if (!v) return '—';
    const d = String(v).split(' ')[0].split('-');
    return d.length === 3 ? `${d[2]}/${d[1]}/${d[0]}` : String(v);
  }

  function esc(v) {
    if (v === null || v === undefined || v === '') return '';
    return String(v).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  function traco(v) {
    return v === null || v === undefined || v === '' ? '<span class="conciliacao-comparacao__vazio">—</span>' : esc(v);
  }

  function selVal(containerId) {
    const el = document.querySelector('#' + containerId + ' input[type="hidden"]');
    return el ? (el.value || '').trim() : '';
  }

  function dataDe(t) {
    return t ? t.data_deposito || t.timestamp_transacao || t.data_transacao : null;
  }

  function badge(texto, classe) {
    return `<span class="badge${classe ? ' ' + classe : ''}">${esc(texto)}</span>`;
  }

  function setLoading(on) {
    document.getElementById('conc-loading')?.classList.toggle('hidden', !on);
  }

  /** Monta a tabela Campo | Sistema | Planilha, destacando divergências. */
  function renderComparacao(sistema, planilha) {
    const linhas = [
      ['Data', fmtData(dataDe(sistema)), planilha ? fmtData(dataDe(planilha)) : null, true],
      ['Valor', fmtMoney(sistema.valor), planilha ? fmtMoney(planilha.valor) : null, true],
      ['Descrição', sistema.descricao || sistema.descricao_reduzida, planilha ? planilha.descricao || planilha.descricao_reduzida : null, false],
      ['Método', sistema.metodo, planilha ? planilha.metodo : null, false],
      ['Instituição', sistema.instituicao, planilha ? planilha.instituicao : null, false],
      ['Carteira', sistema.carteira, planilha ? planilha.carteira : null, false],
      ['Categoria', sistema.categoria, planilha ? planilha.categoria : null, false],
      ['Centro de custo', sistema.centro_de_custo, planilha ? planilha.centro_de_custo : null, false],
      ['Tipo', sistema.ordinaria_extraordinaria, planilha ? planilha.ordinaria_extraordinaria : null, false],
    ];

    const corpo = document.getElementById('conc-comparacao-corpo');
    corpo.innerHTML = linhas
      .map(([campo, vSis, vPla, numerico]) => {
        // Só marca divergência quando há um candidato para comparar.
        const diff = planilha && String(vSis || '') !== String(vPla || '');
        const cls = numerico ? ' class="conciliacao-valor-num"' : '';
        const pla = planilha ? traco(vPla) : '<span class="conciliacao-comparacao__vazio">Selecione um candidato</span>';
        return `<tr data-diff="${diff ? 'true' : 'false'}">
          <th scope="row">${campo}</th>
          <td${cls}>${traco(vSis)}</td>
          <td${cls}>${pla}</td>
        </tr>`;
      })
      .join('');
  }

  async function carregarPendentes() {
    const lista = document.getElementById('conc-lista-pendentes');
    const count = document.getElementById('conc-pendentes-count');
    if (!lista) return;
    lista.innerHTML = '<p class="m-0 text-sm text-muted-foreground">Carregando…</p>';
    try {
      const resp = await frappe.call({
        method: API + '.get_sistema_pendentes',
        args: { carteira: selVal('conc-filtro-carteira') },
      });
      const itens = resp.message || [];
      if (count) count.textContent = String(itens.length);

      if (!itens.length) {
        lista.innerHTML = '<p class="m-0 text-sm text-muted-foreground">Nenhuma transação de sistema pendente.</p>';
        return;
      }

      lista.innerHTML = itens
        .map((t) => {
          const neg = parseNumber(t.valor) < 0 ? ' conciliacao-item__valor--negativo' : '';
          const desc = t.descricao || t.descricao_reduzida || '';
          return `<button type="button" class="conciliacao-item" role="option" aria-selected="false" data-id="${esc(t.name)}">
            <span class="conciliacao-item__topo">
              <span class="conciliacao-item__valor${neg}">${fmtMoney(t.valor)}</span>
              <span class="conciliacao-item__data">${fmtData(dataDe(t))}</span>
            </span>
            <p class="conciliacao-item__descricao" title="${esc(desc)}">${esc(desc) || '—'}</p>
            <span class="conciliacao-item__meta">${t.carteira ? badge(t.carteira) : ''}</span>
          </button>`;
        })
        .join('');

      lista.querySelectorAll('.conciliacao-item').forEach((btn) => {
        btn.addEventListener('click', () => selecionarSistema(btn.dataset.id));
      });
    } catch (e) {
      lista.innerHTML = '<p class="m-0 text-sm text-destructive">Erro ao carregar pendentes.</p>';
      console.error(e);
    }
  }

  async function selecionarSistema(sistemaId) {
    candidatoAtual = null;
    document.getElementById('conc-vazio')?.classList.add('hidden');
    document.getElementById('conc-comparacao')?.classList.remove('hidden');
    const btnConc = document.getElementById('conc-btn-conciliar');
    if (btnConc) btnConc.disabled = true;

    document.querySelectorAll('.conciliacao-item').forEach((b) => {
      b.setAttribute('aria-selected', b.dataset.id === sistemaId ? 'true' : 'false');
    });

    const candDiv = document.getElementById('conc-candidatos');
    candDiv.innerHTML = '<p class="m-0 text-sm text-muted-foreground">Buscando candidatos…</p>';

    try {
      const resp = await frappe.call({ method: API + '.get_candidatos_planilha', args: { sistema_id: sistemaId } });
      const data = resp.message || {};
      sistemaAtual = data.sistema;
      candidatos = data.candidatos || [];

      renderComparacao(sistemaAtual, null);

      if (!candidatos.length) {
        candDiv.innerHTML =
          '<p class="m-0 text-sm text-muted-foreground">Nenhum candidato encontrado na planilha. Se não for duplicada, use “Não é duplicata”.</p>';
        return;
      }

      candDiv.innerHTML = candidatos
        .map((t) => {
          const desc = t.descricao || t.descricao_reduzida || '';
          const difVal = parseNumber(t._diff_valor);
          const match = difVal === 0 ? 'valor idêntico' : `difere ${fmtMoney(difVal)}`;
          return `<label class="conciliacao-candidato">
            <input type="radio" name="conc-candidato" value="${esc(t.name)}" class="conciliacao-candidato__radio" />
            <span class="conciliacao-candidato__corpo">
              <span class="conciliacao-candidato__topo">
                <span class="conciliacao-item__valor conciliacao-valor-num">${fmtMoney(t.valor)}</span>
                <span class="conciliacao-item__data">${fmtData(dataDe(t))}</span>
              </span>
              <p class="conciliacao-candidato__descricao" title="${esc(desc)}">${esc(desc) || '—'}</p>
              <span class="conciliacao-candidato__meta">
                ${t.categoria ? badge(t.categoria) : ''}
                <span class="conciliacao-candidato__match">${match}</span>
              </span>
            </span>
          </label>`;
        })
        .join('');

      candDiv.querySelectorAll('input[name="conc-candidato"]').forEach((radio) => {
        radio.addEventListener('change', () => {
          candidatoAtual = radio.value;
          const t = candidatos.find((c) => c.name === radio.value);
          renderComparacao(sistemaAtual, t);
          if (btnConc) btnConc.disabled = false;
        });
      });
    } catch (e) {
      candDiv.innerHTML = '<p class="m-0 text-sm text-destructive">Erro ao buscar candidatos.</p>';
      console.error(e);
    }
  }

  function categorizacaoArgs() {
    return {
      categoria: selVal('conc-categoria'),
      descricao_reduzida: (document.getElementById('conc-descricao')?.value || '').trim(),
      centro_de_custo: selVal('conc-centro'),
      ordinaria_extraordinaria: selVal('conc-tipo'),
    };
  }

  function resetComparacao() {
    sistemaAtual = null;
    candidatoAtual = null;
    candidatos = [];
    document.getElementById('conc-comparacao')?.classList.add('hidden');
    document.getElementById('conc-vazio')?.classList.remove('hidden');
    const desc = document.getElementById('conc-descricao');
    if (desc) desc.value = '';
  }

  window.conciliarPar = async function () {
    if (!sistemaAtual || !candidatoAtual) {
      frappe.show_alert({ message: 'Selecione um candidato da planilha.', indicator: 'orange' });
      return;
    }
    setLoading(true);
    try {
      const args = Object.assign(
        {
          sistema_id: sistemaAtual.name,
          planilha_id: candidatoAtual,
          manter: selVal('conc-manter') || 'sistema',
        },
        categorizacaoArgs(),
      );
      await frappe.call({ method: API + '.conciliar', args });
      frappe.show_alert({ message: 'Transações conciliadas.', indicator: 'green' });
      resetComparacao();
      await carregarPendentes();
    } catch (e) {
      frappe.show_alert({ message: 'Erro ao conciliar.', indicator: 'red' });
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  window.marcarSemDuplicata = async function () {
    if (!sistemaAtual) return;
    setLoading(true);
    try {
      const args = Object.assign({ sistema_id: sistemaAtual.name }, categorizacaoArgs());
      await frappe.call({ method: API + '.marcar_sem_duplicata', args });
      frappe.show_alert({ message: 'Marcada como não duplicada.', indicator: 'blue' });
      resetComparacao();
      await carregarPendentes();
    } catch (e) {
      frappe.show_alert({ message: 'Erro ao resolver transação.', indicator: 'red' });
      console.error(e);
    } finally {
      setLoading(false);
    }
  };

  frappe.ready(() => {
    carregarPendentes();
    const filtro = document.querySelector('#conc-filtro-carteira input[type="hidden"]');
    if (filtro) filtro.addEventListener('change', carregarPendentes);
  });
})();
