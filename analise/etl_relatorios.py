import pandas as pd
from decimal import Decimal
from django.db import transaction
from .models import BaseHistoricaRelatorio, ResumoInadimplencia, DevedorAging
from datetime import datetime

def clean_val(val, default=""):
    if pd.isna(val) or str(val).lower() == 'nan' or val == '':
        return default
    return val

def clean_date(val):
    if pd.isna(val) or str(val).lower() in ['nan', 'nat', '']:
        return None
    try:
        if hasattr(val, 'date'): return val.date()
        return pd.to_datetime(val).date()
    except:
        return None

def popular_banco_relatorio(df_todos, df_renegociados, df_juridico, data_corte_str):
    """
    Popula o Histórico, o Aging e o Resumo de Inadimplência.
    """
    # 1. Tratamento da Data (Garantindo que seja salva como STRING para evitar o ValueError)
    try:
        data_obj = pd.to_datetime(data_corte_str).date()
    except:
        data_obj = datetime.strptime(data_corte_str, "%Y-%m-%d").date()
    
    # ESTA É A CORREÇÃO: Forçamos a data a virar texto (Ex: '2026-03-23')
    data_str = data_obj.strftime('%Y-%m-%d')

    abas = [
        ('Todos', df_todos),
        ('Renegociados', df_renegociados),
        ('Jurídico', df_juridico)
    ]

    with transaction.atomic():
        # ==========================================================
        # 1. BASE HISTÓRICA
        # ==========================================================
        BaseHistoricaRelatorio.objects.filter(data_geracao=data_str).delete()
        
        objetos_historico = []
        for nome_aba, df in abas:
            for _, row in df.iterrows():
                obj = BaseHistoricaRelatorio(
                    data_geracao=data_str, # Usando a String aqui
                    aba_origem=nome_aba,
                    regional=clean_val(row.get('Regional')),
                    base_operacional=clean_val(row.get('Base Operacional')),
                    estabelecimento=str(clean_val(row.get('Estabelec'))),
                    especie=str(clean_val(row.get('Espécie'), ''))[:5],
                    serie=str(clean_val(row.get('Série'), ''))[:10],
                    titulo=int(clean_val(row.get('Título'), 0)),
                    parcela=str(clean_val(row.get('Parcela'), ''))[:5],
                    unid_negoc=clean_val(row.get('Unid.Negoc')),
                    negocio=clean_val(row.get('Negócio')),
                    empresa=str(clean_val(row.get('Empresa'), ''))[:10],
                    carteira=clean_val(row.get('Carteira')),
                    codigo=int(clean_val(row.get('Codigo'), 0)),
                    pacote=clean_val(row.get('Pacote')),
                    cnpj_raiz=clean_val(row.get('Raiz do CNPJ')),
                    cnpj_cpf=clean_val(row.get('CNPJ/CPF Cliente')),
                    razao_agrupada=clean_val(row.get('Razão Agrupada')),
                    nome_abrev=clean_val(row.get('Nome Abrev')),
                    dt_emissao_orig=clean_date(row.get('Dt.Emissão Orig')),
                    dt_emissao_ult_ren=clean_date(row.get('Dt.Emissão Últ.Ren')),
                    dt_vencto_original=clean_date(row.get('Dt.Vencto Original')),
                    dt_vencto_atual=clean_date(row.get('Dt.Vencto Atual')),
                    vl_bruto_orig=Decimal(str(clean_val(row.get('Vl.Bruto Orig.'), 0))),
                    vl_liquido=Decimal(str(clean_val(row.get('Vl.líquido'), 0))),
                    dias_atraso=int(clean_val(row.get('Dias em Atraso'), 0)),
                    dias_atraso_re=int(clean_val(row.get('Dias em Atraso RE'), 0)),
                    aging=clean_val(row.get('Aging')),
                    aging_re=clean_val(row.get('Aging RE')),
                    status=clean_val(row.get('Status'))
                )
                objetos_historico.append(obj)
                
        if objetos_historico:
            BaseHistoricaRelatorio.objects.bulk_create(objetos_historico, batch_size=2000)

        # ==========================================================
        # 2. DEVEDOR AGING
        # ==========================================================
        if not df_todos.empty:
            soma_aging = df_todos.groupby('Aging')['Vl.líquido'].sum()
            def get_soma(chave): return Decimal(str(soma_aging.get(chave, 0.0)))
            
            DevedorAging.objects.update_or_create(
                data_base=data_str, # Usando a String aqui
                defaults={
                    'ate_30_dias': get_soma('Até 30 dias'),
                    'de_31_a_60_dias': get_soma('31 a 60 dias'),
                    'de_61_a_90_dias': get_soma('61 a 90 dias'),
                    'de_91_a_120_dias': get_soma('91 a 120 dias'),
                    'de_121_a_150_dias': get_soma('121 a 150 dias'),
                    'de_151_a_180_dias': get_soma('151 a 180 dias'),
                    'mais_de_180_dias': get_soma('Mais de 180 dias'),
                }
            )

        # ==========================================================
        # 3. RESUMO INADIMPLÊNCIA
        # ==========================================================
        ResumoInadimplencia.objects.filter(data=data_str, tipo_relatorio='Resumo').delete()
        
        objetos_resumo = []

        # A. Agrupamento por Negócio (A partir da aba 'Todos')
        if not df_todos.empty and 'Negócio' in df_todos.columns:
            resumo_df = df_todos.groupby('Negócio')['Vl.líquido'].sum().reset_index()
            for _, row in resumo_df.iterrows():
                seguimento_nome = clean_val(row['Negócio'], 'Não Identificado')
                if not seguimento_nome: seguimento_nome = 'Não Identificado'
                valor_total = Decimal(str(row['Vl.líquido']))
                
                if valor_total > 0:
                    objetos_resumo.append(
                        ResumoInadimplencia(
                            seguimento=seguimento_nome,
                            data=data_str,
                            valor=valor_total,
                            tipo_relatorio='Resumo'
                        )
                    )

        # B. TOTAL DE RENEGOCIAÇÕES (Adicionando o cálculo que faltava)
        soma_renegociacoes = Decimal("0.00")
        if not df_renegociados.empty and 'Vl.líquido' in df_renegociados.columns:
            soma_renegociacoes = Decimal(str(df_renegociados['Vl.líquido'].sum()))
            
        # Salva o registro no banco com a nomenclatura exata que o Dashboard espera
        objetos_resumo.append(
            ResumoInadimplencia(
                seguimento='Total de Renegociações',
                data=data_str,
                valor=soma_renegociacoes,
                tipo_relatorio='Resumo'
            )
        )

        # Salva tudo de uma vez
        if objetos_resumo:
            ResumoInadimplencia.objects.bulk_create(objetos_resumo)

    return True