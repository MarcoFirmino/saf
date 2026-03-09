import pandas as pd
import xlsxwriter
from io import BytesIO
from django.http import HttpResponse
from .models import BaseGeral, CodigoIgnorado
from .auxiliar import aplicar_regras_banco

# =============================================================================
# FUNÇÃO 1: RELATÓRIO GERAL (Relatório Completo / Staging)
# =============================================================================
def processar_geral_pandas(request, data_corte_str, data_correcao_str):
    """
    Função de Tratamento Completo lendo da Tabela BaseGeral.
    Gera o Excel com 3 abas na ordem EXATA solicitada pela diretoria.
    """
    # 1. CARREGAR DADOS DO BANCO
    qs = BaseGeral.objects.all().values()
    df = pd.DataFrame(list(qs))

    if df.empty:
        raise ValueError("A Base Geral está vazia. Faça a importação no Passo 1 primeiro.")

    # Mapeamento: Variável Lógica -> Nome do Campo no Model
    cols_origem = {
        'especie': 'especie',
        'vencto': 'dt_vencto_original',
        'codigo': 'codigo',
        'empresa': 'empresa',
        'unid_negoc': 'unid_negoc',
        'cnpj_cliente': 'cnpj_cpf_cliente',
        'cnpj_origem': 'cnpj',
        'estabelec': 'estabelecimento',
        'serie': 'serie',
        'titulo': 'titulo',
        'parcela': 'parcela',
        'nome_abrev': 'nome_abrev',
        'dt_emissao': 'dt_emissao_orig',
        'dt_emissao_ren': 'dt_emissao_ult_ren',
        'dt_vencto_atual': 'dt_vencto_atual',
        'vl_bruto': 'vl_bruto_orig',
        'vl_liquido': 'vl_liquido'
    }

    # A. Filtro AN/DNI
    c_esp = cols_origem['especie']
    if c_esp in df.columns:
        df[c_esp] = df[c_esp].astype(str).str.strip()
        df = df[~df[c_esp].isin(['AN', 'DNI'])]

    # B. Datas e Corte
    c_vencto = cols_origem['vencto']
    dt_limite = pd.to_datetime(data_corte_str).normalize()

    # Converter datas cruciais
    for col_data in [c_vencto, cols_origem['dt_emissao'], cols_origem['dt_vencto_atual']]:
        if col_data in df.columns:
            df[col_data] = pd.to_datetime(df[col_data], errors='coerce')

    # Filtro de Data
    df['_data_oculta'] = df[c_vencto]
    df = df.dropna(subset=['_data_oculta'])
    df = df[df['_data_oculta'] <= dt_limite]

    # Ordenação
    df = df.sort_values(by='_data_oculta', ascending=False)

    # E. Lista Negra (Banco)
    c_cod = cols_origem['codigo']
    codigos_db = CodigoIgnorado.objects.values_list('codigo', flat=True)
    lista_negra = [str(c).strip() for c in codigos_db]
    
    if lista_negra and c_cod in df.columns:
        df[c_cod] = df[c_cod].astype(str).str.strip()
        df[c_cod] = df[c_cod].str.replace(r'\.0$', '', regex=True)
        df = df[~df[c_cod].isin(lista_negra)]

    # F. COR/02
    c_emp = cols_origem['empresa']
    c_un = cols_origem['unid_negoc']
    if c_emp in df.columns and c_un in df.columns:
        df[c_emp] = df[c_emp].astype(str).str.strip()
        df[c_un] = df[c_un].astype(str).str.strip()
        condicao_cor = ((df[c_emp] == '02') & (df[c_un].str.upper() == 'COR'))
        df = df[~condicao_cor]

    # G. Filtro FOR / CPF
    c_cli = cols_origem['cnpj_cliente']
    if c_cli in df.columns:
        df[c_cli] = df[c_cli].astype(str).str.strip()
        is_for = df[c_un].str.upper() == 'FOR'
        is_cpf = df[c_cli].str.len() == 14
        df = df[~(is_for & is_cpf)]

    # H. ATI/VEN -> VEN
    mask_ati = df[c_un].str.upper() == 'ATI'
    mask_ven = df[c_un].str.upper() == 'VEN'
    df.loc[mask_ati, c_un] = 'VEN'
    df.loc[mask_ven, c_un] = 'VEN'

    # I. Preencher CNPJ Vazio
    c_origem = cols_origem['cnpj_origem']
    mask_vazio = df[c_cli].isna() | (df[c_cli] == '') | (df[c_cli] == 'nan')
    df.loc[mask_vazio, c_cli] = df.loc[mask_vazio, c_origem]

    # =========================================================
    # MONTAGEM DO DATAFRAME FINAL
    # =========================================================
    df_final = pd.DataFrame()

    # Campos Diretos do Banco
    df_final['Estabelec'] = df[cols_origem['estabelec']]
    df_final['Espécie'] = df[cols_origem['especie']]
    df_final['Série'] = df[cols_origem['serie']]
    df_final['Título'] = df[cols_origem['titulo']]
    
    # Parcela com 2 dígitos (String)
    df_final['Parcela'] = df[cols_origem['parcela']].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(2)
    
    df_final['Unid.Negoc'] = df[cols_origem['unid_negoc']]
    df_final['Empresa'] = df[cols_origem['empresa']]
    
    # ATENÇÃO: Renomeado para 'Codigo' (sem acento) conforme solicitado
    df_final['Codigo'] = df[cols_origem['codigo']] 
    
    df_final['CNPJ/CPF Cliente'] = df[cols_origem['cnpj_cliente']]
    df_final['Nome Abrev'] = df[cols_origem['nome_abrev']]
    df_final['Dt.Emissão Orig'] = df[cols_origem['dt_emissao']]
    df_final['Dt.Emissão Últ.Ren'] = df[cols_origem['dt_emissao_ren']]
    df_final['Dt.Vencto Original'] = df[cols_origem['vencto']]
    df_final['Dt.Vencto Atual'] = df[cols_origem['dt_vencto_atual']]
    df_final['Vl.Bruto Orig.'] = df[cols_origem['vl_bruto']]
    df_final['Vl.líquido'] = df[cols_origem['vl_liquido']]
    
    # Campos Calculados / Vazios Iniciais
    df_final['Regional'] = (
        df_final['Estabelec'].astype(str).str.strip() +
        df_final['Série'].astype(str).str.strip() +
        df_final['Título'].astype(str).str.strip()
    )
    df_final['Base Operacional'] = df_final['Estabelec']
    df_final['Carteira'] = "" # Será preenchido pelo auxiliar
    df_final['Pacote'] = ""
    df_final['Raiz do CNPJ'] = df_final['CNPJ/CPF Cliente'].astype(str).str.split('/').str[0].str.strip()
    df_final['Razão Agrupada'] = ""
    
    # Mapa Unidade de Negócio
    mapa_negocio = {
        'PAX': 'Proair', 'LMO': 'Vigilância', 'PRT': 'Proair', 'GHD': 'Proair',
        'CTV': 'Logística', 'CSG': 'Carga Segura', 'EXE': 'Proair', 'VIG': 'Vigilância',
        'DTV': 'Logística', 'COF': 'Logística', 'MAN': 'Segel', 'NUM': 'Logística',
        'LOC': 'Segel', 'MON': 'Segel', 'CCV': 'Logística de Carga', 'FOR': 'Provig', 'VEN': 'Segel'
    }
    df_final['Negócio'] = df_final['Unid.Negoc'].str.strip().str.upper().map(mapa_negocio).fillna('')

    # Tratamento Empresa
    df_final['Empresa'] = df_final['Empresa'].astype(str).str.strip().str.zfill(2)
    mapa_empresa = {
        '02': 'PROTEGE', '04': 'PROAIR', '05': 'PROVIG',
        '07': 'SERVIÇOS', '50': 'PROTEGE CARGO', '80': 'PORTARIA DO FUTURO'
    }
    df_final['Empresa'] = df_final['Empresa'].replace(mapa_empresa)

    # Tratamento de Datas
    cols_datas_excel = ['Dt.Emissão Orig', 'Dt.Emissão Últ.Ren', 'Dt.Vencto Original', 'Dt.Vencto Atual']
    for col in cols_datas_excel:
        df_final[col] = pd.to_datetime(df_final[col], errors='coerce')
        if pd.api.types.is_datetime64_any_dtype(df_final[col]):
             df_final[col] = df_final[col].dt.tz_localize(None)

    # Tratamento de Valores
    cols_valores = ['Vl.Bruto Orig.', 'Vl.líquido']
    for col in cols_valores:
        df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)

    # Regras e Cálculos Iniciais (Dias em Atraso)
    dt_correcao = pd.to_datetime(data_correcao_str).normalize()
    df_final['Dias em Atraso'] = (dt_correcao - df_final['Dt.Vencto Original']).dt.days.fillna(0).astype(int)
    df_final['Dias em Atraso RE'] = (dt_correcao - df_final['Dt.Vencto Atual']).dt.days.fillna(0).astype(int)

    # Aging
    def classificar_aging(dias):
        if dias <= 0: return "A VENCER"
        if dias <= 30: return "Até 30 dias"
        if dias <= 60: return "31 a 60 dias"
        if dias <= 90: return "61 a 90 dias"
        if dias <= 120: return "91 a 120 dias"
        if dias <= 150: return "121 a 150 dias"
        if dias <= 180: return "151 a 180 dias"
        return "Mais de 180 dias"

    df_final['Aging'] = df_final['Dias em Atraso'].apply(classificar_aging)
    df_final['Aging RE'] = df_final['Dias em Atraso RE'].apply(classificar_aging)

    # Status
    def classificar_status(row):
        dias_orig = row['Dias em Atraso']
        dias_re = row['Dias em Atraso RE']
        if dias_re <= 0: return "RENEGOCIAÇÕES A VENCER"
        elif dias_re < dias_orig: return "QUEBRA DE ACORDO / NÃO PAGAS"
        else: return "INADIMPLÊNCIA"

    df_final['Status'] = df_final.apply(classificar_status, axis=1)

    # Aplicação de Regras do Banco Auxiliar (Preenche Carteira, Razão Agrupada, etc)
    try:
        df_final = aplicar_regras_banco(df_final)
    except Exception as e:
        print(f"Aviso: Não foi possível aplicar regras do auxiliar: {e}")

    # =========================================================
    # REORDENAÇÃO FINAL (ESSENCIAL PARA O COPY-PASTE)
    # =========================================================
    colunas_ordenadas = [
        'Regional', 'Base Operacional', 'Estabelec', 'Espécie', 'Série', 'Título', 'Parcela', 
        'Unid.Negoc', 'Negócio', 'Empresa', 'Carteira', 'Codigo', 'Pacote', 
        'Raiz do CNPJ', 'CNPJ/CPF Cliente', 'Razão Agrupada', 'Nome Abrev', 
        'Dt.Emissão Orig', 'Dt.Emissão Últ.Ren', 'Dt.Vencto Original', 'Dt.Vencto Atual', 
        'Vl.Bruto Orig.', 'Vl.líquido', 'Dias em Atraso', 'Dias em Atraso RE', 
        'Aging', 'Aging RE', 'Status'
    ]
    
    # Garante que o DataFrame tenha apenas essas colunas e nessa ordem
    # Se alguma coluna faltar, o Pandas avisará, mas criamos todas acima.
    df_final = df_final[colunas_ordenadas]

    # =========================================================
    # SEPARAÇÃO EM 3 ABAS
    # =========================================================
    mask_juridico = df_final['Carteira'].astype(str).str.strip() == 'Recuperação Judicial'
    
    # Aba 1: Jurídico
    df_juridico = df_final[mask_juridico]

    # Quem não é jurídico
    df_nao_juridico = df_final[~mask_juridico]

    # Aba 2: Renegociados
    filtros_reneg = ['RENEGOCIAÇÕES A VENCER', 'QUEBRA DE ACORDO / NÃO PAGAS']
    df_renegociados = df_nao_juridico[df_nao_juridico['Status'].isin(filtros_reneg)]

    # Aba 3: Todos os Clientes (Inadimplência + Quebra)
    filtros_todos = ['INADIMPLÊNCIA', 'QUEBRA DE ACORDO / NÃO PAGAS']
    df_todos_clientes = df_nao_juridico[df_nao_juridico['Status'].isin(filtros_todos)]

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    nome_arquivo = f"Relatorio_Tratado_{data_corte_str.replace('/', '-')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'

    with pd.ExcelWriter(response, engine='xlsxwriter', datetime_format='dd/mm/yyyy') as writer:
        workbook = writer.book
        fmt_moeda = workbook.add_format({'num_format': '#,##0.00'})
        fmt_data = workbook.add_format({'num_format': 'dd/mm/yyyy'})
        fmt_texto = workbook.add_format({'num_format': '@'}) 

        def salvar_e_formatar(dataframe, nome_aba):
            dataframe.to_excel(writer, index=False, sheet_name=nome_aba)
            worksheet = writer.sheets[nome_aba]
            
            # Largura padrão para visualização
            worksheet.set_column('A:AB', 15)
            
            if not dataframe.empty:
                colunas = dataframe.columns.tolist()
                
                # Formata Datas
                for col_name in ['Dt.Emissão Orig', 'Dt.Emissão Últ.Ren', 'Dt.Vencto Original', 'Dt.Vencto Atual']:
                    if col_name in colunas:
                        idx = colunas.index(col_name)
                        worksheet.set_column(idx, idx, 15, fmt_data)
                
                # Formata Valores
                for col_name in ['Vl.Bruto Orig.', 'Vl.líquido']:
                    if col_name in colunas:
                        idx = colunas.index(col_name)
                        worksheet.set_column(idx, idx, 15, fmt_moeda)

                # Formata Parcela como Texto (Para manter o 01)
                if 'Parcela' in colunas:
                    idx = colunas.index('Parcela')
                    worksheet.set_column(idx, idx, 10, fmt_texto)

        salvar_e_formatar(df_juridico, 'Jurídico')
        salvar_e_formatar(df_renegociados, 'Renegociados')
        salvar_e_formatar(df_todos_clientes, 'Todos os Clientes')

    return response

# =============================================================================
# FUNÇÃO 2: RELATÓRIO CONTAS A RECEBER (Tabela Dinâmica do Excel)
# =============================================================================
def gerar_excel_contas_receber():
    """
    Gera o Relatório de Contas a Receber completo.
    Regras Aplicadas:
    - Abatimento: Pega do campo 'liquidacao'.
    - Vl.Bruto: Pega do campo 'vl_bruto_reneg'.
    - Parcela: String com 2 dígitos (01, 02...).
    - Empresa: String com 2 dígitos (02, 05...).
    - Segmento: Direto do banco (sem tradução).
    """
    
    # 1. Buscar TODOS os dados
    qs = BaseGeral.objects.all().values()
    df = pd.DataFrame(list(qs))
    
    if df.empty:
        return None

    # === FILTRO DE ESPÉCIE (AN / DNI) ===
    if 'especie' in df.columns:
        df['especie'] = df['especie'].astype(str).str.strip().str.upper()
        df = df[~df['especie'].isin(['AN', 'DNI'])]

    # 2. Tratamento de Tipos
    cols_data = ['dt_emissao_orig', 'dt_vencto_atual']
    for col in cols_data:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    # Lista de valores numéricos para converter
    # Inclui 'liquidacao' e 'vl_bruto_reneg' para garantir precisão
    cols_valor = [
        'vl_bruto_reneg', 'vl_bruto_orig', 
        'pis', 'cofins', 'csll', 'irrf', 'iss', 'inss',
        'desconto', 'acerto', 'multa', 'juros', 'vl_liquido',
        'liquidacao'
    ]
    for col in cols_valor:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].astype(float).fillna(0.0)

    # 3. Tratamento de Strings e Zeros à esquerda
    # Parcela (1 -> 01)
    if 'parcela' in df.columns:
        df['parcela'] = df['parcela'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(2)

    # Empresa (2 -> 02)
    if 'empresa' in df.columns:
        df['empresa'] = df['empresa'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(2)

    # 4. PREPARAR O EXCEL
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Contas a Receber')

    # === CONGELAR CABEÇALHO ===
    worksheet.freeze_panes(1, 0)

    # === ESTILOS ===
    fmt_data = workbook.add_format({'num_format': 'dd/mm/yyyy'})
    fmt_moeda = workbook.add_format({'num_format': '#,##0.00'}) 
    fmt_texto = workbook.add_format({'num_format': '@'}) 

    fmt_input_moeda = workbook.add_format({'num_format': '#,##0.00'}) 
    fmt_input_data = workbook.add_format({'num_format': 'dd/mm/yyyy'})
    fmt_input_txt = workbook.add_format({}) 

    fmt_formula = workbook.add_format({'num_format': '#,##0.00'})
    fmt_formula_pct = workbook.add_format({'num_format': '0.00%'})

    # 5. DEFINIÇÃO DAS COLUNAS
    # Tupla: (Nome no Excel, Nome no DF/Banco, Formato)
    colunas_config = [
        ('Estabelec', 'estabelecimento', None),
        ('Espécie', 'especie', None),
        ('Série', 'serie', None),
        ('Título', 'titulo', None),
        ('Parcela', 'parcela', fmt_texto),
        ('Dt.Emissão Orig', 'dt_emissao_orig', fmt_data),
        ('Dt.Vencto Atual', 'dt_vencto_atual', fmt_data),
        ('Empresa', 'empresa', fmt_texto),
        ('CNPJ', 'cnpj', None),
        ('Nome Abrev', 'nome_abrev', None),
        
        # Apontando para 'vl_bruto_reneg'
        ('Vl.Bruto', 'vl_bruto_reneg', fmt_moeda),
        
        ('PIS', 'pis', fmt_moeda),
        ('Cofins', 'cofins', fmt_moeda),
        ('CSLL', 'csll', fmt_moeda),
        ('IRRF', 'irrf', fmt_moeda),
        ('ISS', 'iss', fmt_moeda),
        ('INSS', 'inss', fmt_moeda),
        ('Desconto', 'desconto', fmt_moeda),
        
        # Apontando para 'liquidacao'
        ('Abatimento', 'liquidacao', fmt_moeda),
        
        ('Multa', 'multa', fmt_moeda),
        ('Juros', 'juros', fmt_moeda),
        
        # Fórmula Vl.líquido (Calculado)
        ('Vl.líquido', None, fmt_formula), 
        
        ('Carteira', 'carteira', None),

        # Inputs e Fórmulas
        ('Vlr. Pago', None, fmt_input_moeda),       
        ('Variação', None, fmt_formula_pct),        
        ('Diferença', None, fmt_formula),           
        ('Dt. Pagamento', None, fmt_input_data),    
        ('Dt. Reversão', None, fmt_input_data),     
        ('Banco', None, fmt_input_txt),             
        
        ('Segmento', 'unid_negoc', None),
        
        ('Nosso Número', 'nosso_numero', None),
        ('Portador', 'portador', None),
        ('Codigo', 'codigo', None),
    ]

    # 6. CONFIGURAR COLUNAS E FÓRMULAS
    headers = [c[0] for c in colunas_config]
    
    table_columns = []
    for titulo, campo, formato in colunas_config:
        col_def = {'header': titulo}
        if formato:
            col_def['format'] = formato
            
        # --- FÓRMULAS ---
        if titulo == 'Variação':
            col_def['formula'] = '=IFERROR(([@[Vlr. Pago]]/[@[Vl.Bruto]])-1, 0)'
        elif titulo == 'Diferença':
            col_def['formula'] = '=[@[Vl.líquido]]-[@[Vlr. Pago]]'
        elif titulo == 'Vl.líquido':
            # Fórmula: Bruto - (Impostos+Descontos+Abatimento) + (Multa+Juros)
            col_def['formula'] = (
                '=[@[Vl.Bruto]]-'
                'SUM([@[PIS]],[@[Cofins]],[@[CSLL]],[@[IRRF]],[@[ISS]],[@[INSS]],[@[Desconto]],[@[Abatimento]])+'
                'SUM([@[Multa]],[@[Juros]])'
            )
            
        table_columns.append(col_def)

    # 7. ESCREVER DADOS
    rows = df.to_dict('records')
    for i, row in enumerate(rows):
        for j, (titulo, campo, formato) in enumerate(colunas_config):
            if campo:
                valor = row.get(campo)
                if valor is None: valor = ''
                worksheet.write(i + 1, j, valor, formato)
            else:
                worksheet.write(i + 1, j, None, formato)

    # 8. CRIAR A TABELA
    last_row = len(rows)
    last_col = len(headers) - 1
    
    worksheet.add_table(0, 0, last_row, last_col, {
        'name': 'TbContasReceber',
        'columns': table_columns,
        'style': 'TableStyleMedium2', 
        'total_row': False 
    })

    # Larguras
    worksheet.set_column('A:E', 10)
    worksheet.set_column('F:G', 12)
    worksheet.set_column('H:J', 25)
    worksheet.set_column('K:W', 15)
    
    workbook.close()
    output.seek(0)
    return output