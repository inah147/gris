let npsChart;
let currentPeriod = 'monthly';

frappe.ready(function() {
    loadSurveys();
    loadNpsChart();
    
    $('#btn-period-monthly').click(function() {
        setPeriod('monthly');
    });
    
    $('#btn-period-weekly').click(function() {
        setPeriod('weekly');
    });
    
    $('#f-search').on('input', function() {
        const val = $(this).val().toLowerCase();
        $('#survey-list tr').each(function() {
            const text = $(this).text().toLowerCase();
            $(this).toggle(text.indexOf(val) > -1);
        });
    });

    // Modal close handlers
    $('[data-modal-close], #detail-modal-backdrop').on('click', function() {
        $('#detail-modal').hide();
        $('#detail-modal-backdrop').hide();
    });
});

function loadSurveys() {
    frappe.call({
        method: "gris.www.recepcao.pesquisa_novos_respostas.get_surveys",
        callback: function(r) {
            if (r.message) {
                renderTable(r.message);
            }
        }
    });
}

function renderTable(data) {
    const tbody = $('#survey-list');
    tbody.empty();
    
    if (data.length === 0) {
        tbody.append('<tr><td colspan="4" class="text-center text-muted p-4">Nenhuma resposta encontrada.</td></tr>');
        return;
    }

    data.forEach(row => {
        const tr = $(`
            <tr>
                <td>${row.responsavel_nome || row.responsavel}</td>
                <td>${row.creation_formatted}</td>
                <td><span class="badge-nps nps-${getNpsClass(row.nps_recepcao)}">${row.nps_recepcao}</span></td>
                <td>
                    <button class="btn-modern btn-modern--sm btn-modern--outline" onclick="openDetails('${row.name}')">
                        Ver Detalhes
                    </button>
                </td>
            </tr>
        `);
        tbody.append(tr);
    });
}

function getNpsClass(score) {
    score = parseInt(score);
    if (score >= 9) return 'promoter';
    if (score >= 7) return 'neutral';
    return 'detractor';
}

window.openDetails = function(name) {
    frappe.call({
        method: "gris.www.recepcao.pesquisa_novos_respostas.get_survey_details",
        args: { survey_name: name },
        freeze: true,
        callback: function(r) {
            if (r.message) {
                renderModal(r.message);
                $('#detail-modal').css('display', 'flex');
                $('#detail-modal-backdrop').show();
            }
        }
    });
};

function renderModal(data) {
    const s = data.survey;
    const b = data.beneficiarios;
    
    let html = `
        <div class="mb-4">
            <h6 class="text-muted mb-2 text-uppercase small fw-bold">Responsável</h6>
            <p class="fw-bold mb-0" style="font-size: 1.1rem;">${s.responsavel_nome || s.responsavel}</p>
        </div>
        
        <div class="mb-4">
            <h6 class="text-muted mb-2 text-uppercase small fw-bold">Beneficiários Vinculados</h6>
            ${b.length ? '<ul class="list-unstyled mb-0">' + b.map(x => `<li class="mb-1">${x.nome_completo} <span class="badge bg-light text-dark border">${x.tipo}</span></li>`).join('') + '</ul>' : '<p class="text-muted fst-italic mb-0">Nenhum beneficiário encontrado.</p>'}
        </div>
        
        <hr class="my-4">
        
        <div class="survey-answers">
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">Como conheceu o Movimento?</label>
                <p>${s.como_conheceu_movimento || '-'}</p>
            </div>
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">Como conheceu o Grupo?</label>
                <p>${s.como_você_conheceu_o_nosso_grupo_escoteiro || '-'}</p>
            </div>
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">Visão sobre o Movimento</label>
                <p>${s.visao_sobre_movimento || '-'}</p>
            </div>
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">O que espera encontrar</label>
                <p>${s.espera_encontrar_movimento || '-'}</p>
            </div>
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">O que chamou atenção</label>
                <p>${s.chamou_atencao_uel || '-'}</p>
            </div>
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">NPS Recepção</label>
                <div><span class="badge-nps nps-${getNpsClass(s.nps_recepcao)}">${s.nps_recepcao}</span></div>
            </div>
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">Pontos Fortes</label>
                <p>${s.pontos_fortes_recepcao || '-'}</p>
            </div>
            <div class="mb-3">
                <label class="fw-bold small text-muted text-uppercase">Pontos a Melhorar</label>
                <p>${s.pontos_melhorar_recepcao || '-'}</p>
            </div>
        </div>
    `;
    
    $('#modal-body-content').html(html);
}

function setPeriod(period) {
    currentPeriod = period;
    
    // Update buttons
    if (period === 'monthly') {
        $('#btn-period-monthly').removeClass('btn-modern--outline').addClass('btn-modern--primary');
        $('#btn-period-weekly').removeClass('btn-modern--primary').addClass('btn-modern--outline');
    } else {
        $('#btn-period-weekly').removeClass('btn-modern--outline').addClass('btn-modern--primary');
        $('#btn-period-monthly').removeClass('btn-modern--primary').addClass('btn-modern--outline');
    }
    
    loadNpsChart();
}

function loadNpsChart() {
    frappe.call({
        method: "gris.www.recepcao.pesquisa_novos_respostas.get_nps_chart_data",
        args: { period: currentPeriod },
        callback: function(r) {
            if (r.message) {
                renderChart(r.message);
            }
        }
    });
}

function renderChart(data) {
    if (!frappe.Chart && window['frappe-charts'] && window['frappe-charts'].Chart) {
        frappe.Chart = window['frappe-charts'].Chart;
    }

    if (!npsChart) {
        npsChart = new frappe.Chart("#nps-chart", {
            data: data,
            type: 'line',
            height: 250,
            colors: ['#2563eb'],
            lineOptions: {
                regionFill: 1
            },
            axisOptions: {
                xIsSeries: true
            }
        });
    } else {
        npsChart.update(data);
    }
}
