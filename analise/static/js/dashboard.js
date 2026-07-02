/* ========================================================
   LÓGICA DE OCULTAR O MENU DO DASHBOARD
   ======================================================== */
document.addEventListener('DOMContentLoaded', function() {
    const btnToggleMenu = document.getElementById('btn-toggle-menu-dash');
    const iconeBtn = document.getElementById('icone-btn-menu-dash');
    const textoBtn = document.getElementById('texto-btn-menu-dash');
    
    const content = document.getElementById('content');
    
    // A MÁGICA AQUI: Busca diretamente pelo ID que está dentro do sidebar.html
    // O JS vai procurar primeiro por 'menu-lateral' e, se não achar, procura por 'sidebar'
    const sidebar = document.getElementById('menu-lateral') || document.getElementById('sidebar'); 

    if (btnToggleMenu && sidebar && content) {
        
        // Garante que o menu pode ser comprimido sem vazar o conteúdo
        sidebar.style.transition = 'all 0.35s ease-in-out';
        sidebar.style.overflow = 'hidden';
        content.style.transition = 'all 0.35s ease-in-out';

        let isAberto = true;

        btnToggleMenu.addEventListener('click', function() {
            if (isAberto) {
                // FECHAR: Salva a largura atual antes de zerar
                sidebar.dataset.originalWidth = window.getComputedStyle(sidebar).width || '250px';
                sidebar.style.width = '0px';
                sidebar.style.minWidth = '0px';
                sidebar.style.opacity = '0';
                sidebar.style.padding = '0';
                sidebar.style.margin = '0';
                
                // Remove qualquer flexbox que impeça o menu de encolher
                sidebar.style.flex = 'none'; 
                
                iconeBtn.className = 'bi bi-arrows-collapse';
                textoBtn.innerText = 'Mostrar Menu';
            } else {
                // ABRIR: Restaura as propriedades
                sidebar.style.width = sidebar.dataset.originalWidth;
                sidebar.style.minWidth = '';
                sidebar.style.opacity = '1';
                sidebar.style.padding = '';
                sidebar.style.margin = '';
                
                // Devolve a propriedade flex original caso exista
                sidebar.style.flex = ''; 
                
                iconeBtn.className = 'bi bi-arrows-expand';
                textoBtn.innerText = 'Ocultar Menu';
            }
            isAberto = !isAberto; // Inverte o status
        });
    } else {
        console.warn("Aviso: Botão, Content ou a div do Sidebar (IDs 'menu-lateral' ou 'sidebar') não foram encontrados na tela.");
    }
});