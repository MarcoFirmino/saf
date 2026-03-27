from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views

# MUDANÇA IMPORTANTE: Importamos o módulo inteiro 'views'
# Isso evita o erro de "name 'views' is not defined" e facilita o uso
from analise import views

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # =========================================================
    # NAVEGAÇÃO
    # =========================================================
    path('', views.index, name='index'),
    
    path('suspensos/', views.suspensos_view, name='suspensos'),
    path('suspensos/editar/<int:id>/', views.editar_suspenso, name='editar_suspenso'), 
    path('contas-receber/', views.relatorio_ar_view, name='relatorio_ar'),

    # =========================================================
    # NOVA LÓGICA: IMPORTAÇÃO E RELATÓRIO (STAGING)
    # =========================================================
    
    # Passo 1: Importar Excel para o Banco (Staging)
    # Substitui a rota antiga 'importar/geral/'
    path('importar-geral/', views.importar_geral_staging, name='importar_geral'),

    # Passo 2: Processar e Baixar Relatório (Com Datas)
    # Substitui a rota antiga 'gerar-relatorio/'
    path('processar-relatorio/', views.processar_relatorio, name='processar_relatorio'),

    # =========================================================
    # TABELAS AUXILIARES
    # =========================================================
    path('importar/paycash/', views.importar_paycash_view, name='importar_paycash'),
    path('importar/jur-carga/', views.importar_jur_carga_view, name='importar_jur_carga'),
    path('importar/consolidado/', views.importar_consolidado_view, name='importar_consolidado'),
    path('importar/bd-clientes/', views.importar_bd_clientes_view, name='importar_bd_clientes'),
    path('aging/', views.aging_view, name='dashboard_aging'),

    # =========================================================
    # LIMPEZA DE DADOS
    # =========================================================
    path('limpar/bd-clientes/', views.limpar_bd_clientes, name='limpar_bd_clientes'),
    path('limpar/consolidado/', views.limpar_consolidado, name='limpar_consolidado'),
    path('limpar/paycash/', views.limpar_paycash, name='limpar_paycash'),

    # =========================================================
    # AUTENTICAÇÃO E SENHAS
    # =========================================================
    
    # 1. Login e Logout
    path('login/', auth_views.LoginView.as_view(template_name='analise/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # 2. Alteração de Senha (Fluxo de Primeiro Acesso)
    path('alterar-senha/', 
         auth_views.PasswordChangeView.as_view(
             template_name='analise/password_change.html',
             success_url='/alterar-senha/sucesso/'
         ), 
         name='password_change'),
         
    path('alterar-senha/sucesso/', views.password_change_done_custom, name='password_change_done'),

    # 3. Recuperação de Senha (Esqueci a Senha)
    path('recuperar-senha/', 
         auth_views.PasswordResetView.as_view(template_name='analise/password_reset.html'), 
         name='password_reset'),
         
    path('recuperar-senha/enviado/', 
         auth_views.PasswordResetDoneView.as_view(template_name='analise/password_reset_done.html'), 
         name='password_reset_done'),
         
    path('reset/<uidb64>/<token>/', 
         auth_views.PasswordResetConfirmView.as_view(template_name='analise/password_reset_confirm.html'), 
         name='password_reset_confirm'),
         
    path('reset/concluido/', 
         auth_views.PasswordResetCompleteView.as_view(template_name='analise/password_reset_complete.html'), 
         name='password_reset_complete'),

    # ADICIONE ESTA LINHA:
    path('tesouraria/', include('tesouraria.urls')),
    path('dashboard/', views.dashboard_resumo, name='dashboard_resumo'),
    path('renegociados/', views.renegociacoes_view, name='renegociados'),
]