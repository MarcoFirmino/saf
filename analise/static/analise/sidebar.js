document.addEventListener("DOMContentLoaded", function() {
    const sidebar = document.getElementById('sidebar');
    const sidebarCollapse = document.getElementById('sidebarCollapse');
    const toggleIcon = document.getElementById('toggleIcon');

    if (sidebarCollapse && sidebar) {
        sidebarCollapse.addEventListener('click', function() {
            // Esconde/Mostra o menu lateral
            sidebar.classList.toggle('active');
            
            // Move o botão flutuante para o canto da tela
            sidebarCollapse.classList.toggle('collapsed');
            
            // Troca o ícone dinamicamente
            if (sidebar.classList.contains('active')) {
                toggleIcon.classList.remove('bi-chevron-double-left');
                toggleIcon.classList.add('bi-chevron-double-right'); // Fica >>
            } else {
                toggleIcon.classList.remove('bi-chevron-double-right');
                toggleIcon.classList.add('bi-chevron-double-left');  // Fica <<
            }
        });
    }
});