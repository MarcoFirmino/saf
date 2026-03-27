import pandas as pd
from django.contrib import admin, messages
from django.shortcuts import render, redirect
from django.urls import path
from import_export import resources, fields, widgets
from datetime import datetime
from import_export.admin import ImportExportModelAdmin
from .forms import ImportarMatrizForm
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
    BaseGeral,
    ResumoInadimplencia,
    DevedorAging,
    
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

class ResumoInadimplenciaResource(resources.ModelResource):
    class Meta:
        model = ResumoInadimplencia
        fields = ('id', 'seguimento', 'data', 'valor', 'tipo_relatorio')
        import_id_fields = [] # Permite criar novos registros sem exigir ID no Excel
        skip_unchanged = True

# 2. Configuração do Admin com o Botão Customizado
@admin.register(ResumoInadimplencia)
class ResumoInadimplenciaAdmin(ImportExportModelAdmin):
    resource_class = ResumoInadimplenciaResource
    list_display = ('data', 'seguimento', 'valor', 'tipo_relatorio')
    list_filter = ('data', 'tipo_relatorio')
    search_fields = ('seguimento',)
    change_list_template = "admin/resumo_change_list.html"

    # Cria a URL para a tela de importação customizada
    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path('importar-matriz/', self.admin_site.admin_view(self.importar_matriz), name='importar_matriz'),
        ]
        return custom_urls + urls

    # A Função que processa o seu Excel de 3 colunas (Seguimento, Data, Valor)
    def importar_matriz(self, request):
        if request.method == "POST":
            form = ImportarMatrizForm(request.POST, request.FILES)
            if form.is_valid():
                arquivo = request.FILES['arquivo_excel']
                tipo = form.cleaned_data['tipo_relatorio']
                
                try:
                    df = pd.read_excel(arquivo)
                    
                    contador = 0
                    for _, row in df.iterrows():
                        # 1. Extração e limpeza básica
                        seg_excel = str(row.iloc[0]).strip() if pd.notna(row.iloc[0]) else None
                        data_raw = row.iloc[1]
                        valor_excel = row.iloc[2]

                        # Pula se os dados essenciais forem nulos
                        if not seg_excel or pd.isna(valor_excel) or pd.isna(data_raw):
                            continue

                        # 2. Tratamento rigoroso da Data
                        data_valida = pd.to_datetime(data_raw, dayfirst=True, errors='coerce')
                        
                        if pd.notna(data_valida):
                            # Tratamos o valor para garantir que seja float (evita NaN do Pandas)
                            valor_final = float(valor_excel) if not pd.isna(valor_excel) else 0.0

                            # 3. O update_or_create com dados higienizados
                            obj, created = ResumoInadimplencia.objects.update_or_create(
                                seguimento=seg_excel,
                                data=data_valida.date(),
                                tipo_relatorio=tipo.strip(), # Garante que o tipo do form está limpo
                                defaults={'valor': valor_final}
                            )
                            contador += 1
                    
                    self.message_user(request, f"Sucesso! {contador} registros importados.", messages.SUCCESS)
                    return redirect("..")
                    
                except Exception as e:
                    self.message_user(request, f"Erro ao processar: {e}", messages.ERROR)
        else:
            form = ImportarMatrizForm()

        payload = {"form": form, "opts": self.model._meta}
        return render(request, "admin/importar_matriz.html", payload)

# 1. Definição do Resource para permitir Import/Export via Excel/CSV
class DevedorAgingResource(resources.ModelResource):
    # Mapeamento manual: column_name deve ser IGUAL ao cabeçalho do CSV
    data_base = fields.Field(column_name='Aging', attribute='data_base')
    ate_30_dias = fields.Field(column_name='até 30 dias', attribute='ate_30_dias')
    de_31_a_60_dias = fields.Field(column_name='31 a 60 dias', attribute='de_31_a_60_dias')
    de_61_a_90_dias = fields.Field(column_name='61 a 90 dias', attribute='de_61_a_90_dias')
    de_91_a_120_dias = fields.Field(column_name='91 a 120 dias', attribute='de_91_a_120_dias')
    de_121_a_150_dias = fields.Field(column_name='121 a 150 dias', attribute='de_121_a_150_dias')
    de_151_a_180_dias = fields.Field(column_name='151 a 180 dias', attribute='de_151_a_180_dias')
    mais_de_180_dias = fields.Field(column_name='mais de 180 dias', attribute='mais_de_180_dias')

    class Meta:
        model = DevedorAging
        import_id_fields = ('data_base',) # Usa a data tratada como chave para não duplicar
        fields = (
            'data_base', 'ate_30_dias', 'de_31_a_60_dias', 'de_61_a_90_dias',
            'de_91_a_120_dias', 'de_121_a_150_dias', 'de_151_a_180_dias', 'mais_de_180_dias'
        )

    def before_import_row(self, row, **kwargs):
        # 1. Tratamento da Data (Limpa o "Base-")
        valor_aging = row.get('Aging')
        if valor_aging and isinstance(valor_aging, str) and 'Base-' in valor_aging:
            data_str = valor_aging.replace('Base-', '').strip()
            try:
                row['Aging'] = datetime.strptime(data_str, '%d/%m/%Y').date()
            except ValueError:
                pass

        # 2. Tratamento de Números (Garante que pontos/vírgulas do CSV não quebrem o float)
        # O pandas costuma ler bem, mas se vier como string "2.849.559,90", o Django se perde.
        campos_financeiros = [
            'até 30 dias', '31 a 60 dias', '61 a 90 dias', '91 a 120 dias',
            '121 a 150 dias', '151 a 180 dias', 'mais de 180 dias'
        ]
        
        for campo in campos_financeiros:
            valor = row.get(campo)
            if isinstance(valor, str):
                # Limpa pontos de milhar e troca vírgula por ponto decimal
                limpo = valor.replace('.', '').replace(',', '.')
                row[campo] = float(limpo)

# 2. Configuração do Admin
@admin.register(DevedorAging)
class DevedorAgingAdmin(ImportExportModelAdmin):
    resource_class = DevedorAgingResource
    
    # Exibição das colunas financeiras lado a lado
    list_display = (
        'data_base', 
        'ate_30_dias', 
        'de_31_a_60_dias', 
        'de_61_a_90_dias', 
        'de_91_a_120_dias', 
        'total' # O total aparece por último como resumo
    )
    
    search_fields = ('data_base',)
    
    # readonly_fields impede que o usuário tente mudar o total manualmente no form,
    # já que o nosso método save() do model é quem manda ali.
    readonly_fields = ('total',)
    
    # Organizando o formulário de edição em seções (Fieldsets) para ficar profissional
    fieldsets = (
        ('Identificação', {
            'fields': ('data_base',)
        }),
        ('Faixas de Atraso (Valores)', {
            'fields': (
                ('ate_30_dias', 'de_31_a_60_dias', 'de_61_a_90_dias'),
                ('de_91_a_120_dias', 'de_121_a_150_dias', 'de_151_a_180_dias'),
                ('mais_de_180_dias',)
            )
        }),
        ('Resumo Financeiro', {
            'fields': ('total',),
            'description': 'O total é calculado automaticamente na gravação.'
        }),
    )