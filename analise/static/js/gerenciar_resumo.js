document.addEventListener('DOMContentLoaded', function() {
    const config = window.AppConfig;

    // ==========================================
    // 1. LÓGICA DE EDIÇÃO RÁPIDA (BLUR)
    // ==========================================
    document.querySelectorAll('.editavel').forEach(cell => {
        cell.addEventListener('blur', function() {
            const originalContent = this.innerText;
            const payload = {
                acao: 'editar',
                id: this.dataset.id,
                campo: this.dataset.campo,
                valor: this.innerText.trim()
            };

            fetch(config.apiAcaoUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken
                },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') {
                    this.style.backgroundColor = '#d1e7dd'; 
                    setTimeout(() => this.style.backgroundColor = '', 800);
                } else {
                    alert('Erro ao salvar: ' + data.message);
                    location.reload(); 
                }
            })
            .catch(err => console.error("Erro na edição:", err));
        });
    });

    // ==========================================
    // 2. LÓGICA DE CRIAÇÃO (MODAL)
    // ==========================================
    const btnSalvarNovo = document.getElementById('btnSalvarNovo');
    if (btnSalvarNovo) {
        btnSalvarNovo.addEventListener('click', function() {
            const payload = {
                acao: 'criar',
                data: document.getElementById('novaData').value,
                seguimento: document.getElementById('novoSeguimento').value,
                valor: document.getElementById('novoValor').value,
                tipo_relatorio: document.getElementById('novoTipo').value
            };

            if(!payload.data || !payload.seguimento || !payload.valor) {
                alert("Por favor, preencha Data, Segmento e Valor.");
                return;
            }

            this.disabled = true;
            this.innerText = "Salvando...";

            fetch(config.apiAcaoUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken
                },
                body: JSON.stringify(payload)
            })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') {
                    location.reload(); 
                } else {
                    alert('Erro ao criar: ' + data.message);
                    this.disabled = false;
                    this.innerText = "Salvar Registro";
                }
            })
            .catch(err => {
                console.error(err);
                alert("Ocorreu um erro na requisição.");
                this.disabled = false;
                this.innerText = "Salvar Registro";
            });
        });
    }

    // ==========================================
    // 3. LÓGICA DE EXCLUSÃO (EVENT DELEGATION)
    // ==========================================
    document.querySelectorAll('.btn-excluir').forEach(btn => {
        btn.addEventListener('click', function() {
            const id = this.dataset.id;
            
            if(!confirm('Deseja excluir este registro permanentemente?')) return;

            // Desabilita o botão temporariamente para evitar duplo clique
            this.disabled = true;

            fetch(config.apiAcaoUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': config.csrfToken
                },
                body: JSON.stringify({ acao: 'excluir', id: id })
            })
            .then(res => res.json())
            .then(data => {
                if(data.status === 'sucesso') {
                    const linha = document.getElementById(`row-${id}`);
                    if (linha) {
                        linha.remove();
                    }
                } else {
                    alert('Erro ao excluir: ' + data.message);
                    this.disabled = false;
                }
            })
            .catch(err => {
                console.error("Erro na exclusão:", err);
                alert("Ocorreu um erro de conexão ao tentar excluir.");
                this.disabled = false;
            });
        });
    });
});