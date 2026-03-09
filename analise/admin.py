from django.contrib import admin
from import_export import resources, fields, widgets
from import_export.admin import ImportExportModelAdmin
from .models import (
    CodigoIgnorado, 
    EmpresasCorporativas, 
    NegocioCorporativo, 
    ResponsavelEmpresa, 
    ResponsavelNegocio,
    JurCargaSegura,
    Paycash,
    Bd_Clientes,
    Consolidado_Juridico,
    BaseGeral
)
@admin.register(CodigoIgnorado)
class CodigoIgnoradoAdmin(ImportExportModelAdmin):
    list_display = ('codigo',)
    search_fields = ('codigo',)

# --- NOVO REGISTRO ---
@admin.register(EmpresasCorporativas)
class EmpresasCorporativasAdmin(admin.ModelAdmin):
    list_display = ('nome',)      # Mostra o nome na lista
    search_fields = ('nome',)     # Cria barra de pesquisa por nome

@admin.register(NegocioCorporativo)
class NegocioCorporativoAdmin(admin.ModelAdmin):
    list_display = ('nome',)
    search_fields = ('nome',)

@admin.register(ResponsavelEmpresa)
class ResponsavelEmpresaAdmin(admin.ModelAdmin):
    list_display = ('empresa', 'carteira') # Mostra as duas colunas na lista
    search_fields = ('empresa', 'carteira') # Permite pesquisar por ambas

@admin.register(ResponsavelNegocio)
class ResponsavelNegocioAdmin(admin.ModelAdmin):
    list_display = ('negocio', 'carteira')
    search_fields = ('negocio', 'carteira')

@admin.register(JurCargaSegura)
class JurCargaSeguraAdmin(ImportExportModelAdmin):
    # Vamos mostrar várias colunas na lista para facilitar a visualização
    list_display = ('razao', 'raiz', 'negocio', 'executivo', 'status')
    
    # Barra de pesquisa para encontrar por Razão, Raiz ou Chave
    search_fields = ('razao', 'raiz', 'chave')
    
    # Filtros laterais úteis
    list_filter = ('status', 'negocio', 'perfil')

# --- Configuração Especial para Ler Data Brasileira ---
class PaycashResource(resources.ModelResource):
    # Aqui redefinimos o campo de data para ensinar o formato
    dt_emissao_fatura = fields.Field(
        column_name='dt_emissao_fatura', # Nome da coluna no cabeçalho do CSV
        attribute='dt_emissao_fatura',   # Nome da coluna no Banco de Dados
        widget=widgets.DateWidget(format='%d/%m/%Y') # <--- O SEGREDO: Formato Dia/Mês/Ano
    )

    class Meta:
        model = Paycash
        import_id_fields = ('id',) # Usa o ID interno como identificador
        # Se quiser excluir colunas na importação, use exclude = ('id',)

# --- O Admin usando a Receita acima ---
@admin.register(Paycash)
class PaycashAdmin(ImportExportModelAdmin):
    resource_class = PaycashResource # <--- Avisamos para usar a nossa receita
    list_display = ('chave','nome', 'nro_fatura', 'dt_emissao_fatura', 'uf')
    search_fields = ('nome', 'chave', 'nro_fatura')
    list_filter = ('uf','nro_fatura')
    
@admin.register(Bd_Clientes)
class BdClientesAdmin(ImportExportModelAdmin):
    # Mostra colunas principais na lista
    list_display = ('cnpj_raiz', 'razao_social', 'perfil_responsavel_financeiro', 'perfil_grupo_ponto', 'perfil_fatura')
    
    # Permite pesquisar por CNPJ ou Nome
    search_fields = ('cnpj_raiz', 'razao_social', 'perfil_responsavel_financeiro', 'perfil_fatura')
    
    # Filtro lateral por Status e Perfil de Negócio
    list_filter = ('perfil_responsavel_financeiro','perfil_negocio','cnpj_raiz')

@admin.register(Consolidado_Juridico)
class ConsolidadoJuridicoAdmin(ImportExportModelAdmin):
    # Colunas principais para leitura rápida
    list_display = ('chave', 'titulo', 'nome_abrev', 'dt_vencto_original', 'vl_liquido')
    
    # Pesquisa por Chave, Nome ou CNPJ
    search_fields = ('chave', 'nome_abrev', 'cnpj_cpf_cliente', 'titulo')
    
    # Filtros laterais
    list_filter = ('estabelec', 'classificacao', 'dt_vencto_original')

@admin.register(BaseGeral)
class BaseGeralAdmin(admin.ModelAdmin):
    # Mostra essas colunas na lista
    list_display = ('titulo', 'estabelecimento', 'nome_abrev', 'dt_vencto_original', 'vl_bruto_orig', 'vl_liquido', 'data_importacao')
    # Permite pesquisar por esses campos
    search_fields = ('titulo', 'nome_abrev', 'cnpj')
    # Filtros laterais
    list_filter = ('data_importacao', 'empresa')