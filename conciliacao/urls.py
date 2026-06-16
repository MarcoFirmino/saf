from django.urls import path
from . import views

urlpatterns = [

    path('importar/', views.importar_extrato, name='importar_extrato'),
    path('painel/', views.painel_conciliacao, name='painel_conciliacao'),
    path('exportar-datasul/<int:extrato_id>/', views.exportar_lote_datasul, name='exportar_lote_datasul'),
    path('exportar-lote/', views.exportar_lote_datasul, name='exportar_lote_datasul'),
    path('gestao-conciliados/', views.gestao_conciliados, name='gestao_conciliados'),
    path('notas-baixadas/', views.notas_baixadas, name='notas_baixadas'),
    path('credito/editar/<str:dni>/', views.editar_credito, name='editar_credito'),
    path('credito/cancelar/<str:dni>/', views.cancelar_credito, name='cancelar_credito'),
    path('creditos-nao-destinados/', views.painel_creditos_nao_destinados, name='creditos_nao_destinados'),
    
]