from django.urls import path
from . import views

urlpatterns = [
    # Rota para a tela de conversão: seu-site.com/tesouraria/converter-prn/
    path('converter-prn/', views.converter_prn_view, name='converter_prn'),
]