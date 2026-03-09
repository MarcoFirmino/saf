import pandas as pd
import numpy as np
from .models import (
    Bd_Clientes, 
    ResponsavelNegocio, 
    ResponsavelEmpresa, 
    Consolidado_Juridico, 
    EmpresasCorporativas,
    NegocioCorporativo,
    JurCargaSegura,
    Paycash
)

def aplicar_regras_banco(df):
    """
    Recebe o DataFrame 'df' processado.
    Enriquece: Razão Agrupada, Carteira, Pacote e Atualiza Empresa.
    Padroniza: Nome Abrev.
    """
    
    print("--- Iniciando enriquecimento (Camadas + Case Insensitive) ---")

    if 'Raiz do CNPJ' not in df.columns:
        return df

    # ==============================================================================
    # 0. CARREGAMENTO DOS DICIONÁRIOS
    # ==============================================================================
    try:
        print("Carregando tabelas do banco...")
        
        # --- BD CLIENTES ---
        dict_razao = dict(Bd_Clientes.objects.values_list('cnpj_raiz', 'perfil_grupo_ponto'))
        dict_carteira_cliente = dict(Bd_Clientes.objects.values_list('cnpj_raiz', 'perfil_responsavel_financeiro'))
        dict_pacote_cliente = dict(Bd_Clientes.objects.values_list('cnpj_raiz', 'perfil_fatura'))
        
        # --- RESPONSÁVEL NEGÓCIO ---
        qs_negocio = ResponsavelNegocio.objects.values_list('negocio', 'carteira')
        dict_carteira_negocio = {str(k).strip().upper(): v for k, v in qs_negocio if k is not None}

        # --- RESPONSÁVEL EMPRESA ---
        qs_empresa = ResponsavelEmpresa.objects.values_list('empresa', 'carteira')
        dict_carteira_empresa = {str(k).strip().upper(): v for k, v in qs_empresa if k is not None}

        # --- CONSOLIDADO JURÍDICO ---
        qs_juridico = Consolidado_Juridico.objects.values_list('chave', flat=True)
        dict_juridico = {str(k).strip().upper(): "Recuperação Judicial" for k in qs_juridico if k}

        # --- EMPRESAS CORPORATIVAS ---
        qs_emp_corp = EmpresasCorporativas.objects.values_list('nome', flat=True)
        dict_emp_corp = {str(k).strip().upper(): "CORPORATIVO" for k in qs_emp_corp if k}

        # --- NEGÓCIOS CORPORATIVOS ---
        qs_neg_corp = NegocioCorporativo.objects.values_list('nome', flat=True)
        dict_neg_corp = {str(k).strip().upper(): "CORPORATIVO" for k in qs_neg_corp if k}

        # --- JUR CARGA SEGURA ---
        qs_jur_carga = JurCargaSegura.objects.values_list('raiz', flat=True)
        dict_jur_carga = {str(k).strip(): "Jurídico - Carga Segura" for k in qs_jur_carga if k}

        # --- PAYCASH ---
        qs_paycash = Paycash.objects.values_list('chave', flat=True)
        dict_paycash = {str(k).strip().upper(): "PROTEGE CASH" for k in qs_paycash if k}

    except Exception as e:
        print(f"Erro ao ler banco: {e}")
        return df

    # ==============================================================================
    # 1. RAZÃO AGRUPADA
    # ==============================================================================
    chave_raiz = df['Raiz do CNPJ'].astype(str).str.strip()
    df['Razão Agrupada'] = chave_raiz.map(dict_razao)
    df['Razão Agrupada'] = df['Razão Agrupada'].fillna('N/D').replace(['', 'nan', 'NaN', 'None'], 'N/D')
    mask_vazio = df['Razão Agrupada'].astype(str).str.strip() == ''
    df.loc[mask_vazio, 'Razão Agrupada'] = 'N/D'

    # ==============================================================================
    # 2. CARTEIRA
    # ==============================================================================
    if 'Carteira' not in df.columns: df['Carteira'] = np.nan

    camada_1 = chave_raiz.map(dict_carteira_cliente)
    df['Carteira'] = camada_1.fillna(df['Carteira'])
    
    chave_negocio_upper = df['Negócio'].astype(str).str.strip().str.upper()
    camada_2 = chave_negocio_upper.map(dict_carteira_negocio)
    df['Carteira'] = camada_2.fillna(df['Carteira'])

    chave_empresa_upper = df['Empresa'].astype(str).str.strip().str.upper()
    camada_3 = chave_empresa_upper.map(dict_carteira_empresa)
    df['Carteira'] = camada_3.fillna(df['Carteira'])

    chave_regional_upper = df['Regional'].astype(str).str.strip().str.upper()
    camada_4 = chave_regional_upper.map(dict_juridico)
    df['Carteira'] = camada_4.fillna(df['Carteira'])

    df['Carteira'] = df['Carteira'].fillna('N/D').replace(['', 'nan', 'NaN', 'None'], 'N/D')
    mask_vazio_cart = df['Carteira'].astype(str).str.strip() == ''
    df.loc[mask_vazio_cart, 'Carteira'] = 'N/D'

    # ==============================================================================
    # 3. PACOTE
    # ==============================================================================
    print("Iniciando preenchimento do Pacote...")

    df['Pacote'] = df['Pacote'].replace(r'^\s*$', np.nan, regex=True)
    df['Pacote'] = df['Pacote'].replace(['', 'nan', 'NaN', 'None'], np.nan)
    
    if 'Pacote' not in df.columns:
        df['Pacote'] = np.nan

    # Regra 1: Empresas Corporativas
    camada_pacote_1 = chave_empresa_upper.map(dict_emp_corp)
    df['Pacote'] = camada_pacote_1.fillna(df['Pacote'])

    # Regra 2: Negócios Corporativos
    camada_pacote_2 = chave_negocio_upper.map(dict_neg_corp)
    df['Pacote'] = df['Pacote'].fillna(camada_pacote_2)

    # Regra 3: Bd_Clientes
    camada_pacote_3 = chave_raiz.map(dict_pacote_cliente)
    df['Pacote'] = df['Pacote'].fillna(camada_pacote_3)

    # Regra 4: Jurídico Carga Segura
    camada_pacote_4 = chave_raiz.map(dict_jur_carga)
    df['Pacote'] = camada_pacote_4.fillna(df['Pacote'])

    # Regra 6: Limpeza Final
    print("Aplicando limpeza final no Pacote...")
    df['Pacote'] = df['Pacote'].fillna('N/D')
    df['Pacote'] = df['Pacote'].replace(['', 'nan', 'NaN', 'None'], 'N/D')
    mask_vazio_pacote = df['Pacote'].astype(str).str.strip() == ''
    df.loc[mask_vazio_pacote, 'Pacote'] = 'N/D'

    # ==============================================================================
    # 4. ATUALIZAÇÃO DE EMPRESA (PAYCASH)
    # ==============================================================================
    print("Aplicando regra Paycash (Empresa)...")
    nova_empresa_paycash = chave_regional_upper.map(dict_paycash)
    df['Empresa'] = nova_empresa_paycash.fillna(df['Empresa'])

    # ==============================================================================
    # 5. PADRONIZAÇÃO DE NOMES (GRAN FINALE)
    # ==============================================================================
    print("Padronizando Nome Abrev pelo CNPJ Raiz (Gran Finale)...")

    # 1. Cria um dataframe auxiliar apenas com Raiz e Nome
    # 2. .drop_duplicates(keep='first') mantém apenas a PRIMEIRA aparição de cada Raiz
    # Isso define quem será o "Dono do Nome"
    df_nomes_padrao = df[['Raiz do CNPJ', 'Nome Abrev']].drop_duplicates(subset=['Raiz do CNPJ'], keep='first')

    # 3. Transforma em dicionário: { '12345678': 'EBAZAR', '99999999': 'OUTRO' }
    dict_padronizacao = dict(zip(df_nomes_padrao['Raiz do CNPJ'], df_nomes_padrao['Nome Abrev']))

    # 4. Aplica o dicionário em TODO o dataframe original
    # Todas as linhas com a mesma raiz receberão o nome que estava no dicionário
    df['Nome Abrev'] = chave_raiz.map(dict_padronizacao).fillna(df['Nome Abrev'])

    print("--- Enriquecimento concluído ---")
    
    return df