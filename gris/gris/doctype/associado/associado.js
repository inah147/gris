// Copyright (c) 2025, Grupo Escoteiro Professora Inah de Mello - 47/SP and contributors
// For license information, please see license.txt

function update_tipo_guarda_properties(frm) {
    const hide = frm.doc.pais_divorciados === "Não";
    frm.set_df_property("tipo_guarda", "hidden", hide);
    frm.set_df_property("tipo_guarda", "reqd", !hide);
}

function update_guardiao_legal_responsavel_1_properties(frm) {
    const hide = frm.doc.tipo_guarda !== "Unilateral";
    frm.set_df_property("guardiao_legal_responsavel_1", "hidden", hide);
    frm.set_df_property("guardiao_legal_responsavel_1", "reqd", !hide);
}

function update_guardiao_legal_responsavel_2_properties(frm) {
    const hide = frm.doc.tipo_guarda !== "Unilateral";
    frm.set_df_property("guardiao_legal_responsavel_2", "hidden", hide);
    frm.set_df_property("guardiao_legal_responsavel_2", "reqd", !hide);
}

function update_eleito_properties(frm) {
    const hide = frm.doc.funcao !== "Diretor";
    frm.set_df_property("eleito", "hidden", hide);
}

function update_area_properties(frm) {
    const hide = frm.doc.categoria === "Beneficiário";
    frm.set_df_property("area", "hidden", hide);
}

function update_responsaveis_tab_properties(frm) {
    // Calcula a idade
    let idade = 0;
    if (frm.doc.data_de_nascimento) {
        const nascimento = new Date(frm.doc.data_de_nascimento);
        const hoje = new Date();
        idade = hoje.getFullYear() - nascimento.getFullYear();
        const m = hoje.getMonth() - nascimento.getMonth();
        if (m < 0 || (m === 0 && hoje.getDate() < nascimento.getDate())) {
            idade--;
        }
    }

    const maior_de_idade = idade > 18;

    // Define obrigatoriedade dos campos
    const campos = [
        // "nome_responsavel_1",
        // "estado_civil_responsavel_1",
        // "telefone_responsavel_1",
        // "email_responsavel_1",
        // "cpf_responsavel_1"
    ];
    campos.forEach(campo => {
        frm.set_df_property(campo, "reqd", !maior_de_idade);
    });
}

function set_fields_read_only(frm) {
    // Lista de campos que nunca devem ser read only
    const excecoes = [
        "anos_afastamento",
        "pais_divorciados",
        "tipo_guarda",
        "guardiao_legal_responsavel_1",
        "guardiao_legal_responsavel_2",
        "eleito",
        "area",
        "historico_no_grupo",
        "route",
        "cpf",
        "status_cobranca"
    ];

    // Percorre todos os campos do formulário
    frm.fields_dict && Object.keys(frm.fields_dict).forEach(fieldname => {
        if (!excecoes.includes(fieldname)) {
            const valor = frm.doc[fieldname];
            // Torna read only se já estiver preenchido (não vazio, não nulo)
            frm.set_df_property(fieldname, "read_only", 1);
        }
    });
}

function enforce_guardiao_exclusivity(frm, changed_field) {
    if (changed_field === "guardiao_legal_responsavel_1" && frm.doc.guardiao_legal_responsavel_1 === 1) {
        if (frm.doc.guardiao_legal_responsavel_2 === 1) {
            frm.set_value("guardiao_legal_responsavel_2", 0);
        }
    }
    if (changed_field === "guardiao_legal_responsavel_2" && frm.doc.guardiao_legal_responsavel_2 === 1) {
        if (frm.doc.guardiao_legal_responsavel_1 === 1) {
            frm.set_value("guardiao_legal_responsavel_1", 0);
        }
    }
}


frappe.ui.form.on("Associado", {
	pais_divorciados(frm) {
        update_tipo_guarda_properties(frm);
    },
    tipo_guarda(frm) {
        update_guardiao_legal_responsavel_1_properties(frm);
        update_guardiao_legal_responsavel_2_properties(frm);
    },
    data_de_nascimento(frm) {
        update_responsaveis_tab_properties(frm);
    },
    guardiao_legal_responsavel_1(frm) {
        enforce_guardiao_exclusivity(frm, "guardiao_legal_responsavel_1");
    },
    guardiao_legal_responsavel_2(frm) {
        enforce_guardiao_exclusivity(frm, "guardiao_legal_responsavel_2");
    },
    eleito(frm) {
        update_eleito_properties(frm);
    },
    area(frm) {
        update_area_properties(frm);
    },
    refresh(frm) {
        update_tipo_guarda_properties(frm);
        update_guardiao_legal_responsavel_1_properties(frm);
        update_guardiao_legal_responsavel_2_properties(frm);
        update_responsaveis_tab_properties(frm);
        update_eleito_properties(frm);
        update_area_properties(frm);

        set_fields_read_only(frm);
        // Se ambos estiverem marcados, desmarca o segundo
        if (frm.doc.guardiao_legal_responsavel_1 === 1 && frm.doc.guardiao_legal_responsavel_2 === 1) {
            frm.set_value("guardiao_legal_responsavel_2", 0);
        }
    }
});
