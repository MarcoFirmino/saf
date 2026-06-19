document.addEventListener('DOMContentLoaded', function() {
    const somaDisplay = document.getElementById('soma-selecionada');
    const btnConciliar = document.getElementById('btn-conciliar-multiplas');
    const valorDepositoEl = document.getElementById('valor-deposito-display');
    const painelImpostos = document.getElementById('painel-impostos');
    const fileInput = document.getElementById('compo-excel-input');
    const alertaCompo = document.getElementById('alerta-composicao');
    
    // 1. Tornar as linhas clicáveis
    document.querySelectorAll('.linha-nota').forEach(tr => {
        tr.addEventListener('click', function(e) {
            const tag = e.target.tagName.toLowerCase();
            if (tag !== 'input' && tag !== 'button' && tag !== 'a') {
                const cb = this.querySelector('.nota-checkbox');
                if (cb) {
                    if (!cb.checked) {
                        cb.checked = true;
                        cb.dispatchEvent(new Event('change'));
                    } else {
                        abrirPainelImpostos(cb);
                    }
                }
            }
        });
    });

    if (valorDepositoEl) {
        const valorDeposito = parseFloat(valorDepositoEl.getAttribute('data-valor'));

        // ==========================================
        // 2. ATUALIZAR SOMA E SEMÁFORO
        // ==========================================
        function atualizarSoma(triggerCb = null) {
            let soma = 0;
            let checkedCount = 0;
            let firstChecked = null;

            document.querySelectorAll('.nota-checkbox').forEach(cb => {
                if (cb.checked) {
                    soma += parseFloat(cb.getAttribute('data-valor'));
                    checkedCount++;
                    if (!firstChecked) firstChecked = cb;
                }
            });

            const diferenca = soma - valorDeposito;
            let textoSoma = 'Soma: ' + soma.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });

            if (checkedCount > 0 && Math.abs(diferenca) > 0.009) {
                textoSoma += ' | Dif: ' + diferenca.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
            }

            if (somaDisplay) {
                somaDisplay.innerText = textoSoma;
                if (Math.abs(diferenca) < 0.01) {
                    somaDisplay.className = 'mb-0 px-3 py-1 rounded shadow-sm bg-success text-white';
                } else if (soma > valorDeposito) {
                    somaDisplay.className = 'mb-0 px-3 py-1 rounded shadow-sm bg-danger text-white';
                } else {
                    somaDisplay.className = 'mb-0 px-3 py-1 rounded shadow-sm bg-dark text-white';
                }
            }

            if (btnConciliar) {
                btnConciliar.disabled = (checkedCount === 0);
            }

            if (checkedCount === 0) {
                if(painelImpostos) painelImpostos.style.display = 'none';
                document.querySelectorAll('.linha-nota').forEach(tr => tr.classList.remove('table-warning'));
            } else {
                const currentId = document.getElementById('ajuste-nota-id') ? document.getElementById('ajuste-nota-id').value : '';
                const currentCb = document.querySelector(`.nota-checkbox[value="${currentId}"]`);

                if (triggerCb && triggerCb.checked) {
                    abrirPainelImpostos(triggerCb);
                } else if (triggerCb && !triggerCb.checked) {
                    if (currentId === triggerCb.value) {
                        abrirPainelImpostos(firstChecked);
                    }
                } else {
                    if (currentCb && currentCb.checked) {
                        abrirPainelImpostos(currentCb);
                    } else if (firstChecked) {
                        abrirPainelImpostos(firstChecked);
                    }
                }
            }
        }

        // ==========================================
        // 3. PAINEL DE IMPOSTOS
        // ==========================================
        function abrirPainelImpostos(cb) {
            if(!painelImpostos) return;
            painelImpostos.style.display = 'block';
            
            document.querySelectorAll('.linha-nota').forEach(tr => tr.classList.remove('table-warning'));
            cb.closest('tr').classList.add('table-warning');

            document.getElementById('ajuste-titulo-nota').innerText = cb.getAttribute('data-titulo');
            document.getElementById('ajuste-nota-id').value = cb.value;
            document.getElementById('ajuste-vl-bruto').value = cb.getAttribute('data-bruto');

            const excelVal = cb.getAttribute('data-excel');
            if (excelVal !== null && excelVal !== "") {
                painelImpostos.setAttribute('data-excel', excelVal);
            } else {
                painelImpostos.removeAttribute('data-excel');
            }

            const campos = ['pis', 'cofins', 'csll', 'irrf', 'iss', 'inss', 'desconto', 'abatimento', 'multa', 'juros'];
            campos.forEach(c => {
                let val = parseFloat(cb.getAttribute(`data-${c}`)) || 0;
                document.getElementById(`inp-${c}`).value = val.toFixed(2);
            });
            
            calcularImpostosEmTempoReal();
        }

        function calcularImpostosEmTempoReal() {
            const bruto = parseFloat(document.getElementById('ajuste-vl-bruto').value) || 0;
            const camposDeducao = ['inp-pis', 'inp-cofins', 'inp-csll', 'inp-irrf', 'inp-iss', 'inp-inss', 'inp-desconto', 'inp-abatimento'];
            const camposAcrescimo = ['inp-multa', 'inp-juros'];
            
            let deducoes = 0, acrescimos = 0;
            let totalPercTaxas = 0; 

            const listaImpostos = ['pis', 'cofins', 'csll', 'irrf', 'iss', 'inss'];
            listaImpostos.forEach(taxa => {
                const val = parseFloat(document.getElementById(`inp-${taxa}`).value) || 0;
                deducoes += val;
                
                const percSpan = document.getElementById(`perc-${taxa}`);
                if (bruto > 0 && val > 0) {
                    const perc = (val / bruto) * 100;
                    totalPercTaxas += perc;
                    if(percSpan) percSpan.innerText = `(${perc.toFixed(2).replace('.', ',')}%)`;
                } else {
                    if(percSpan) percSpan.innerText = '';
                }
            });

            ['inp-desconto', 'inp-abatimento'].forEach(id => {
                deducoes += (parseFloat(document.getElementById(id).value) || 0);
            });

            camposAcrescimo.forEach(id => acrescimos += (parseFloat(document.getElementById(id).value) || 0));
            
            const totalTxSpan = document.getElementById('ajuste-total-tx');
            if (totalTxSpan) {
                if (totalPercTaxas > 0) {
                    totalTxSpan.innerText = `- TOTAL TX ${totalPercTaxas.toFixed(2).replace('.', ',')}%`;
                } else {
                    totalTxSpan.innerText = '';
                }
            }

            const novoSaldo = bruto - deducoes + acrescimos;
            document.getElementById('calc-novo-saldo').innerText = novoSaldo.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
            
            const difEl = document.getElementById('calc-diferenca');
            const excelAttr = painelImpostos.getAttribute('data-excel');
            
            // =================================================================
            // CORREÇÃO DO CÁLCULO DE VARIAÇÃO (MÉTODO EXCEL)
            // =================================================================
            // No Excel: =([Vlr. Pago]/[Vl.Bruto]) * 100 - 100
            // 1. O Vlr. Pago por padrão é o valor do Depósito bancário
            let valorPagoCliente = valorDeposito; 
            
            // 2. Mas se a nota veio de uma importação de Excel, usamos o valor do Excel
            if (excelAttr && parseFloat(excelAttr) > 0) {
                valorPagoCliente = parseFloat(excelAttr);
            }

            // 3. Aplica a fórmula exata
            let variacao = 0;
            if (bruto > 0) {
                variacao = (valorPagoCliente / bruto) * 100 - 100;
            }
            
            const varEl = document.getElementById('calc-variacao');
            if (varEl) {
                varEl.innerText = variacao.toFixed(2).replace('.', ',') + '%';
            }

            // --- CÁLCULO DA DIFERENÇA FINANCEIRA ---
            if (difEl) {
                let diferencaImposto = 0;
                if (excelAttr) {
                    diferencaImposto = parseFloat(excelAttr) - novoSaldo;
                } else {
                    let somaTotalSimulada = 0;
                    const currentNotaId = document.getElementById('ajuste-nota-id').value;
                    document.querySelectorAll('.nota-checkbox').forEach(cb => {
                        if (cb.checked) {
                            if (cb.value === currentNotaId) {
                                somaTotalSimulada += novoSaldo;
                            } else {
                                somaTotalSimulada += parseFloat(cb.getAttribute('data-valor')) || 0;
                            }
                        }
                    });
                    diferencaImposto = somaTotalSimulada - valorDeposito;
                }
                
                difEl.innerText = diferencaImposto.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
                difEl.className = Math.abs(diferencaImposto) < 0.01 ? 'fw-bold text-success' : 'fw-bold text-danger';
            }
        
        }

        // Removemos o evento 'input' dos txt-inputs aqui, e passamos a usar o evento 'change' da calculadora mais abaixo.
        document.querySelectorAll('.tx-input').forEach(inp => {
            // Alterado de 'input' para 'change' para não ficar recalculando sem parar com o readonly
            inp.addEventListener('change', calcularImpostosEmTempoReal); 
        });

        // ==========================================
        // 4. SALVAR IMPOSTOS VIA AJAX (FETCH)
        // ==========================================
        const btnSalvar = document.getElementById('btn-salvar-impostos');
        if (btnSalvar) {
            btnSalvar.addEventListener('click', function() {
                const notaId = document.getElementById('ajuste-nota-id').value;
                const csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;
                
                const payload = {
                    acao: 'atualizar_impostos',
                    nota_id: notaId,
                    pis: document.getElementById('inp-pis').value,
                    cofins: document.getElementById('inp-cofins').value,
                    csll: document.getElementById('inp-csll').value,
                    irrf: document.getElementById('inp-irrf').value,
                    iss: document.getElementById('inp-iss').value,
                    inss: document.getElementById('inp-inss').value,
                    desconto: document.getElementById('inp-desconto').value,
                    abatimento: document.getElementById('inp-abatimento').value,
                    multa: document.getElementById('inp-multa').value,
                    juros: document.getElementById('inp-juros').value
                };

                btnSalvar.innerText = 'Salvando...';

                fetch(window.location.href, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfToken
                    },
                    body: JSON.stringify(payload)
                })
                .then(res => res.json())
                .then(data => {
                    btnSalvar.innerHTML = '<i class="bi bi-save"></i> Gravar Ajustes (Sem recarregar)';
                    
                    if (data.status === 'sucesso') {
                        const tr = document.getElementById(`tr-nota-${notaId}`);
                        const cb = tr.querySelector('.nota-checkbox');
                        const tdSaldo = tr.querySelector('.td-saldo-real');
                        
                        cb.setAttribute('data-valor', data.novo_saldo);
                        tdSaldo.innerHTML = `R$ ${data.novo_saldo.toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2})}`;
                        
                        Object.keys(payload).forEach(k => {
                            if (k !== 'acao' && k !== 'nota_id') cb.setAttribute(`data-${k}`, payload[k]);
                        });
                        
                        const tdVl = tr.querySelector('.td-vl-informado');
                        const tdDif = tr.querySelector('.td-diferenca');
                        if (tdVl && tdVl.innerText !== '-' && cb.getAttribute('data-excel')) {
                            const vlExcel = parseFloat(cb.getAttribute('data-excel')) || 0;
                            const novaDif = vlExcel - data.novo_saldo;
                            
                            tdDif.innerText = novaDif.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
                            if (Math.abs(novaDif) < 0.01) {
                                tdDif.className = 'text-end fw-bold col-compo td-diferenca text-success';
                            } else {
                                tdDif.className = 'text-end fw-bold col-compo td-diferenca text-danger';
                            }
                        }
                        
                        atualizarSoma(null); 
                    } else {
                        alert('Erro ao salvar: ' + data.message);
                    }
                });
            });
        }

        // ==========================================
        // 5. IMPORTAÇÃO DO EXCEL
        // ==========================================
        if (fileInput) {
            fileInput.addEventListener('change', function() {
                if (!this.files.length) return;
                
                const formData = new FormData();
                formData.append('compo_excel', this.files[0]);
                formData.append('extrato_id', document.querySelector('input[name="extrato_id"]').value);
                formData.append('csrfmiddlewaretoken', document.querySelector('[name=csrfmiddlewaretoken]').value);

                const lbl = document.querySelector(`label[for="compo-excel-input"]`);
                const oldHtml = lbl.innerHTML;
                lbl.innerHTML = '<i class="bi bi-hourglass-split"></i> Lendo Excel...';

                fetch(window.location.href, {
                    method: 'POST',
                    body: formData,
                    headers: { 'X-Requested-With': 'XMLHttpRequest' }
                })
                .then(res => res.json())
                .then(data => {
                    lbl.innerHTML = oldHtml;
                    this.value = ''; 

                    if (data.status === 'sucesso') {
                        document.querySelectorAll('.col-compo').forEach(el => el.classList.remove('d-none'));
                        document.querySelectorAll('.td-vl-informado').forEach(el => el.innerText = '-');
                        document.querySelectorAll('.td-diferenca').forEach(el => {
                            el.innerText = '-';
                            el.className = 'text-end fw-bold col-compo td-diferenca';
                        });

                        document.querySelectorAll('.nota-checkbox').forEach(cb => {
                            cb.checked = false;
                            cb.removeAttribute('data-excel'); 
                        });
                        
                        data.ids_encontrados.forEach(item => {
                            const cb = document.querySelector(`.nota-checkbox[value="${item.id}"]`);
                            if (cb) {
                                cb.checked = true;
                                cb.setAttribute('data-excel', item.valor_excel); 
                                
                                const tr = cb.closest('tr');
                                const tdVl = tr.querySelector('.td-vl-informado');
                                const tdDif = tr.querySelector('.td-diferenca');
                                
                                const saldoReal = parseFloat(cb.getAttribute('data-valor'));
                                const diferenca = item.valor_excel - saldoReal;
                                
                                tdVl.innerText = item.valor_excel.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
                                tdDif.innerText = diferenca.toLocaleString('pt-BR', {style: 'currency', currency: 'BRL'});
                                
                                if (Math.abs(diferenca) < 0.01) {
                                    tdDif.classList.add('text-success');
                                } else {
                                    tdDif.classList.add('text-danger');
                                }
                            }
                        });

                        atualizarSoma(null); 

                        alertaCompo.classList.remove('d-none', 'alert-info', 'alert-danger', 'alert-warning', 'alert-success');
                        alertaCompo.classList.add(data.nao_encontrados.length > 0 ? 'alert-warning' : 'alert-success');
                        
                        let htmlMsg = `<div class="d-flex justify-content-between align-items-center">
                                         <span><strong>Importação concluída!</strong> <span class="badge bg-dark">${data.qtd_encontrada} de ${data.qtd_importada}</span> notas foram localizadas e selecionadas.</span>
                                         <button type="button" class="btn-close btn-sm" onclick="document.getElementById('alerta-composicao').classList.add('d-none')"></button>
                                       </div>`;
                        
                        if (data.nao_encontrados.length > 0) {
                            htmlMsg += `<hr class="my-2"><p class="mb-1 fw-bold text-danger"><i class="bi bi-exclamation-triangle"></i> Atenção! As notas abaixo constam no Excel mas não foram localizadas neste CNPJ:</p>
                                        <div style="max-height: 100px; overflow-y: auto;">
                                        <ul class="mb-0">`;
                            data.nao_encontrados.forEach(n => {
                                htmlMsg += `<li>Nota: <strong>${n.nota}</strong> | Valor Pago: R$ ${n.valor.toFixed(2).replace('.', ',')}</li>`;
                            });
                            htmlMsg += `</ul></div>`;
                        }
                        alertaCompo.innerHTML = htmlMsg;

                    } else {
                        alert('Erro na importação: ' + data.message);
                    }
                })
                .catch(err => {
                    lbl.innerHTML = oldHtml;
                    alert('Erro de conexão ao enviar o arquivo.');
                });
            });
        }

        document.querySelectorAll('.nota-checkbox').forEach(cb => {
            cb.addEventListener('change', function() {
                atualizarSoma(this);
            });
        });

        atualizarSoma(null);
    }

    // ==========================================
    // 6. ORDENAÇÃO (SORT DA TABELA)
    // ==========================================
    const getCellValue = (tr, idx) => tr.children[idx].innerText || tr.children[idx].textContent;
    const comparer = (idx, type, asc) => (a, b) => {
        let v1 = getCellValue(asc ? a : b, idx).trim();
        let v2 = getCellValue(asc ? b : a, idx).trim();

        if (type === 'currency') {
            v1 = parseFloat(v1.replace(/\./g, '').replace(',', '.').replace(/[^\d.-]/g, '')) || 0;
            v2 = parseFloat(v2.replace(/\./g, '').replace(',', '.').replace(/[^\d.-]/g, '')) || 0;
            return v1 - v2;
        } else if (type === 'date') {
            const parseDate = d => {
                const p = d.split('/');
                return p.length === 3 ? p[2] + p[1] + p[0] : d;
            };
            return parseDate(v1).localeCompare(parseDate(v2));
        } else {
            return v1.localeCompare(v2, undefined, {numeric: true, sensitivity: 'base'});
        }
    };

    document.querySelectorAll('th.sortable').forEach(th => {
        th.addEventListener('click', function() {
            const table = th.closest('table');
            const tbody = table.querySelector('tbody');
            const type = this.dataset.sort;
            
            let asc = this.asc = !this.asc;
            table.querySelectorAll('th i').forEach(icon => icon.className = 'bi bi-arrow-down-up small text-muted');
            
            const icon = this.querySelector('i');
            if(icon) {
                icon.className = asc ? 'bi bi-arrow-up small text-dark fw-bold' : 'bi bi-arrow-down small text-dark fw-bold';
            }

            Array.from(tbody.querySelectorAll('tr.linha-nota'))
                .sort(comparer(Array.from(th.parentNode.children).indexOf(th), type, asc))
                .forEach(tr => tbody.appendChild(tr));
        });
    });
// ==============================================================================
// 7. MODAL CALCULADORA DE PORCENTAGEM (IMPOSTOS E DESCONTOS)
// ==============================================================================
    let inputAlvoOriginal = null;
    let valorBrutoAtual = 0;
    let resultadoCalculado = 0;
    let calculoRealizado = false; // <-- NOVA FLAG: Sabe se o usuário clicou em calcular

    // Inicializa o modal do Bootstrap (Verifica se ele existe na tela para não dar erro)
    const modalEl = document.getElementById('modalCalculadora');
    if (modalEl) {
        const modalCalculadora = new bootstrap.Modal(modalEl);

        // Mapeia os elementos do modal
        const calcValorBrutoText = document.getElementById('calcValorBrutoText');
        const calcPercentual = document.getElementById('calcPercentual');
        const calcResultadoText = document.getElementById('calcResultadoText');
        const btnCalcular = document.getElementById('btnCalcularPercentual');
        const btnConfirmar = document.getElementById('btnConfirmarCalculo');

        // ESCUTA O CLIQUE NOS CAMPOS DE IMPOSTO
        const inputsCalculaveis = document.querySelectorAll('.acionar-calculadora');
        
        inputsCalculaveis.forEach(input => {
            input.addEventListener('click', function() {
                inputAlvoOriginal = this; 

                // Pega o valor bruto DIRETAMENTE do campo oculto do painel
                valorBrutoAtual = parseFloat(document.getElementById('ajuste-vl-bruto').value) || 0;

                // Limpa o modal para uma nova conta
                calcPercentual.value = '';
                resultadoCalculado = 0;
                calculoRealizado = false; // Reseta a flag ao abrir
                calcResultadoText.innerText = '0.00';
                calcValorBrutoText.innerText = valorBrutoAtual.toLocaleString('pt-BR', {minimumFractionDigits: 2});

                // Abre o modal
                modalCalculadora.show();
            });
        });

        // Coloca o cursor automaticamente no campo ao abrir
        modalEl.addEventListener('shown.bs.modal', () => {
            calcPercentual.focus();
        });

        // Se o usuário voltar a digitar algo, apagamos a flag do cálculo
        if (calcPercentual) {
            calcPercentual.addEventListener('input', function() {
                calculoRealizado = false; 
            });
        }

        // AÇÃO DO BOTÃO "CALCULAR"
        if (btnCalcular) {
            btnCalcular.addEventListener('click', function() {
                // Pega a porcentagem digitada
                let valorDigitado = parseFloat(calcPercentual.value.replace(',', '.')) || 0;
                
                // Faz a conta como porcentagem
                resultadoCalculado = (valorBrutoAtual * valorDigitado) / 100;
                
                // Mostra o resultado na legenda
                calcResultadoText.innerText = resultadoCalculado.toFixed(2);
                calculoRealizado = true; // Avisa o sistema que o cálculo de % foi feito!
            });
        }

        // AÇÃO DO BOTÃO "OK"
        if (btnConfirmar) {
            btnConfirmar.addEventListener('click', function() {
                
                // A MÁGICA ACONTECE AQUI:
                // Se NÃO clicou em calcular, e tem um valor maior que zero digitado:
                if (!calculoRealizado) {
                    let valorDigitado = parseFloat(calcPercentual.value.replace(',', '.')) || 0;
                    if (valorDigitado > 0) {
                        // Assume o valor digitado diretamente em Reais (R$)
                        resultadoCalculado = valorDigitado; 
                        // Atualiza a legenda interna para respeitar o fluxo (mesmo fechando rápido)
                        calcResultadoText.innerText = resultadoCalculado.toFixed(2); 
                    }
                }

                if(inputAlvoOriginal) {
                    // Joga o valor (seja ele a porcentagem calculada ou o valor absoluto) de volta
                    inputAlvoOriginal.value = resultadoCalculado.toFixed(2);
                    
                    // Dispara o evento para salvar no banco
                    inputAlvoOriginal.dispatchEvent(new Event('change', { bubbles: true }));
                }
                
                // Fecha o modal
                modalCalculadora.hide();
            });
        }
    }
    // ==============================================================================
    // 8. DISPARO DE E-MAIL (OUTLOOK)
    // ==============================================================================
    const btnEnviarEmail = document.getElementById('btnEnviarEmailOutlook');
    if (btnEnviarEmail) {
        btnEnviarEmail.addEventListener('click', function() {
            
            const inputEmailRaw = document.getElementById('inputEmailCliente') ? document.getElementById('inputEmailCliente').value.trim() : "";
            const cnpjBusca = document.getElementById('cnpjAtivoBusca') ? document.getElementById('cnpjAtivoBusca').value : "";
            
            if (!inputEmailRaw) {
                alert("Por favor, preencha o e-mail do cliente.");
                return;
            }

            const inputEmailFormatado = inputEmailRaw.replace(/;/g, ',').replace(/\s/g, '');

            const csrfTokenEl = document.querySelector('[name=csrfmiddlewaretoken]');
            if (csrfTokenEl) {
                fetch(window.location.href, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Requested-With': 'XMLHttpRequest',
                        'X-CSRFToken': csrfTokenEl.value
                    },
                    body: JSON.stringify({ acao: 'salvar_email', cnpj: cnpjBusca, email: inputEmailRaw })
                }).catch(e => console.log("Aviso Ajax:", e));
            }

            const valorDep = document.getElementById('valorDepositoEmail') ? document.getElementById('valorDepositoEmail').value : "0,00";
            const dataDep = document.getElementById('dataDepositoEmail') ? document.getElementById('dataDepositoEmail').value : "";
            
            // ================================================================
            // NOVIDADE: EXTRAINDO NOME DO CLIENTE E RAIZ DO CNPJ
            // ================================================================
            const nomeCliente = document.getElementById('nomeClienteEmail') ? document.getElementById('nomeClienteEmail').value.trim() : "Cliente";
            let raizCnpj = "";
            
            if (cnpjBusca) {
                // Remove tudo que não for número (pontos, barras, traços)
                const numerosCnpj = cnpjBusca.replace(/\D/g, ''); 
                if (numerosCnpj.length >= 8) {
                    // Pega os 8 primeiros dígitos e formata como XX.XXX.XXX
                    const r = numerosCnpj.substring(0, 8);
                    raizCnpj = `${r.substring(0,2)}.${r.substring(2,5)}.${r.substring(5,8)}`;
                } else {
                    raizCnpj = cnpjBusca; // Fallback caso venha algo estranho
                }
            }

            // 1. LÊ OS DADOS DO JSON (CNPJs e Estabs)
            let dadosEstabsStr = "[]";
            const tagDados = document.getElementById('dadosEstabsJson');
            if (tagDados) {
                dadosEstabsStr = tagDados.value || tagDados.textContent || tagDados.innerText || "[]";
            }

            let listaCnpjsTexto = "";
            let codigoEstabParaValidar = ""; 
            const horaAtual = new Date().getHours();
            const saudacao = horaAtual < 12 ? "Bom dia" : "Boa tarde";

            if (dadosEstabsStr && dadosEstabsStr.trim() !== '[]' && dadosEstabsStr.trim() !== '') {
                try {
                    const jsonLimpo = dadosEstabsStr.replace(/'/g, '"');
                    const ests = JSON.parse(jsonLimpo);
                    
                    if (ests.length > 0) {
                        codigoEstabParaValidar = String(ests[0].estab);
                        listaCnpjsTexto = "\n\nCNPJ(s) para faturamento:\n";
                        ests.forEach(e => {
                            listaCnpjsTexto += `- Estab. ${e.estab}: ${e.cnpj} (${e.empresa})\n`;
                        });
                    }
                } catch(e) {
                    console.error("Erro ao converter JSON: ", e);
                }
            }

            if (!codigoEstabParaValidar) {
                codigoEstabParaValidar = document.getElementById('nomeEmpresaDeposito') ? document.getElementById('nomeEmpresaDeposito').value.trim() : "";
            }

            // TRADUTOR DE CÓDIGO DA EMPRESA
            function obterNomeEmpresaPorEstab(estabStr) {
                if (!estabStr || estabStr === "None") return "Grupo Protege";
                const estab = String(estabStr).trim();

                if (estab.startsWith("550")) return "Protege Cargo Transportadora";
                if (estab.startsWith("830")) return "Portaria do Futuro";
                if (estab.startsWith("2")) return "Protege Proteção e Transporte de Valores";
                if (estab.startsWith("4")) return "Proair Serviços Aux. de Transporte Aereo";
                if (estab.startsWith("5")) return "Provig Form de Profissionais de Segurança";
                if (estab.startsWith("6")) return "Protege Segurança Eletronica";
                if (estab.startsWith("7")) return "Protege Serviços Especiais";

                return "Grupo Protege"; 
            }

            const nomeEmpresaReal = obterNomeEmpresaPorEstab(codigoEstabParaValidar);

            // ================================================================
            // NOVO ASSUNTO COM CLIENTE E RAIZ
            // ================================================================
            const assunto = `Composição de pagamentos - ${nomeEmpresaReal} - ${nomeCliente} - CNPJ Raiz: ${raizCnpj}`;
            
            let corpoEmail = `${saudacao},\n\n`;
            corpoEmail += `Prezado cliente,\n\n`;
            corpoEmail += `Recebemos o crédito de R$ ${valorDep} no dia ${dataDep}, porém não conseguimos compor o pagamento. Pode, por favor, nos enviar a composição?`;
            
            if (listaCnpjsTexto) {
                corpoEmail += listaCnpjsTexto;
            } else {
                corpoEmail += `\n\n(Aguardamos os dados para identificar a filial correta).`;
            }
            
            corpoEmail += `\n\nAtenciosamente,\nDepartamento Financeiro.`;

            const mailtoLink = `mailto:${inputEmailFormatado}?subject=${encodeURIComponent(assunto)}&body=${encodeURIComponent(corpoEmail)}`;
            window.location.href = mailtoLink;
            
            try {
                const modalEl = document.getElementById('modalEmailCliente');
                if (modalEl) {
                    const modalInst = bootstrap.Modal.getInstance(modalEl) || bootstrap.Modal.getOrCreateInstance(modalEl);
                    modalInst.hide();
                }
            } catch(e) { }
        });
    }
    
}); // <-- Fim do ÚNICO DOMContentLoaded