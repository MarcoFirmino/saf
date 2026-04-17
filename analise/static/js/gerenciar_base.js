// static/js/gerenciar_base.js

document.addEventListener('DOMContentLoaded', function() {
    
    // Função para pegar o token CSRF dos cookies (padrão Django)
    function getCookie(name) {
        let cookieValue = null;
        if (document.cookie && document.cookie !== '') {
            const cookies = document.cookie.split(';');
            for (let i = 0; i < cookies.length; i++) {
                const cookie = cookies[i].trim();
                if (cookie.substring(0, name.length + 1) === (name + '=')) {
                    cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                    break;
                }
            }
        }
        return cookieValue;
    }

    const csrfToken = getCookie('csrftoken') || window.AppConfig.csrfToken;
    const apiUrl = window.AppConfig.apiAcaoUrl;

    // Evento para salvar ao sair do campo (blur)
    document.querySelectorAll('.editavel').forEach(el => {
        el.addEventListener('blur', function() {
            const id = this.dataset.id;
            const campo = this.dataset.campo;
            const valor = this.innerText.trim();

            fetch(apiUrl, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRFToken': csrfToken
                },
                body: JSON.stringify({ acao: 'editar', id: id, campo: campo, valor: valor })
            })
            .then(response => response.json())
            .then(data => {
                if(data.status === 'sucesso') {
                    this.classList.add('table-success');
                    setTimeout(() => this.classList.remove('table-success'), 1000);
                } else {
                    alert('Erro ao salvar: ' + data.message);
                }
            })
            .catch(error => console.error('Erro na requisição:', error));
        });
    });

    // Expondo a função de excluir para o escopo global (já que ela é chamada via onclick no HTML)
    window.excluirRegistro = function(id) {
        if(!confirm('Deseja realmente excluir este registro?')) return;

        fetch(apiUrl, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': csrfToken
            },
            body: JSON.stringify({ acao: 'excluir', id: id })
        })
        .then(response => response.json())
        .then(data => {
            if(data.status === 'sucesso') {
                const linha = document.getElementById(`row-${id}`);
                if (linha) linha.remove();
            } else {
                alert('Erro ao excluir: ' + data.message);
            }
        })
        .catch(error => console.error('Erro na requisição:', error));
    };
});