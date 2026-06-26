/* ========================================================
   CONTROLE DOS CHECKBOXES E BOTÃO DE DESFAZER EM LOTE
   ======================================================== */
document.addEventListener('DOMContentLoaded', function() {
    const checkAll = document.getElementById('checkAll');
    const checkItems = document.querySelectorAll('.check-item');
    const btnDesconciliar = document.getElementById('btn-desconciliar');

    // Função que liga/desliga o botão se tiver algo marcado
    function toggleButton() {
        const hasChecked = Array.from(checkItems).some(cb => cb.checked);
        btnDesconciliar.disabled = !hasChecked;
    }

    // Se clicar no checkbox principal (Master), marca/desmarca todos
    if(checkAll) {
        checkAll.addEventListener('change', function() {
            checkItems.forEach(cb => cb.checked = checkAll.checked);
            toggleButton();
        });
    }

    // Se clicar em um checkbox individual, verifica a situação
    checkItems.forEach(cb => {
        cb.addEventListener('change', function() {
            // Se desmarcar um, desmarca o Master
            if (!this.checked && checkAll) checkAll.checked = false;
            
            // Se todos estiverem marcados, marca o Master
            if (Array.from(checkItems).every(item => item.checked) && checkAll) {
                checkAll.checked = true;
            }
            
            toggleButton();
        });
    });
});