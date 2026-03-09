// Comportamentos Globais do Sistema
document.addEventListener('DOMContentLoaded', function() {
    console.log("Sistema Protege carregado com sucesso.");
});

// Exemplo de função global para botões de processamento
function showLoading(btnId, spinnerId) {
    const btn = document.getElementById(btnId);
    const spinner = document.getElementById(spinnerId);
    if (btn && spinner) {
        btn.style.display = 'none';
        spinner.style.display = 'inline-block';
    }
}