/* ========================================================
   MODAL DE REVISÃO DOS DEPÓSITOS VERDES (LOTE GLOBAL)
   ======================================================== */
function abrirModalRevisaoVerdes() {
    var modalElement = document.getElementById('modalRevisaoVerdes');
    if (!modalElement) return;
    
    var modal = new bootstrap.Modal(modalElement);
    modal.show();
    
    document.getElementById('loading-revisao').classList.remove('d-none');
    document.getElementById('conteudo-revisao').classList.add('d-none');
    document.getElementById('btn-confirmar-verdes').disabled = true;
    document.getElementById('alerta-divergencia').classList.add('d-none');

    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').value;

    fetch(window.location.pathname, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-Requested-With': 'XMLHttpRequest',
            'X-CSRFToken': csrfToken
        },
        body: JSON.stringify({ 'acao': 'resumo_verdes_cnpj' }) // Não manda mais ID nem CNPJ!
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById('loading-revisao').classList.add('d-none');
        document.getElementById('conteudo-revisao').classList.remove('d-none');
        
        if(data.status === 'sucesso') {
            document.getElementById('rev-qtd').textContent = data.qtd_depositos;
            document.getElementById('rev-soma-dep').textContent = 'R$ ' + parseFloat(data.total_depositos).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            document.getElementById('rev-soma-notas').textContent = 'R$ ' + parseFloat(data.total_notas).toLocaleString('pt-BR', {minimumFractionDigits: 2, maximumFractionDigits: 2});
            
            if (Math.abs(data.total_depositos - data.total_notas) <= 0.05) {
                document.getElementById('btn-confirmar-verdes').disabled = false; 
            } else {
                document.getElementById('alerta-divergencia').classList.remove('d-none'); 
            }
        } else {
            alert('Atenção: ' + data.message);
            modal.hide();
        }
    })
    .catch(error => {
        console.error('Erro:', error);
        alert('Erro de conexão ao calcular os totais.');
        modal.hide();
    });
}

function forçarEfetivacaoLote() {
    document.getElementById('btn-confirmar-verdes').disabled = true;
    document.getElementById('btn-confirmar-verdes').innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processando...';

    var form = document.createElement('form');
    form.method = 'POST';
    form.action = window.location.search; // Mantém os filtros da URL
    
    var inputAcao = document.createElement('input');
    inputAcao.type = 'hidden';
    inputAcao.name = 'acao';
    inputAcao.value = 'efetivar_verdes_cnpj';
    form.appendChild(inputAcao);
    
    var csrfToken = document.querySelector('[name=csrfmiddlewaretoken]').cloneNode();
    form.appendChild(csrfToken);
    
    document.body.appendChild(form);
    form.submit();
}
/* ========================================================
   FUNÇÃO PARA FORÇAR O ENVIO CORRETO AO CLICAR EM CONFIRMAR
   ======================================================== */
function forcarEfetivacaoLote() {
    // 1. Muda o visual do botão
    var btn = document.getElementById('btn-confirmar-verdes');
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Processando...';
    }

    // 2. Cria o formulário de envio
    var form = document.createElement('form');
    form.method = 'POST';
    form.action = window.location.search; // Mantém os filtros que estiverem na URL
    
    var inputAcao = document.createElement('input');
    inputAcao.type = 'hidden';
    inputAcao.name = 'acao';
    inputAcao.value = 'efetivar_verdes_cnpj';
    form.appendChild(inputAcao);
    
    // 3. Captura o Token de Segurança do Django
    var csrfTokenOriginal = document.querySelector('[name=csrfmiddlewaretoken]');
    if (csrfTokenOriginal) {
        form.appendChild(csrfTokenOriginal.cloneNode(true));
    } else {
        alert('Erro: Token de segurança (CSRF) não encontrado na página.');
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = '<i class="bi bi-check-circle"></i> Confirmar Baixa em Lote';
        }
        return;
    }
    
    // 4. Envia para o Python
    document.body.appendChild(form);
    form.submit();
}