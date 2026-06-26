from django.contrib import admin
from import_export import resources
from import_export.admin import ImportExportModelAdmin
from .models import MapeamentoDePara, ExtratoBancario, ExcecaoConciliacao, EstabelecimentoCNPJ, ClienteEmail, ConciliacaoNota, SugestaoAutomacao
from analise.models import ContasReceber

# =========================================================
# 1. TRADUTOR DA PLANILHA PARA O BANCO (IMPORT/EXPORT)
# =========================================================
class EstabelecimentoCNPJResource(resources.ModelResource):
    class Meta:
        model = EstabelecimentoCNPJ
        import_id_fields = ('estab',) 
        fields = ('estab', 'nome_empresa', 'cnpj')

@admin.register(EstabelecimentoCNPJ)
class EstabelecimentoCNPJAdmin(ImportExportModelAdmin):
    resource_class = EstabelecimentoCNPJResource
    list_display = ('estab', 'nome_empresa', 'cnpj')
    search_fields = ('estab', 'nome_empresa', 'cnpj')

# =========================================================
# 2. TABELAS COMUNS DO SISTEMA
# =========================================================
@admin.register(MapeamentoDePara)
class MapeamentoDeParaAdmin(admin.ModelAdmin):
    list_display = ('descricao_extrato', 'cnpj_cpf', 'nome_cliente', 'atualizado_em')
    search_fields = ('descricao_extrato', 'cnpj_cpf', 'nome_cliente')
    list_filter = ('atualizado_em',)
    ordering = ('-atualizado_em',)

@admin.register(ExtratoBancario)
class ExtratoBancarioAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'banco', 'conta_corrente', 'data_transacao', 'valor','cor_automacao', 'status', 'cnpj_cpf')
    list_filter = ('empresa', 'banco', 'conta_corrente', 'status','cor_automacao', 'data_transacao')
    search_fields = ('descricao', 'documento', 'cnpj_cpf', 'razao_social', 'conta_corrente')
    date_hierarchy = 'data_transacao'
    readonly_fields = ('data_importacao',)

@admin.register(ContasReceber)
class ContasReceberAdmin(admin.ModelAdmin):
    list_display = ('titulo', 'parcela', 'nome_abrev', 'cnpj', 'empresa', 'dt_vencto_atual', 'vl_liquido', 'status')
    search_fields = ('titulo', 'nome_abrev', 'cnpj', 'nosso_numero')
    list_filter = ('status', 'empresa', 'carteira')
    ordering = ('-dt_vencto_atual',)

    

@admin.register(ExcecaoConciliacao)
class ExcecaoConciliacaoAdmin(admin.ModelAdmin):
    list_display = ('termo', 'descricao')
    search_fields = ('termo',)

@admin.register(ClienteEmail)
class ClienteEmailAdmin(admin.ModelAdmin):
    list_display = ('cnpj_busca', 'email')

# DEIXAMOS APENAS UMA ÚNICA VERSÃO DA ConciliacaoNota:
@admin.register(ConciliacaoNota)
class ConciliacaoNotaAdmin(admin.ModelAdmin):
    # Juntei os campos de display da versão 2 com os campos de busca da versão 1
    list_display = ('extrato', 'nota', 'valor_pago', 'impostos_retidos', 'data_conciliacao', 'usuario')
    search_fields = ('extrato__descricao', 'nota__titulo')
    
    # Adicionando o filtro lateral pelo status da nota
    list_filter = ('nota__status', 'extrato__data_importacao', 'extrato__data_transacao')
    search_fields = ('nota__titulo', 'extrato__descricao')

@admin.register(SugestaoAutomacao)
class SugestaoAutomacaoAdmin(admin.ModelAdmin):
    list_display = ('id', 'extrato', 'nota', 'valor_sugerido')
    search_fields = ('extrato__descricao', 'nota__titulo')