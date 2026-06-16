document.addEventListener('DOMContentLoaded', function() {
    const btnToggleMenu = document.getElementById('btn-toggle-menu');
    const menuLateral = document.getElementById('menu-lateral');
    const areaTabela = document.getElementById('area-tabela');
    const iconeBtn = document.getElementById('icone-btn-menu');
    const textoBtn = document.getElementById('texto-btn-menu');

    if (menuLateral && areaTabela) {
        // Preparamos os dois blocos para transições suaves
        menuLateral.style.transition = 'all 0.35s ease-in-out';
        menuLateral.style.overflow = 'hidden';
        
        areaTabela.style.transition = 'all 0.35s ease-in-out';
    }

    if(btnToggleMenu && menuLateral && areaTabela) {
        let isAberto = true;

        btnToggleMenu.addEventListener('click', function() {
            if (isAberto) {
                // FECHAR: Força a largura exata para zero
                menuLateral.style.width = '0';
                menuLateral.style.flex = '0 0 0%';
                menuLateral.style.padding = '0';
                menuLateral.style.opacity = '0';
                
                // Tabela assume 100% suavemente
                areaTabela.style.width = '100%';
                areaTabela.style.flex = '0 0 100%';
                
                iconeBtn.className = 'bi bi-arrows-collapse';
                textoBtn.innerText = 'Mostrar Menu Lateral';
            } else {
                // ABRIR: Volta exatamente para a proporção do Bootstrap (25% = col-md-3)
                menuLateral.style.width = '25%';
                menuLateral.style.flex = '0 0 25%';
                menuLateral.style.padding = ''; // Restaura o padding
                menuLateral.style.opacity = '1';
                
                // Tabela volta exatamente para 75% (col-md-9)
                areaTabela.style.width = '75%';
                areaTabela.style.flex = '0 0 75%';
                
                iconeBtn.className = 'bi bi-arrows-expand';
                textoBtn.innerText = 'Ocultar Menu Lateral';
            }
            
            isAberto = !isAberto;
        });
    }
});