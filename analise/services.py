import pandas as pd
import xlsxwriter
from io import BytesIO
from django.http import HttpResponse
from .models import BaseGeral, CodigoIgnorado, Excecao, ContasReceber
from .auxiliar import aplicar_regras_banco
from .etl_relatorios import popular_banco_relatorio
from decimal import Decimal, InvalidOperation


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

    cols_origem = {
        'especie': 'especie', 'vencto': 'dt_vencto_original', 'codigo': 'codigo',
        'empresa': 'empresa', 'unid_negoc': 'unid_negoc', 'cnpj_cliente': 'cnpj_cpf_cliente',
        'cnpj_origem': 'cnpj', 'estabelec': 'estabelecimento', 'serie': 'serie',
        'titulo': 'titulo', 'parcela': 'parcela', 'nome_abrev': 'nome_abrev',
        'dt_emissao': 'dt_emissao_orig', 'dt_emissao_ren': 'dt_emissao_ult_ren',
        'dt_vencto_atual': 'dt_vencto_atual', 'vl_bruto': 'vl_bruto_orig',
        'vl_liquido': 'vl_liquido'
    }

    c_esp = cols_origem['especie']
    if c_esp in df.columns:
        df[c_esp] = df[c_esp].astype(str).str.strip()
        df = df[~df[c_esp].isin(['AN', 'DNI'])]

    c_vencto = cols_origem['vencto']
    dt_limite = pd.to_datetime(data_corte_str).normalize()

    for col_data in [c_vencto, cols_origem['dt_emissao'], cols_origem['dt_vencto_atual']]:
        if col_data in df.columns:
            df[col_data] = pd.to_datetime(df[col_data], errors='coerce')

    df['_data_oculta'] = df[c_vencto]
    df = df.dropna(subset=['_data_oculta'])
    df = df[df['_data_oculta'] <= dt_limite]
    df = df.sort_values(by='_data_oculta', ascending=False)

    c_cod = cols_origem['codigo']
    codigos_db = CodigoIgnorado.objects.values_list('codigo', flat=True)
    lista_negra = [str(c).strip() for c in codigos_db]
    
    if lista_negra and c_cod in df.columns:
        df[c_cod] = df[c_cod].astype(str).str.strip()
        df[c_cod] = df[c_cod].str.replace(r'\.0$', '', regex=True)
        df = df[~df[c_cod].isin(lista_negra)]

    c_emp = cols_origem['empresa']
    c_un = cols_origem['unid_negoc']
    if c_emp in df.columns and c_un in df.columns:
        df[c_emp] = df[c_emp].astype(str).str.strip()
        df[c_un] = df[c_un].astype(str).str.strip()
        condicao_cor = ((df[c_emp] == '02') & (df[c_un].str.upper() == 'COR'))
        df = df[~condicao_cor]

    c_cli = cols_origem['cnpj_cliente']
    if c_cli in df.columns:
        df[c_cli] = df[c_cli].astype(str).str.strip()
        is_for = df[c_un].str.upper() == 'FOR'
        is_cpf = df[c_cli].str.len() == 14
        df = df[~(is_for & is_cpf)]

    mask_ati = df[c_un].str.upper() == 'ATI'
    mask_ven = df[c_un].str.upper() == 'VEN'
    df.loc[mask_ati, c_un] = 'VEN'
    df.loc[mask_ven, c_un] = 'VEN'

    c_origem = cols_origem['cnpj_origem']
    mask_vazio = df[c_cli].isna() | (df[c_cli] == '') | (df[c_cli] == 'nan')
    df.loc[mask_vazio, c_cli] = df.loc[mask_vazio, c_origem]

    # =========================================================
    # MONTAGEM DO DATAFRAME FINAL
    # =========================================================
    df_final = pd.DataFrame()

    df_final['Estabelec'] = df[cols_origem['estabelec']]
    df_final['Espécie'] = df[cols_origem['especie']]
    df_final['Série'] = df[cols_origem['serie']]
    df_final['Título'] = df[cols_origem['titulo']]
    df_final['Parcela'] = df[cols_origem['parcela']].astype(str).str.replace(r'\.0$', '', regex=True).str.zfill(2)
    df_final['Unid.Negoc'] = df[cols_origem['unid_negoc']].astype(str).str.strip()
    df_final['Empresa'] = df[cols_origem['empresa']]
    df_final['Codigo'] = df[cols_origem['codigo']] 
    df_final['CNPJ/CPF Cliente'] = df[cols_origem['cnpj_cliente']]
    df_final['Nome Abrev'] = df[cols_origem['nome_abrev']]
    df_final['Dt.Emissão Orig'] = df[cols_origem['dt_emissao']]
    df_final['Dt.Emissão Últ.Ren'] = df[cols_origem['dt_emissao_ren']]
    df_final['Dt.Vencto Original'] = df[cols_origem['vencto']]
    df_final['Dt.Vencto Atual'] = df[cols_origem['dt_vencto_atual']]
    df_final['Vl.Bruto Orig.'] = df[cols_origem['vl_bruto']]
    df_final['Vl.líquido'] = df[cols_origem['vl_liquido']]
    
    df_final['Regional'] = (
        df_final['Estabelec'].astype(str).str.strip() +
        df_final['Série'].astype(str).str.strip() +
        df_final['Título'].astype(str).str.strip()
    )
    df_final['Base Operacional'] = df_final['Estabelec']
    df_final['Carteira'] = "" 
    df_final['Pacote'] = ""
    df_final['Raiz do CNPJ'] = df_final['CNPJ/CPF Cliente'].astype(str).str.split('/').str[0].str.strip()
    df_final['Razão Agrupada'] = ""
    
    mapa_negocio = {
        'PAX': 'Proair', 'LMO': 'Vigilância', 'PRT': 'Proair', 'GHD': 'Proair',
        'CTV': 'Logística', 'CSG': 'Carga Segura', 'EXE': 'Proair', 'VIG': 'Vigilância',
        'DTV': 'Logística', 'COF': 'Logística', 'MAN': 'Segel', 'NUM': 'Logística',
        'LOC': 'Segel', 'MON': 'Segel', 'CCV': 'Logística de Carga', 'FOR': 'Provig', 'VEN': 'Segel'
    }
    df_final['Negócio'] = df_final['Unid.Negoc'].str.upper().map(mapa_negocio).fillna('')

    df_final['Empresa'] = df_final['Empresa'].astype(str).str.strip().str.zfill(2)
    mapa_empresa = {
        '02': 'PROTEGE', '04': 'PROAIR', '05': 'PROVIG',
        '07': 'SERVIÇOS', '50': 'PROTEGE CARGO', '80': 'PORTARIA DO FUTURO'
    }
    df_final['Empresa'] = df_final['Empresa'].replace(mapa_empresa)

    cols_datas_excel = ['Dt.Emissão Orig', 'Dt.Emissão Últ.Ren', 'Dt.Vencto Original', 'Dt.Vencto Atual']
    for col in cols_datas_excel:
        df_final[col] = pd.to_datetime(df_final[col], errors='coerce')
        if pd.api.types.is_datetime64_any_dtype(df_final[col]):
             df_final[col] = df_final[col].dt.tz_localize(None)

    cols_valores = ['Vl.Bruto Orig.', 'Vl.líquido']
    for col in cols_valores:
        df_final[col] = pd.to_numeric(df_final[col], errors='coerce').fillna(0.0)

    dt_correcao = pd.to_datetime(data_correcao_str).normalize()
    df_final['Dias em Atraso'] = (dt_correcao - df_final['Dt.Vencto Original']).dt.days.fillna(0).astype(int)
    df_final['Dias em Atraso RE'] = (dt_correcao - df_final['Dt.Vencto Atual']).dt.days.fillna(0).astype(int)

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

    def classificar_status(row):
        dias_orig = row['Dias em Atraso']
        dias_re = row['Dias em Atraso RE']
        if dias_re <= 0: return "RENEGOCIAÇÕES A VENCER"
        elif dias_re < dias_orig: return "QUEBRA DE ACORDO / NÃO PAGAS"
        else: return "INADIMPLÊNCIA"

    df_final['Status'] = df_final.apply(classificar_status, axis=1)

    # =========================================================
    # REGRAS GERAIS DA EMPRESA (O VILÃO QUE SOBREESCREVIA)
    # =========================================================
    try:
        df_final = aplicar_regras_banco(df_final)
    except Exception as e:
        print(f"Aviso: Não foi possível aplicar regras do auxiliar: {e}")

    # =========================================================
    # NOVA REGRA: EXCEÇÕES (RODA POR ÚLTIMO PARA NÃO SER APAGADA)
    # =========================================================
    from .models import Excecao
    
    excecoes_qs = Excecao.objects.values('raiz_cnpj', 'unid_negoc', 'carteira')
    if excecoes_qs.exists():
        mapa_excecoes = {
            (str(e['raiz_cnpj']).strip(), str(e['unid_negoc']).strip()): e['carteira'] 
            for e in excecoes_qs
        }

        def aplicar_excecao_final(row):
            chave_dataset = (str(row['Raiz do CNPJ']).strip(), str(row['Unid.Negoc']).strip())
            # Se a chave existir, traz a carteira do banco. Se não, preserva o que a regra geral aplicou.
            return mapa_excecoes.get(chave_dataset, row['Carteira'])

        df_final['Carteira'] = df_final.apply(aplicar_excecao_final, axis=1)
    # =========================================================

    colunas_ordenadas = [
        'Regional', 'Base Operacional', 'Estabelec', 'Espécie', 'Série', 'Título', 'Parcela', 
        'Unid.Negoc', 'Negócio', 'Empresa', 'Carteira', 'Codigo', 'Pacote', 
        'Raiz do CNPJ', 'CNPJ/CPF Cliente', 'Razão Agrupada', 'Nome Abrev', 
        'Dt.Emissão Orig', 'Dt.Emissão Últ.Ren', 'Dt.Vencto Original', 'Dt.Vencto Atual', 
        'Vl.Bruto Orig.', 'Vl.líquido', 'Dias em Atraso', 'Dias em Atraso RE', 
        'Aging', 'Aging RE', 'Status'
    ]
    df_final = df_final[colunas_ordenadas]

    # =========================================================
    # SEPARAÇÃO EM 3 ABAS
    # =========================================================
    mask_juridico = df_final['Carteira'].astype(str).str.strip() == 'Recuperação Judicial'
    df_juridico = df_final[mask_juridico]
    df_nao_juridico = df_final[~mask_juridico]

    filtros_reneg = ['RENEGOCIAÇÕES A VENCER', 'QUEBRA DE ACORDO / NÃO PAGAS']
    df_renegociados = df_nao_juridico[df_nao_juridico['Status'].isin(filtros_reneg)]

    filtros_todos = ['INADIMPLÊNCIA', 'QUEBRA DE ACORDO / NÃO PAGAS']
    df_todos_clientes = df_nao_juridico[df_nao_juridico['Status'].isin(filtros_todos)]

    # =========================================================
    # INTELIGÊNCIA: POPULAR BANCO DE DADOS EM BACKGROUND
    # =========================================================
    try:
        popular_banco_relatorio(
            df_todos=df_todos_clientes, 
            df_renegociados=df_renegociados, 
            df_juridico=df_juridico, 
            data_corte_str=data_corte_str
        )
    except Exception as e:
        print(f"Erro ao popular tabelas do Dashboard: {e}")
    # =========================================================

    # =========================================================
    # GERAÇÃO DO ARQUIVO EXCEL
    # =========================================================
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
            worksheet.set_column('A:AB', 15)
            
            if not dataframe.empty:
                colunas = dataframe.columns.tolist()
                for col_name in ['Dt.Emissão Orig', 'Dt.Emissão Últ.Ren', 'Dt.Vencto Original', 'Dt.Vencto Atual']:
                    if col_name in colunas:
                        idx = colunas.index(col_name)
                        worksheet.set_column(idx, idx, 15, fmt_data)
                
                for col_name in ['Vl.Bruto Orig.', 'Vl.líquido']:
                    if col_name in colunas:
                        idx = colunas.index(col_name)
                        worksheet.set_column(idx, idx, 15, fmt_moeda)

                if 'Parcela' in colunas:
                    idx = colunas.index('Parcela')
                    worksheet.set_column(idx, idx, 10, fmt_texto)

        salvar_e_formatar(df_juridico, 'Jurídico')
        salvar_e_formatar(df_renegociados, 'Renegociados')
        salvar_e_formatar(df_todos_clientes, 'Todos os Clientes')

    return response

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

def debug_comparacao_excecoes(df_final, mapa_excecoes):
    print("\n" + "="*50)
    print("DEBUG: ANÁLISE DE CONTEÚDO - EXCEÇÕES")
    print("="*50)

    # 1. Mostra o que tem no Mapa (vindo do Banco)
    print("\n--- CONTEÚDO DA TABELA EXCEÇÕES (MAPA) ---")
    if not mapa_excecoes:
        print("AVISO: O mapa de exceções está VAZIO!")
    for chave, carteira in mapa_excecoes.items():
        # Usamos repr() para ver se existem espaços ocultos ou quebras de linha
        print(f"Chave no Banco: {repr(chave)} -> Carteira: {repr(carteira)}")

    # 2. Mostra o que tem no DataFrame para o cliente específico
    print("\n--- CONTEÚDO DO DATAFRAME (LINHA ALVO) ---")
    alvo_raiz = "03.007.331"
    alvo_unid = "CSG"
    
    # Filtra o dataframe para achar o registro
    filtro = (df_final['Raiz do CNPJ'] == alvo_raiz) & (df_final['Unid.Negoc'] == alvo_unid)
    df_teste = df_final[filtro]

    if not df_teste.empty:
        linha = df_teste.iloc[0]
        print(f"Raiz no DF: {repr(linha['Raiz do CNPJ'])} (Tamanho: {len(linha['Raiz do CNPJ'])})")
        print(f"Unid no DF: {repr(linha['Unid.Negoc'])} (Tamanho: {len(linha['Unid.Negoc'])})")
        
        # Simula a chave que o sistema está tentando montar
        chave_busca = (str(linha['Raiz do CNPJ']).strip(), str(linha['Unid.Negoc']).strip())
        print(f"Chave gerada para busca: {repr(chave_busca)}")
        
        if chave_busca in mapa_excecoes:
            print("\n>>> RESULTADO: O 'match' DEVERIA FUNCIONAR! A chave existe no mapa.")
        else:
            print("\n>>> RESULTADO: O 'match' FALHOU. A chave gerada não é idêntica à do mapa.")
    else:
        print(f"AVISO: Não encontrei no DataFrame nenhuma linha com Raiz {alvo_raiz} e Unid {alvo_unid}.")
    print("="*50 + "\n")

def popular_banco_contas_receber():

    """
    Lê a BaseGeral e popula a tabela ContasReceber, 
    preservando rigorosamente o histórico das notas já conciliadas ou exportadas.
    """
    qs = BaseGeral.objects.all().values()
    df = pd.DataFrame(list(qs))
    
    if df.empty:
        return False

    # Filtros
    if 'especie' in df.columns:
        df['especie'] = df['especie'].astype(str).str.strip().str.upper()
        df = df[~df['especie'].isin(['AN', 'DNI'])]

    # Datas
    cols_data = ['dt_emissao_orig', 'dt_vencto_atual']
    for col in cols_data:
        df[col] = pd.to_datetime(df[col], errors='coerce').dt.date

    # Valores
    cols_valor = [
        'vl_bruto_reneg', 'pis', 'cofins', 'csll', 'irrf', 'iss', 'inss',
        'desconto', 'liquidacao', 'multa', 'juros'
    ]
    for col in cols_valor:
        if col not in df.columns:
            df[col] = 0.0
        else:
            df[col] = df[col].astype(float).fillna(0.0)

    # Strings
    if 'parcela' in df.columns:
        df['parcela'] = df['parcela'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(2)
    if 'empresa' in df.columns:
        df['empresa'] = df['empresa'].astype(str).str.replace(r'\.0$', '', regex=True).str.strip().str.zfill(2)

    # ========================================================
    # A MÁGICA DA PRESERVAÇÃO DE HISTÓRICO
    # ========================================================
    
    # 1. Guarda as chaves únicas das notas que já estão CONCILIADAS ou EXPORTADAS no banco
    notas_protegidas = ContasReceber.objects.filter(status__in=['CONCILIADO', 'EXPORTADO'])
    chaves_protegidas = set()
    for n in notas_protegidas:
        chave = f"{n.estabelecimento}-{n.serie}-{n.titulo}-{n.parcela}"
        chaves_protegidas.add(chave)

    # 2. Apaga APENAS as notas que estão em "ABERTO" (Preserva a história do que já foi feito!)
    ContasReceber.objects.exclude(status__in=['CONCILIADO', 'EXPORTADO']).delete()
    
    novos_registros = []
    
    for _, row in df.iterrows():
        estab = str(row.get('estabelecimento', ''))
        serie = str(row.get('serie', ''))
        titulo = str(row.get('titulo', ''))
        parcela = str(row.get('parcela', ''))
        
        # Monta a chave da linha do Excel atual
        chave_excel = f"{estab}-{serie}-{titulo}-{parcela}"
        
        # 3. Se essa nota do Excel já foi trabalhada e está protegida no banco, pula ela!
        if chave_excel in chaves_protegidas:
            continue

        # Matemática exata do Excel para o Vl Líquido
        bruto = Decimal(str(row['vl_bruto_reneg']))
        impostos = Decimal(str(row['pis'])) + Decimal(str(row['cofins'])) + Decimal(str(row['csll'])) + Decimal(str(row['irrf'])) + Decimal(str(row['iss'])) + Decimal(str(row['inss']))
        descontos = Decimal(str(row['desconto'])) + Decimal(str(row['liquidacao']))
        acrescimos = Decimal(str(row['multa'])) + Decimal(str(row['juros']))
        vl_liq = bruto - impostos - descontos + acrescimos

        novos_registros.append(ContasReceber(
            estabelecimento=estab,
            especie=str(row.get('especie', '')),
            serie=serie,
            titulo=titulo,
            parcela=parcela,
            dt_emissao_orig=row.get('dt_emissao_orig'),
            dt_vencto_atual=row.get('dt_vencto_atual'),
            empresa=str(row.get('empresa', '')),
            cnpj=str(row.get('cnpj_cpf_cliente', '')),
            nome_abrev=str(row.get('nome_abrev', '')),
            vl_bruto=bruto,
            pis=Decimal(str(row['pis'])),
            cofins=Decimal(str(row['cofins'])),
            csll=Decimal(str(row['csll'])),
            irrf=Decimal(str(row['irrf'])),
            iss=Decimal(str(row['iss'])),
            inss=Decimal(str(row['inss'])),
            desconto=Decimal(str(row['desconto'])),
            abatimento=Decimal(str(row['liquidacao'])),
            multa=Decimal(str(row['multa'])),
            juros=Decimal(str(row['juros'])),
            vl_liquido=vl_liq,
            carteira=str(row.get('carteira', '')),
            nosso_numero=str(row.get('nosso_numero', '')),
            portador=str(row.get('portador', '')),
            codigo=str(row.get('codigo', '')),
            segmento=str(row.get('unid_negoc', '')),
            status='ABERTO' # Garante que as novas entram sempre como pendentes
        ))

    # Salva tudo de uma vez
    ContasReceber.objects.bulk_create(novos_registros, batch_size=2000)
    return True



def converter_moeda_br(valor_str: str) -> Decimal:
    """
    Remove pontos de milhar e converte a vírgula decimal para o formato matemático.
    """
    if not valor_str:
        return Decimal('0.00')
    
    try:
        valor_limpo = str(valor_str).strip().replace('.', '').replace(',', '.')
        return Decimal(valor_limpo)
    except (ValueError, InvalidOperation):
        return Decimal('0.00')