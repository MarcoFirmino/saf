
import pandas as pd
import numpy as np
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_POST
import json
from django.utils import timezone 
from django.db.models import Q
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
from .services import gerar_excel_contas_receber, processar_geral_pandas, popular_banco_contas_receber 
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
from django.db.models import Max, Sum
import unicodedata
from .etl_relatorios import processar_planilha_creditos
import re
from .forms import UploadSuspensosForm, EditarSuspensoForm
from .processador import processar_suspensos_db
from .models import (
    Paycash, 
    JurCargaSegura, 
    Consolidado_Juridico, 
    Bd_Clientes, 
    BaseGeral,
    ClienteSuspenso,
    ResumoInadimplencia,
    DevedorAging,
    BaseHistoricaRelatorio,
    CreditoNaoDestinado, 
    HistoricoAbatimento, 
    HistoricoContato
)


# ==============================================================================
# FUNÇÕES AUXILIARES GLOBAIS
# ==============================================================================

# --- FUNÇÕES DE LIMPEZA PADRONIZADAS ---
def clean_str(val, limit=None):
    if pd.isna(val) or str(val).strip().lower() == 'nan' or val is None:
        return "" 
    s = str(val).strip()
    if s.endswith('.0'): s = s[:-2]
    return s[:limit] if limit else s

def clean_decimal(val):
    if pd.isna(val) or str(val).strip().lower() == 'nan' or val == '' or val is None:
        return 0.0
    try:
        return float(val)
    except:
        return 0.0

def clean_date(val):
    if pd.isna(val) or str(val).strip().lower() == 'nan' or str(val).strip() == '':
        return None
    try:
        if hasattr(val, 'date'): return val.date()
        return pd.to_datetime(val, dayfirst=True).date()
    except:
        return None

# ==============================================================================
# VIEWS PRINCIPAIS
# ==============================================================================

def index(request):
    if request.user.is_authenticated:
        return redirect('suspensos')
    else:
        return redirect('login')


def password_change_done_custom(request):
    if request.user.is_authenticated:
        try:
            profile = request.user.profile
            profile.force_password_change = False
            profile.save()
        except:
            pass
    return render(request, 'analise/password_change_done.html')

# ==============================================================================
# IMPORTAR GERAL (Staging e Relatório)
# ==============================================================================

def normalizar_cabecalho(texto):
    """Limpa acentos, espaços e caracteres especiais do cabeçalho."""
    if not isinstance(texto, str):
        return str(texto)
    nfkd_form = unicodedata.normalize('NFKD', texto)
    texto_sem_acento = "".join([c for c in nfkd_form if not unicodedata.combining(c)])
    texto_lower = texto_sem_acento.lower()
    texto_limpo = re.sub(r'[^a-z0-9]', '', texto_lower)
    return texto_limpo

@login_required
def importar_geral_staging(request):
    """
    PASSO 1: Importação com Normalização de Cabeçalhos e Correção da Parcela (01, 02...).
    """
    if request.method == 'POST' and request.FILES.get('arquivo_geral'):
        arquivo = request.FILES['arquivo_geral']
        
        try:
            df = pd.read_excel(arquivo)
            
            # 1. Normaliza cabeçalhos (remove acentos, espaços, etc)
            # Ex: "Dt. Emissão" vira "dtemissao"
            df.columns = [normalizar_cabecalho(col) for col in df.columns]

            # 2. Conversão de datas (usando chaves normalizadas)
            cols_data = ['dtemissaoorig', 'dtemissaoultren', 'dtvenctooriginal', 'dtvenctoatual']
            for col in cols_data:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], errors='coerce')

            agora = timezone.now()

            with transaction.atomic():
                # Limpa a base antiga antes de importar a nova
                BaseGeral.objects.all().delete()
                
                objetos = []
                for row in df.to_dict('records'):
                    
                    # === CORREÇÃO DA PARCELA ===
                    # Garante que tenha 2 dígitos (1 -> 01)
                    raw_parcela = row.get('parcela')
                    parcela_final = ""
                    
                    if pd.notna(raw_parcela):
                        s_parc = str(raw_parcela).strip()
                        if s_parc.endswith('.0'): # Remove decimal se houver
                            s_parc = s_parc[:-2]
                        if s_parc:
                            parcela_final = s_parc.zfill(2) # Adiciona zero à esquerda
                    # ===========================

                    # === CORREÇÃO DA EMPRESA (OPCIONAL, SE QUISER JÁ NO BANCO) ===
                    raw_empresa = row.get('empresa')
                    empresa_final = ""
                    if pd.notna(raw_empresa):
                        s_emp = str(raw_empresa).strip()
                        if s_emp.endswith('.0'): s_emp = s_emp[:-2]
                        if s_emp: empresa_final = s_emp.zfill(2)

                    novo_registro = BaseGeral(
                        # Identificação
                        estabelecimento = clean_str(row.get('estabelec'), 4),
                        especie         = clean_str(row.get('especie'), 3),
                        serie           = clean_str(row.get('serie'), 5),
                        titulo          = int(row.get('titulo', 0)) if pd.notna(row.get('titulo')) else 0,
                        
                        # Usa a parcela corrigida
                        parcela         = parcela_final[:3],
                        
                        # Datas (chaves limpas)
                        dt_emissao_orig    = clean_date(row.get('dtemissaoorig')),
                        dt_emissao_ult_ren = clean_date(row.get('dtemissaoultren')),
                        dt_vencto_original = clean_date(row.get('dtvenctooriginal')),
                        dt_vencto_atual    = clean_date(row.get('dtvenctoatual')),
                        
                        # Destino
                        estab_dest   = clean_str(row.get('estabdest'), 4),
                        c_custo_dest = clean_str(row.get('ccustodest'), 4),
                        
                        # Empresa corrigida (02, 05...)
                        empresa      = empresa_final[:3], 
                        
                        # Cliente
                        cnpj             = clean_str(row.get('cnpj'), 18),
                        cnpj_cpf_cliente = clean_str(row.get('cnpjcpfcliente'), 18),
                        codigo           = int(row.get('codigo', 0)) if pd.notna(row.get('codigo')) else 0,
                        nome_abrev       = clean_str(row.get('nomeabrev'), 250),
                        
                        # Valores (Chaves limpas)
                        vl_bruto_reneg = clean_decimal(row.get('vlbrutoreneg')),
                        vl_bruto_orig  = clean_decimal(row.get('vlbrutoorig')),
                        
                        # Impostos e Descontos
                        pis            = clean_decimal(row.get('pis')),
                        cofins         = clean_decimal(row.get('cofins')),
                        csll           = clean_decimal(row.get('csll')),
                        irrf           = clean_decimal(row.get('irrf')),
                        iss            = clean_decimal(row.get('iss')),
                        inss           = clean_decimal(row.get('inss')),
                        desconto       = clean_decimal(row.get('desconto')),
                        liquidacao     = clean_decimal(row.get('liquidacao')),
                        acerto         = clean_decimal(row.get('acerto')),
                        conta_contabil = clean_decimal(row.get('contacontabil')),
                        multa          = clean_decimal(row.get('multa')),
                        juros          = clean_decimal(row.get('juros')),
                        vl_liq_orig    = clean_decimal(row.get('vlliqorig')),
                        vl_liquido     = clean_decimal(row.get('vlliquido')),
                        
                        # Classificação
                        carteira         = clean_str(row.get('carteira'), 2),
                        unid_negoc       = clean_str(row.get('unidnegoc'), 4),
                        cnpj_estab       = clean_str(row.get('cnpjestab'), 18),
                        gr_cli           = clean_str(row.get('grcli'), 5),
                        descricao_gr_cli = clean_str(row.get('descricaogrcli'), 20),
                        
                        # Régua
                        posicao_da_regua    = clean_str(row.get('posicaodaregua'), 100),
                        usuario_regua       = clean_str(row.get('usuarioregua'), 20),
                        ultima_movimentacao = clean_str(row.get('ultimamovimentacaodacobranca'), 10),
                        responsavel         = clean_str(row.get('responsavel'), 20),
                        motivo_renegociacao = clean_str(row.get('motivorenegociaco'), 10),
                        
                        # Outros
                        nosso_numero    = clean_str(row.get('nossonumero'), 15),
                        portador        = clean_str(row.get('portador'), 5),
                        observacao_nota = clean_str(row.get('observacaonota'), 15),

                        data_importacao = agora
                    )
                    objetos.append(novo_registro)

                BaseGeral.objects.bulk_create(objetos, batch_size=1000)
            
            messages.success(request, f"Sucesso! {len(objetos)} registros importados. Parcelas e datas corrigidas.")
            return redirect('importar_geral')

        except Exception as e:
            messages.error(request, f"Erro na importação: {e}")
            return redirect('importar_geral')

    # Lógica GET: Mostra status da base
    qtd_registros = 0
    ultima_atualizacao = None
    if BaseGeral.objects.exists():
        qtd_registros = BaseGeral.objects.count()
        reg = BaseGeral.objects.first()
        if reg: ultima_atualizacao = reg.data_importacao

    context = {
        'qtd_registros': qtd_registros,
        'ultima_atualizacao': ultima_atualizacao
    }
    return render(request, 'analise/importar_geral.html', context)
    
# ==============================================================================
# OUTRAS IMPORTAÇÕES (TODAS AGORA APONTAM PARA analise/)
# ==============================================================================
# --- FUNÇÃO AUXILIAR DE TRATAMENTO ---
def tratar_data(valor):
    """
    Converte valores do Excel para Data Python.
    Retorna None se for vazio ou inválido.
    """
    if pd.isna(valor) or valor == '' or str(valor).strip() == '':
        return None
    try:
        # dayfirst=True ajuda com datas brasileiras DD/MM/AAAA
        dt = pd.to_datetime(valor, dayfirst=True, errors='coerce')
        return dt.date() if pd.notnull(dt) else None
    except:
        return None

@login_required
def suspensos_view(request):
    # 1. CRIA O FORMULÁRIO VAZIO LOGO NO INÍCIO
    upload_form = UploadSuspensosForm()

    # --- AÇÃO 1: LIMPAR BANCO ---
    if request.method == "POST" and 'limpar_banco' in request.POST:
        try:
            ClienteSuspenso.objects.all().delete()
            messages.success(request, "Base de dados limpa com sucesso!")
        except Exception as e:
            messages.error(request, f"Erro ao limpar banco: {e}")
        return redirect('suspensos')

    # --- AÇÃO 2: IMPORTAR ARQUIVO ---
    if request.method == "POST" and 'upload_file' in request.POST:
        upload_form = UploadSuspensosForm(request.POST, request.FILES)
        
        if upload_form.is_valid():
            arquivo = request.FILES['arquivo']
            try:
                # Opcional: Limpar tabela antes de importar
                ClienteSuspenso.objects.all().delete()
                
                # Lê o Excel
                df = pd.read_excel(arquivo)
                
                objetos = []
                
                for _, row in df.iterrows():
                    objetos.append(ClienteSuspenso(
                        # Usando clean_str para remover o 'nan' e limitar caracteres
                        status=clean_str(row.get('Status'), 15) or 'Em Análise',
                        cnpj=clean_str(row.get('CNPJ'), 18),
                        cnpj_raiz=clean_str(row.get('CNPJ Raiz'), 12),
                        estabelecimento=clean_str(row.get('Estabelecimento'), 30),
                        razao_social=clean_str(row.get('Razão Social'), 200),
                        
                        # Usando clean_date em vez de tratar_data
                        data_suspensao=clean_date(row.get('Data Suspensão')),
                        data_restabelecimento=clean_date(row.get('Data Restabelecimento')),
                        operacao_ultimo_atendimento=clean_date(row.get('Operação - Último Atendimento')),
                        data_cancelamento=clean_date(row.get('Data Cancelamento')),
                        
                        # Campos Manuais
                        suspenso=clean_str(row.get('Suspenso'), 3),
                        cancelado_flag=clean_str(row.get('Cancelado?'), 3),
                        
                        # Outros
                        executivo=clean_str(row.get('EXECUTIVO'), 150),
                        inadimplencia2=clean_decimal(row.get('Inadimplência2'))
                    ))
                
                ClienteSuspenso.objects.bulk_create(objetos)
                messages.success(request, "Importação concluída com sucesso!")
                
            except Exception as e:
                messages.error(request, f"Erro na importação: {e}")
            
            return redirect('suspensos')

    # --- AÇÃO 3: PROCESSAR DADOS ---
    if request.method == "POST" and 'processar_dados' in request.POST:
        try:
            qtd = processar_suspensos_db()
            messages.success(request, f"Análise concluída! {qtd} registros foram atualizados.")
        except Exception as e:
            messages.error(request, f"Erro no processamento: {e}")
        return redirect('suspensos')

    # --- AÇÃO 4: EXPORTAR EXCEL ---
    exportar = False
    if request.method == "POST" and 'exportar_excel' in request.POST:
        exportar = True

    # --- LÓGICA DE FILTROS ---
    clientes = ClienteSuspenso.objects.all()

    # Define a fonte dos filtros (GET na tela normal, POST se for exportação)
    src = request.POST if exportar else request.GET

    # 1. Filtro: Status Calculado (NOVO)
    status_query = src.get('status')
    if status_query:
        clientes = clientes.filter(status__iexact=status_query)

    # 2. Filtro: CNPJ Raiz
    cnpj_raiz_query = src.get('cnpj_raiz')
    if cnpj_raiz_query:
        clientes = clientes.filter(cnpj_raiz__icontains=cnpj_raiz_query)

    # 3. Filtro: Data Suspensão
    data_query = src.get('data_suspensao')
    if data_query:
        clientes = clientes.filter(data_suspensao=data_query)

    # 4. Filtro: Suspenso (Manual)
    suspenso_query = src.get('suspenso')
    if suspenso_query == 'Sim':
        clientes = clientes.exclude(suspenso__isnull=True).exclude(suspenso__exact='')
    elif suspenso_query == 'Não':
        clientes = clientes.filter(suspenso__isnull=True) | clientes.filter(suspenso__exact='')

    # 5. Filtro: Cancelado (Manual)
    cancelado_query = src.get('cancelado')
    if cancelado_query == 'Sim':
        clientes = clientes.exclude(cancelado_flag__isnull=True).exclude(cancelado_flag__exact='')
    elif cancelado_query == 'Não':
        clientes = clientes.filter(cancelado_flag__isnull=True) | clientes.filter(cancelado_flag__exact='')
    
    # 6. Filtro: Status Calculado (O campo que adicionamos)
    status_query = src.get('status')
    if status_query:
        clientes = clientes.filter(status__iexact=status_query)

    # --- EXECUTA A EXPORTAÇÃO SE SOLICITADO ---
    if exportar:
        data = list(clientes.values())
        if not data:
            messages.warning(request, "Nada para exportar com os filtros atuais.")
            return redirect('suspensos')
            
        df = pd.DataFrame(data)
        
        # Remove fuso horário para Excel aceitar
        for col in df.select_dtypes(include=['datetimetz']).columns:
            df[col] = df[col].dt.tz_localize(None)

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="Suspensos_Export.xlsx"'
        df.to_excel(response, index=False)
        return response

    # --- RENDERIZAÇÃO FINAL ---
    return render(request, 'analise/suspensos.html', {
        'clientes': clientes,
        'upload_form': upload_form
    })

# --- VIEW PARA EDITAR (MODAL) ---
@login_required
def editar_suspenso(request, id):
    cliente = get_object_or_404(ClienteSuspenso, id=id)
    
    if request.method == "POST":
        form = EditarSuspensoForm(request.POST, instance=cliente)
        
        if form.is_valid():
            form.save()
            messages.success(request, f"Dados de {cliente.razao_social} atualizados.")
        else:
            # Aqui está o segredo: mostrar os erros reais do formulário
            erros = form.errors.as_text()
            messages.error(request, f"Erro ao salvar: {erros}")
            print(f"Erro de validação no ID {id}: {form.errors}")
            
    return redirect('suspensos')

@login_required
def importar_paycash_view(request):
    if request.method == "POST":
        arquivo = request.FILES.get('arquivo_paycash')
        if not arquivo:
            messages.error(request, "Nenhum arquivo selecionado.")
            return render(request, 'analise/importar_paycash.html')

        try:
            if arquivo.name.endswith('.csv'):
                df = pd.read_csv(arquivo, encoding='utf-8', sep=';', header=0)
            else:
                df = pd.read_excel(arquivo, header=0)
            
            df = df.fillna('')
            cols_to_str = ['Chave', 'UF', 'SERIE', 'NOME DO CLIENTE']
            for col in cols_to_str:
                if col in df.columns:
                    df[col] = df[col].astype(str)

            objetos_para_salvar = []
            for index, row in df.iterrows():
                data_banco = clean_date(row.get('DT.EMISSAO FATURA'))
                novo_registro = Paycash(
                    chave=str(row['Chave']).strip(),
                    dt_emissao_fatura=data_banco,
                    estabelecimento=int(row['ESTABELECIMENTO']) if row.get('ESTABELECIMENTO') else 0,
                    uf=str(row['UF']).strip()[:2],
                    nro_fatura=int(row['NRO.FATURA']) if row.get('NRO.FATURA') else 0,
                    serie=str(row['SERIE']).strip(),
                    rps=int(row['RPS']) if row.get('RPS') else 0,
                    codigo=int(row['CODIGO']) if row.get('CODIGO') else 0,
                    nome=str(row['NOME DO CLIENTE']).strip()
                )
                objetos_para_salvar.append(novo_registro)

            Paycash.objects.bulk_create(objetos_para_salvar)
            messages.success(request, f"Sucesso! {len(objetos_para_salvar)} registros importados.")

        except KeyError as e:
            messages.error(request, f"Erro de Cabeçalho: {str(e)}.")
        except Exception as e:
            messages.error(request, f"Erro crítico: {str(e)}")
            
    return render(request, 'analise/importar_paycash.html')

@login_required
def importar_jur_carga_view(request):
    if request.method == "POST":
        arquivo = request.FILES.get('arquivo_jur')
        if not arquivo:
            messages.error(request, "Nenhum arquivo selecionado.")
            return render(request, 'analise/importar_jur_carga.html')

        try:
            if arquivo.name.endswith('.csv'):
                df = pd.read_csv(arquivo, encoding='utf-8', sep=';', header=0)
            else:
                df = pd.read_excel(arquivo, header=0)
            
            df = df.fillna('').astype(str)
            objetos_para_salvar = []
            
            for index, row in df.iterrows():
                novo_registro = JurCargaSegura(
                    raiz=row.get('Raiz', '').strip(),
                    razao=row.get('Razão Social', '').strip(),
                    perfil=row.get('Perfil', '').strip(),
                    negocio=row.get('Negócio', '').strip(),
                    chave=row.get('chave', '').strip(),
                    executivo=row.get('Executivo', '').strip(),
                    responsavel_financeiro=row.get('Responsável Financeiro', '').strip(),
                    grupo=row.get('Grupo Ponto', '').strip(),
                    status=row.get('Status', '').strip()
                )
                objetos_para_salvar.append(novo_registro)

            JurCargaSegura.objects.bulk_create(objetos_para_salvar)
            messages.success(request, f"Sucesso! {len(objetos_para_salvar)} registros importados.")

        except Exception as e:
            messages.error(request, f"Erro ao processar: {str(e)}")
            
    return render(request, 'analise/importar_jur_carga.html')

@login_required
def importar_consolidado_view(request):
    if request.method == "POST":
        arquivo = request.FILES.get('arquivo_consolidado')
        if not arquivo:
            messages.error(request, "Nenhum arquivo selecionado.")
            return render(request, 'analise/importar_consolidado.html')

        try:
            if arquivo.name.endswith('.csv'):
                df = pd.read_csv(arquivo, encoding='utf-8', sep=';', header=0)
            else:
                df = pd.read_excel(arquivo, header=0)
            
            df = df.fillna('')
            df['Vl.Bruto Orig.'] = df['Vl.Bruto Orig.'].apply(clean_decimal)
            df['Vl.líquido'] = df['Vl.líquido'].apply(clean_decimal)

            objetos_para_salvar = []
            for index, row in df.iterrows():
                estab = str(row.get('Estabelec', '')).split('.')[0].strip()
                serie = str(row.get('Série', '')).split('.')[0].strip()
                titulo = str(row.get('Título', '')).split('.')[0].strip()
                chave_gerada = f"{estab}{serie}{titulo}"

                novo_registro = Consolidado_Juridico(
                    chave=chave_gerada,
                    classificacao=str(row.get('Classificação', '')).strip(),
                    estabelec=estab,
                    serie=serie,
                    titulo=int(titulo) if titulo.isdigit() else 0,
                    unid_neg=str(row.get('Unid.Neg', '')).strip(),
                    codigo=int(row.get('Codigo', 0)) if str(row.get('Codigo')).isdigit() else 0,
                    cnpj_cpf_cliente=str(row.get('CNPJ/CPF Cliente', '')).strip(),
                    grupo=str(row.get('Grupo', '')).strip(),
                    nome_abrev=str(row.get('Nome Abrev', '')).strip(),
                    dt_emissao_orig=clean_date(row.get('Dt.Emissão Orig')),
                    dt_vencto_original=clean_date(row.get('Dt.Vencto Original')),
                    vl_bruto_orig=row['Vl.Bruto Orig.'],
                    vl_liquido=row['Vl.líquido']
                )
                objetos_para_salvar.append(novo_registro)

            Consolidado_Juridico.objects.bulk_create(objetos_para_salvar)
            messages.success(request, f"Sucesso! {len(objetos_para_salvar)} registros importados.")

        except Exception as e:
            messages.error(request, f"Erro ao processar: {str(e)}")
            
    return render(request, 'analise/importar_consolidado.html')

@login_required
def importar_bd_clientes_view(request):
    if request.method == "POST":
        arquivo = request.FILES.get('arquivo_clientes')
        if not arquivo:
            messages.error(request, "Nenhum arquivo selecionado.")
            return render(request, 'analise/importar_bd_clientes.html')

        try:
            if arquivo.name.endswith('.csv'):
                df = pd.read_csv(arquivo, encoding='utf-8', sep=';', header=0, dtype=str)
            else:
                df = pd.read_excel(arquivo, header=0, dtype=str)
            df = df.fillna('')

            def manter_pontuacao_original(valor):
                val_str = str(valor).strip()
                if val_str in ['', 'nan', 'None', '-']: return ''
                if val_str.endswith('.0'): val_str = val_str[:-2]
                return val_str

            objetos_para_salvar = []
            for index, row in df.iterrows():
                novo_registro = Bd_Clientes(
                    cnpj_raiz=manter_pontuacao_original(row.get('CNPJ Raiz', '')),
                    razao_social=str(row.get('Razão Social', '')).strip(),
                    perfil_chave=manter_pontuacao_original(row.get('chave', '')),
                    perfil_fatura=str(row.get('Perfil', '')).strip(),
                    perfil_negocio=str(row.get('Negócio', '')).strip(),
                    perfil_executivo=str(row.get('Executivo', '')).strip(),
                    perfil_responsavel_financeiro=str(row.get('Responsável Financeiro', '')).strip(),
                    perfil_grupo_ponto=str(row.get('Grupo Ponto', '')).strip(),
                    perfil_status=str(row.get('Status', '')).strip()
                )
                objetos_para_salvar.append(novo_registro)

            Bd_Clientes.objects.bulk_create(objetos_para_salvar)
            messages.success(request, f"Sucesso! {len(objetos_para_salvar)} clientes importados.")

        except Exception as e:
            messages.error(request, f"Erro ao processar: {str(e)}")
            
    return render(request, 'analise/importar_bd_clientes.html')

# ==============================================================================
# LIMPEZA
# ==============================================================================

@login_required
def limpar_bd_clientes(request):
    try:
        count = Bd_Clientes.objects.count()
        Bd_Clientes.objects.all().delete()
        messages.warning(request, f"Limpeza concluída! {count} registros apagados.")
    except Exception as e:
        messages.error(request, f"Erro: {e}")
    return redirect('importar_bd_clientes')

@login_required
def limpar_consolidado(request):
    try:
        count = Consolidado_Juridico.objects.count()
        Consolidado_Juridico.objects.all().delete()
        messages.warning(request, f"Limpeza concluída! {count} registros apagados.")
    except Exception as e:
        messages.error(request, f"Erro: {e}")
    return redirect('importar_consolidado')

@login_required
def limpar_paycash(request):
    try:
        count = Paycash.objects.count()
        Paycash.objects.all().delete()
        messages.warning(request, f"Limpeza concluída! {count} registros apagados.")
    except Exception as e:
        messages.error(request, f"Erro: {e}")
    return redirect('importar_paycash')

@login_required
def relatorio_ar_view(request):
    """
    Página específica para o Relatório de Contas a Receber.
    """
    if request.method == 'POST':
        acao = request.POST.get('acao')
        
        # Prevenção: Verifica se a BaseGeral tem dados antes de qualquer ação
        if not BaseGeral.objects.exists():
            messages.error(request, "A base está vazia. Importe o arquivo geral primeiro.")
            return redirect('relatorio_ar')

        # ===============================================
        # AÇÃO 1: BOTÃO AZUL (Atualizar Banco)
        # ===============================================
        if acao == 'popular_banco':
            popular_banco_contas_receber()
            messages.success(request, "Base de Contas a Receber atualizada com sucesso e pronta para a Conciliação!")
            return redirect('relatorio_ar')

        # ===============================================
        # AÇÃO 2: BOTÃO BRANCO (Baixar Excel Original)
        # ===============================================
        elif acao == 'gerar_excel':
            excel_file = gerar_excel_contas_receber()
            
            if not excel_file:
                messages.error(request, "Erro ao gerar planilha.")
                return redirect('relatorio_ar')

            response = HttpResponse(
                excel_file,
                content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            )
            response['Content-Disposition'] = 'attachment; filename="Contas_Receber_Tabela_Dinamica.xlsx"'
            return response

    return render(request, 'analise/relatorio_ar.html')

@login_required
def processar_relatorio(request):
    """
    PASSO 2: Gera o Relatório Geral Tratado (Chama o service).
    """
    if request.method == 'POST':
        data_corte = request.POST.get('data_corte')
        data_correcao = request.POST.get('data_correcao')
        
        # Validação básica
        if not data_corte or not data_correcao:
            messages.error(request, "Por favor, preencha as datas de corte e correção.")
            return redirect('importar_geral')
        
        # Validação se a base está vazia
        if not BaseGeral.objects.exists():
            messages.error(request, "A Base Geral está vazia. Faça a importação no Passo 1 primeiro.")
            return redirect('importar_geral')

        try:
            # Chama a função do services.py que ajustamos anteriormente
            return processar_geral_pandas(request, data_corte, data_correcao)
            
        except ValueError as ve:
            messages.warning(request, str(ve))
            return redirect('importar_geral')
        except Exception as e:
            messages.error(request, f"Erro ao gerar relatório: {e}")
            return redirect('importar_geral')
            
    # Se tentar acessar via GET sem querer, volta para a tela inicial
    return redirect('importar_geral')

@login_required
def dashboard_inadimplencia(request):
    # 1. Trazemos TODOS os títulos ativos (A base já é filtrada pelo processo de PDD)
    dados = ResumoInadimplencia.objects.filter(tipo_relatorio='Resumo').values(
        'seguimento', 'data', 'valor'
    )
    
    if not dados:
        return render(request, 'dashboard.html', {'tabela': None})

    df = pd.DataFrame(dados)
    
    # HIGIENIZAÇÃO: Garante que "Logística" e "Logística " sejam agrupados juntos
    df['seguimento'] = df['seguimento'].str.strip()
    
    # 2. AGRUPAMENTO: Soma todos os títulos (estab+serie+titulo) de um mesmo segmento/data
    df_pivot = df.pivot_table(
        index='seguimento', 
        columns='data', 
        values='valor',
        aggfunc='sum' 
    ).fillna(0)
    
    # --- LÓGICA DO DEMONSTRATIVO ---
    segmentos_operacionais = [
        'Logística', 'Vigilância', 'Segel', 'Proair', 
        'Provig', 'Logística de Carga', 'Carga Segura'
    ]
    
    # Filtra com segurança
    segmentos_presentes = [s for s in segmentos_operacionais if s in df_pivot.index]
    
    # A. Inadimplência Total - Bruta
    df_pivot.loc['Inadimplência Total - Bruta'] = df_pivot.loc[segmentos_presentes].sum()
    
    # B. Depósitos Não Identificados
    if 'Depósitos Não Identificados' not in df_pivot.index:
        df_pivot.loc['Depósitos Não Identificados'] = 0
        
    # C. Inadimplência Total - Líquida
    df_pivot.loc['Inadimplência Total - Líquida'] = (
        df_pivot.loc['Inadimplência Total - Bruta'] - df_pivot.loc['Depósitos Não Identificados']
    )
    
    # D. Total de Renegociações
    if 'Total de Renegociações' not in df_pivot.index:
        df_pivot.loc['Total de Renegociações'] = 0

    # 4. ORDENAÇÃO FINAL
    ordem_linhas = segmentos_presentes + [
        'Inadimplência Total - Bruta', 
        'Depósitos Não Identificados', 
        'Inadimplência Total - Líquida', 
        'Total de Renegociações'
    ]
    
    df_final = df_pivot.reindex(ordem_linhas).fillna(0)

    # 5. PREPARAÇÃO PARA O HTML
    contexto = {
        'colunas_data': df_final.columns,
        'linhas_relatorio': [
            {
                'nome': str(nome),
                'valores': row.values,
                'estilo': 'tabela-total' if 'Total' in str(nome) or 'Líquida' in str(nome) else 'tabela-comum'
            } 
            for nome, row in df_final.iterrows()
        ]
    }

    return render(request, 'dashboard.html', contexto)

@login_required
def dashboard_resumo(request):
    # 1. Busca os dados
    qs = ResumoInadimplencia.objects.filter(tipo_relatorio='Resumo').values()
    
    if not qs:
        return render(request, 'analise/dashboard.html', {'datas': [], 'linhas': []})

    df = pd.DataFrame(qs)
    
    # 2. Pivot e Ordenação Cronológica (Datas na horizontal)
    df_pivot = df.pivot(index='seguimento', columns='data', values='valor').fillna(0)
    df_pivot.columns = pd.to_datetime(df_pivot.columns)
    df_pivot = df_pivot.sort_index(axis=1)

    # 3. Cálculos de Totais
    operacionais = ['Logística', 'Vigilância', 'Segel', 'Proair', 'Provig', 'Logística de Carga', 'Carga Segura']
    presentes = [s for s in operacionais if s in df_pivot.index]

    df_pivot.loc['Inadimplência Total - Bruta'] = df_pivot.loc[presentes].sum()
    
    if 'Depósitos Não Identificados' not in df_pivot.index:
        df_pivot.loc['Depósitos Não Identificados'] = 0
        
    df_pivot.loc['Inadimplência Total - Líquida'] = (
        df_pivot.loc['Inadimplência Total - Bruta'] - df_pivot.loc['Depósitos Não Identificados']
    )
    
    if 'Total de Renegociações' not in df_pivot.index:
        df_pivot.loc['Total de Renegociações'] = 0

    # 4. Cálculo de Variação (Último mês vs Penúltimo)
    if len(df_pivot.columns) >= 2:
        df_pivot['variacao'] = df_pivot.iloc[:, -1] - df_pivot.iloc[:, -2]
    else:
        df_pivot['variacao'] = 0

    # 5. CRIAÇÃO DO DF_FINAL (AQUI ESTÁ A SOLUÇÃO)
    ordem_linhas = presentes + [
        'Inadimplência Total - Bruta', 
        'Depósitos Não Identificados', 
        'Inadimplência Total - Líquida', 
        'Total de Renegociações'
    ]
    df_final = df_pivot.reindex([o for o in ordem_linhas if o in df_pivot.index])

    # 6. Dados para os CARDS do topo (Pega a última data disponível)
    # Usamos .iloc[:, -2] porque a última coluna ( -1 ) agora é a 'variacao'
    resumo_kpi = {
        'bruta': df_final.loc['Inadimplência Total - Bruta'].iloc[-2],
        'liquida': df_final.loc['Inadimplência Total - Líquida'].iloc[-2],
        'renegociacao': df_final.loc['Total de Renegociações'].iloc[-2],
    }

    contexto = {
        'datas': df_final.columns[:-1], # Datas sem a coluna de variação
        'linhas': [
            {
                'nome': nome, 
                'valores': row[:-1], 
                'variacao': row['variacao'], 
                'destaque': nome in ['Inadimplência Total - Bruta', 'Inadimplência Total - Líquida', 'Total de Renegociações']
            } for nome, row in df_final.iterrows()
        ],
        'resumo': resumo_kpi,
        'segmento_ativo': 'resumo'
    }
    return render(request, 'analise/dashboard.html', contexto)
    # =========================================================
    # Agin
    # =========================================================

@login_required
def aging_view(request):
    # 1. Captura os IDs do formulário de filtro (GET)
    data_atual_id = request.GET.get('data_atual')
    data_base_id = request.GET.get('data_base')

    # 2. Busca todo o histórico para as linhas superiores da tabela
    historico = DevedorAging.objects.all().order_by('data_base')
    
    # Lista para os selects do filtro (mais recentes primeiro)
    registros_dropdown = historico.order_by('-data_base')

    # 3. Define quais registros usar para o cálculo da variação
    obj_atual = None
    obj_base = None

    if data_atual_id and data_base_id:
        obj_atual = DevedorAging.objects.filter(id=data_atual_id).first()
        obj_base = DevedorAging.objects.filter(id=data_base_id).first()
    else:
        # Fallback: Se não houver filtro, compara os dois últimos do histórico
        if historico.count() >= 2:
            obj_atual = historico.last()
            obj_base = historico[historico.count() - 2]

    # 4. Preparação dos cálculos de Variação
    variacao_reais = []
    variacao_percentual = []
    
    # Mapeamento exato das colunas do seu Model DevedorAging
    campos = [
        'ate_30_dias', 'de_31_a_60_dias', 'de_61_a_90_dias', 
        'de_91_a_120_dias', 'de_121_a_150_dias', 'de_151_a_180_dias', 
        'mais_de_180_dias', 'total'
    ]

    if obj_atual and obj_base:
        for campo in campos:
            # Forçamos Decimal para evitar o erro de precisão (.37999999)
            v_atual = Decimal(str(getattr(obj_atual, campo) or 0))
            v_base = Decimal(str(getattr(obj_base, campo) or 0))
            
            # Cálculo Variação R$ (2 casas decimais)
            diff_rs = (v_atual - v_base).quantize(Decimal("0.00"), rounding=ROUND_HALF_UP)
            variacao_reais.append(diff_rs)
            
            # Cálculo Variação % (1 casa decimal)
            if v_base != 0:
                diff_pct = ((v_atual - v_base) / abs(v_base)) * 100
                variacao_percentual.append(diff_pct.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))
            else:
                variacao_percentual.append(Decimal("0.0"))

    context = {
        'historico': historico,
        'registros_dropdown': registros_dropdown,
        'obj_atual': obj_atual,
        'obj_base': obj_base,
        'var_reais': variacao_reais,
        'var_pct': variacao_percentual,
        'segmento_ativo': 'aging'
    }
    return render(request, 'analise/aging.html', context)

@login_required
def renegociacoes_view(request):
    ultima_data = BaseHistoricaRelatorio.objects.filter(aba_origem='Renegociados').aggregate(Max('data_geracao'))['data_geracao__max']
    
    if not ultima_data:
        return render(request, 'analise/renegociados.html', {'vazio': True})
        
    qs = BaseHistoricaRelatorio.objects.filter(data_geracao=ultima_data, aba_origem='Renegociados')
    
    # Filtros
    f_status = request.GET.get('status', '')
    f_pacote = request.GET.get('pacote', '')
    f_negocio = request.GET.get('negocio', '')
    
    if f_status: qs = qs.filter(status=f_status)
    if f_pacote: qs = qs.filter(pacote=f_pacote)
    if f_negocio: qs = qs.filter(negocio=f_negocio)
    
    # Opções dinâmicas
    opcoes_base = BaseHistoricaRelatorio.objects.filter(data_geracao=ultima_data, aba_origem='Renegociados')
    lista_status = opcoes_base.exclude(status__isnull=True).exclude(status='').values_list('status', flat=True).distinct().order_by('status')
    lista_pacote = opcoes_base.exclude(pacote__isnull=True).exclude(pacote='').values_list('pacote', flat=True).distinct().order_by('pacote')
    lista_negocio = opcoes_base.exclude(negocio__isnull=True).exclude(negocio='').values_list('negocio', flat=True).distinct().order_by('negocio')
    
    # ==========================================
    # NOVO: CÁLCULO PARA OS CARDS DO TOPO
    # (Calcula com base na tabela filtrada)
    # ==========================================
    total_quebra = qs.filter(status='QUEBRA DE ACORDO / NÃO PAGAS').aggregate(Sum('vl_liquido'))['vl_liquido__sum'] or 0
    total_vencer = qs.filter(status='RENEGOCIAÇÕES A VENCER').aggregate(Sum('vl_liquido'))['vl_liquido__sum'] or 0
    total_geral_cards = total_quebra + total_vencer

    # Processamento Pandas
    df = pd.DataFrame(list(qs.values('nome_abrev', 'dt_vencto_atual', 'vl_liquido')))
    
    if df.empty:
        return render(request, 'analise/renegociados.html', {
            'vazio': True, 'lista_status': lista_status, 'lista_pacote': lista_pacote, 'lista_negocio': lista_negocio,
            'card_quebra': total_quebra, 'card_vencer': total_vencer, 'card_total': total_geral_cards
        })
        
    df['dt_vencto_atual'] = pd.to_datetime(df['dt_vencto_atual'])
    df['Ano'] = df['dt_vencto_atual'].dt.year.fillna(0).astype(int).astype(str)
    df.loc[df['Ano'] == '0', 'Ano'] = 'Sem Data'
    
    pivot = df.pivot_table(index='nome_abrev', columns='Ano', values='vl_liquido', aggfunc='sum', fill_value=0)
    pivot['Total'] = pivot.sum(axis=1)
    pivot = pivot.sort_values(by='Total', ascending=False)
    totais_colunas = pivot.sum(axis=0)
    
    anos_colunas = [col for col in pivot.columns if col != 'Total']
    linhas = []
    for cliente, row in pivot.iterrows():
        linhas.append({
            'cliente': cliente,
            'valores': [row[ano] for ano in anos_colunas],
            'total': row['Total']
        })
        
    context = {
        'anos': anos_colunas,
        'linhas': linhas,
        'totais_rodape': [totais_colunas[ano] for ano in anos_colunas],
        'total_geral': totais_colunas['Total'],
        'lista_status': lista_status,
        'lista_pacote': lista_pacote,
        'lista_negocio': lista_negocio,
        'f_status': f_status,
        'f_pacote': f_pacote,
        'f_negocio': f_negocio,
        'data_ref': ultima_data,
        'segmento_ativo': 'renegociados',
        
        # Variáveis dos Cards
        'card_quebra': total_quebra,
        'card_vencer': total_vencer,
        'card_total': total_geral_cards
    }
    
    return render(request, 'analise/renegociados.html', context)
    # ==========================================
    # Aging jurídico
    # ==========================================

@login_required
def aging_juridico_view(request):
    ultima_data = BaseHistoricaRelatorio.objects.filter(aba_origem='Jurídico').aggregate(Max('data_geracao'))['data_geracao__max']
    
    if not ultima_data:
        return render(request, 'analise/aging_juridico.html', {'vazio': True, 'segmento_ativo': 'aging_juridico'})
        
    # Filtra apenas a aba Jurídico da última foto
    qs = BaseHistoricaRelatorio.objects.filter(data_geracao=ultima_data, aba_origem='Jurídico')
    
    # Captura filtros do formulário
    f_negocio = request.GET.get('negocio', '')
    f_empresa = request.GET.get('empresa', '')
    
    if f_negocio: qs = qs.filter(negocio=f_negocio)
    if f_empresa: qs = qs.filter(empresa=f_empresa)
    
    # Opções para os Selects
    opcoes_base = BaseHistoricaRelatorio.objects.filter(data_geracao=ultima_data, aba_origem='Jurídico')
    lista_negocio = opcoes_base.exclude(negocio__isnull=True).exclude(negocio='').values_list('negocio', flat=True).distinct().order_by('negocio')
    lista_empresa = opcoes_base.exclude(empresa__isnull=True).exclude(empresa='').values_list('empresa', flat=True).distinct().order_by('empresa')
    
    # ==========================================
    # CÁLCULOS PARA OS CARDS
    # ==========================================
    total_geral = qs.aggregate(Sum('vl_liquido'))['vl_liquido__sum'] or Decimal('0.00')
    total_vencer = qs.filter(aging='A VENCER').aggregate(Sum('vl_liquido'))['vl_liquido__sum'] or Decimal('0.00')
    total_vencido = total_geral - total_vencer

    # ==========================================
    # PROCESSAMENTO PANDAS (PIVOT TABLE)
    # ==========================================
    df = pd.DataFrame(list(qs.values('nome_abrev', 'aging', 'vl_liquido')))
    
    if df.empty:
        return render(request, 'analise/aging_juridico.html', {
            'vazio': True, 'lista_negocio': lista_negocio, 'lista_empresa': lista_empresa,
            'card_total': total_geral, 'card_vencer': total_vencer, 'card_vencido': total_vencido,
            'segmento_ativo': 'aging_juridico'
        })
        
    # Define a ordem exata das colunas de Aging para não ficar bagunçado (alfabético)
    ordem_aging = [
        "A VENCER", "Até 30 dias", "31 a 60 dias", "61 a 90 dias", 
        "91 a 120 dias", "121 a 150 dias", "151 a 180 dias", "Mais de 180 dias"
    ]
    
    # Cria a Tabela Dinâmica
    pivot = df.pivot_table(index='nome_abrev', columns='aging', values='vl_liquido', aggfunc='sum', fill_value=0)
    pivot['Total'] = pivot.sum(axis=1)
    pivot = pivot.sort_values(by='Total', ascending=False)
    
    # Mantém apenas as colunas que têm dados, mas respeitando a nossa ordem lógica
    colunas_presentes = [col for col in ordem_aging if col in pivot.columns]
    totais_colunas = pivot.sum(axis=0)
    
    linhas = []
    for cliente, row in pivot.iterrows():
        linhas.append({
            'cliente': cliente,
            'valores': [row[col] for col in colunas_presentes],
            'total': row['Total']
        })
        
    context = {
        'colunas_aging': colunas_presentes,
        'linhas': linhas,
        'totais_rodape': [totais_colunas[col] for col in colunas_presentes],
        'total_geral_tabela': totais_colunas['Total'],
        
        'lista_negocio': lista_negocio,
        'lista_empresa': lista_empresa,
        'f_negocio': f_negocio,
        'f_empresa': f_empresa,
        'data_ref': ultima_data,
        
        'card_total': total_geral,
        'card_vencer': total_vencer,
        'card_vencido': total_vencido,
        'segmento_ativo': 'aging_juridico' # Importante para acender o botão no menu
    }
    
    return render(request, 'analise/aging_juridico.html', context)

@login_required
def gerenciar_resumo(request):
    if not request.user.is_superuser:
        return redirect('dashboard_resumo')

    queryset = ResumoInadimplencia.objects.all().order_by('-data', 'seguimento')
    
    # Capturando filtros da URL
    data_filtro = request.GET.get('data', '')
    seguimento_filtro = request.GET.get('seguimento', '')

    # Aplicando os filtros (se existirem)
    if data_filtro:
        queryset = queryset.filter(data=data_filtro)
    if seguimento_filtro:
        queryset = queryset.filter(seguimento__icontains=seguimento_filtro)

    paginator = Paginator(queryset, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'analise/gerenciar_resumo.html', {
        'page_obj': page_obj,
        'data_filtro': data_filtro,
        'seguimento_filtro': seguimento_filtro
    })

@login_required
@require_POST
def api_resumo_acao(request):
    if not request.user.is_superuser:
        return JsonResponse({'status': 'erro', 'message': 'Não autorizado'}, status=403)

    try:
        data = json.loads(request.body)
        acao = data.get('acao')

        if acao == 'criar':
            valor_novo = str(data.get('valor', '0')).replace(',', '.')
            nova_linha = ResumoInadimplencia(
                data=data.get('data'), # O input type="date" envia em YYYY-MM-DD nativamente
                seguimento=data.get('seguimento'),
                valor=valor_novo,
                tipo_relatorio=data.get('tipo_relatorio', 'Resumo')
            )
            nova_linha.full_clean()
            nova_linha.save()
            return JsonResponse({'status': 'sucesso', 'id': nova_linha.pk})

        # Para edição e exclusão, precisamos do ID
        pk = data.get('id')
        instancia = get_object_or_404(ResumoInadimplencia, pk=pk)

        if acao == 'excluir':
            instancia.delete()
            return JsonResponse({'status': 'sucesso'})

        elif acao == 'editar':
            campo = data.get('campo')
            valor = data.get('valor').strip()

            if campo == 'valor':
                valor = valor.replace(',', '.')
            
            # Tratamento de Data BR para salvar no banco
            if campo == 'data' and '/' in valor:
                try:
                    valor = datetime.strptime(valor, '%d/%m/%Y').date()
                except ValueError:
                    return JsonResponse({'status': 'erro', 'message': 'Formato de data inválido. Use DD/MM/AAAA'}, status=400)
            
            setattr(instancia, campo, valor)
            instancia.full_clean()
            instancia.save()
            return JsonResponse({'status': 'sucesso'})

    except Exception as e:
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

@login_required
def gerenciar_base_geral(request):
    if not request.user.is_superuser:
        messages.error(request, "Acesso negado.")
        return redirect('dashboard_resumo')

    # Buscamos todos os registros da BaseGeral
    queryset = BaseGeral.objects.all().order_by('-data_importacao', 'id')
    
    # Paginação: 50 registros por vez para não travar o browser
    paginator = Paginator(queryset, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'analise/gerenciar_base.html', {'page_obj': page_obj})

@login_required
@require_POST
def api_base_geral_acao(request):
    """ Endpoint para salvar edições ou excluir via AJAX """
    if not request.user.is_superuser:
        return JsonResponse({'status': 'erro', 'message': 'Não autorizado'}, status=403)

    try:
        data = json.loads(request.body)
        acao = data.get('acao')
        pk = data.get('id')
        instancia = get_object_or_404(BaseGeral, pk=pk)

        if acao == 'excluir':
            instancia.delete()
            return JsonResponse({'status': 'sucesso'})

        elif acao == 'editar':
            # Mapeamento dinâmico dos campos enviados
            campo = data.get('campo')
            valor = data.get('valor')
            
            # Tratamento básico para campos numéricos ou de data se necessário
            # Aqui usamos setattr para atualizar qualquer campo enviado pelo JS
            setattr(instancia, campo, valor)
            instancia.save()
            return JsonResponse({'status': 'sucesso'})

    except Exception as e:
        return JsonResponse({'status': 'erro', 'message': str(e)}, status=400) 
    

@login_required
def listar_creditos(request):
    # Lista apenas os que têm saldo a devolver. Se quiser listar todos, tire o filtro.
    creditos = CreditoNaoDestinado.objects.filter(saldo_final__gt=0).order_by('data')
    return render(request, 'analise/listar_creditos.html', {'creditos': creditos})

@login_required
def detalhe_credito(request, dni):
    credito = get_object_or_404(CreditoNaoDestinado, dni=dni)
    
    if request.method == 'POST':
        acao = request.POST.get('acao')
        
        # Adicionando um novo Contato
        if acao == 'novo_contato':
            anotacao = request.POST.get('anotacao')
            HistoricoContato.objects.create(
                credito_origem=credito,
                anotacao=anotacao,
                usuario=request.user
            )
            messages.success(request, "Contato registrado com sucesso!")
            
       # Adicionando um novo Abatimento
        elif acao == 'novo_abatimento':
            valor_digitado = request.POST.get('valor', '0').strip()
            
            # Limpeza do padrão BR
            if ',' in valor_digitado:
                valor_limpo = valor_digitado.replace('.', '').replace(',', '.')
            else:
                valor_limpo = valor_digitado
            
            observacao = request.POST.get('observacao')
            
            try:
                # A MÁGICA ACONTECE AQUI: Usando Decimal em vez de float!
                valor_decimal = Decimal(valor_limpo)
                
                if valor_decimal > credito.saldo_final:
                    messages.error(request, "O valor do abatimento não pode ser maior que o Saldo Final!")
                elif valor_decimal <= 0:
                    messages.error(request, "O valor do abatimento deve ser maior que zero!")
                else:
                    HistoricoAbatimento.objects.create(
                        credito_origem=credito,
                        valor=valor_decimal, # Passando o Decimal para o banco
                        observacao=observacao,
                        usuario=request.user
                    )
                    messages.success(request, "Abatimento registrado e saldo atualizado!")
            except (ValueError, InvalidOperation):
                messages.error(request, "Valor inválido para abatimento. Use o formato 21.000,00 ou 21000.00")
        
        # EXCLUIR CONTATO
        elif acao == 'excluir_contato':
            contato_id = request.POST.get('contato_id')
            contato = get_object_or_404(HistoricoContato, id=contato_id, credito_origem=credito)
            contato.delete()
            messages.success(request, "Contato excluído com sucesso!")

        # EXCLUIR ABATIMENTO
        elif acao == 'excluir_abatimento':
            abatimento_id = request.POST.get('abatimento_id')
            abatimento = get_object_or_404(HistoricoAbatimento, id=abatimento_id, credito_origem=credito)
            abatimento.delete() # Isso já dispara a função que recalcula o saldo do DNI!
            messages.success(request, "Abatimento excluído. O saldo retornou ao DNI com sucesso!")
                
        return redirect('detalhe_credito', dni=dni)

    return render(request, 'analise/detalhe_credito.html', {'credito': credito})

@login_required
def importar_creditos_view(request):
    if not request.user.is_superuser:
        return redirect('dashboard_resumo')

    if request.method == 'POST' and request.FILES.get('planilha'):
        arquivo = request.FILES['planilha']
        sucesso, erros = processar_planilha_creditos(arquivo)
        
        if sucesso > 0:
            messages.success(request, f"Importação concluída! {sucesso} registros processados.")
        if erros:
            for erro in erros:
                messages.warning(request, erro)
        
        return redirect('listar_creditos')

    return render(request, 'analise/importar_creditos.html')

@login_required
def exportar_creditos_excel(request):
    # Função auxiliar para formatar moeda em PT-BR (Ex: 21000.50 -> 21.000,50)
    def formatar_moeda_br(valor):
        if valor is None: return "0,00"
        return f'{valor:,.2f}'.replace(',', 'X').replace('.', ',').replace('X', '.')

    # --- 1. Aba PRINCIPAL (Créditos) ---
    creditos = CreditoNaoDestinado.objects.all().values(
        'dni', 'data', 'estab', 'cliente', 'empresa', 'banco', 'credito', 'debitos', 'saldo_final'
    )
    df_creditos = pd.DataFrame(list(creditos))
    
    if not df_creditos.empty:
        df_creditos.columns = ['DNI', 'Data Origem', 'Estab', 'Cliente', 'Empresa', 'Banco', 'Crédito Original', 'Total Débitos', 'Saldo Final']
        
        # Formata Data
        df_creditos['Data Origem'] = pd.to_datetime(df_creditos['Data Origem']).dt.strftime('%d/%m/%Y')
        
        # Formata Valores (Moeda BR)
        df_creditos['Crédito Original'] = df_creditos['Crédito Original'].apply(formatar_moeda_br)
        df_creditos['Total Débitos'] = df_creditos['Total Débitos'].apply(formatar_moeda_br)
        df_creditos['Saldo Final'] = df_creditos['Saldo Final'].apply(formatar_moeda_br)

    # --- 2. Aba ABATIMENTOS ---
    abatimentos = HistoricoAbatimento.objects.all().select_related('credito_origem', 'usuario').values(
        'credito_origem__dni', 'data_abatimento', 'valor', 'observacao', 'usuario__username'
    )
    df_abatimentos = pd.DataFrame(list(abatimentos))
    if not df_abatimentos.empty:
        df_abatimentos.columns = ['DNI', 'Data Abatimento', 'Valor Abatido', 'Observação', 'Usuário']
        df_abatimentos['Data Abatimento'] = pd.to_datetime(df_abatimentos['Data Abatimento']).dt.strftime('%d/%m/%Y')
        
        # Formata Valor (Moeda BR)
        df_abatimentos['Valor Abatido'] = df_abatimentos['Valor Abatido'].apply(formatar_moeda_br)

    # --- 3. Aba CONTATOS ---
    contatos = HistoricoContato.objects.all().select_related('credito_origem', 'usuario').values(
        'credito_origem__dni', 'data_contato', 'anotacao', 'usuario__username'
    )
    df_contatos = pd.DataFrame(list(contatos))
    if not df_contatos.empty:
        df_contatos.columns = ['DNI', 'Data Contato', 'Histórico/Anotação', 'Usuário']
        df_contatos['Data Contato'] = pd.to_datetime(df_contatos['Data Contato']).dt.strftime('%d/%m/%Y')

    # --- 4. Gerar o arquivo ---
    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = 'attachment; filename=Relatorio_Creditos_Completo.xlsx'

    with pd.ExcelWriter(response, engine='openpyxl') as writer:
        if not df_creditos.empty:
            df_creditos.to_excel(writer, index=False, sheet_name='Base de Créditos')
        if not df_abatimentos.empty:
            df_abatimentos.to_excel(writer, index=False, sheet_name='Histórico de Abatimentos')
        if not df_contatos.empty:
            df_contatos.to_excel(writer, index=False, sheet_name='Histórico de Contatos')

    return response

@login_required
def listar_creditos(request):
    # ==========================================
    # O SEGREDO ESTÁ AQUI NA PRIMEIRA LINHA
    # ==========================================
    # Trocamos o .all() pelo .exclude()
    # Isso bloqueia as Exceções (CD-) e deixa passar só os DNIs oficiais.
    creditos = CreditoNaoDestinado.objects.exclude(dni__startswith='CD-').order_by('-data')
    
    # Capturando os dados digitados nos filtros (se houver)
    f_dni = request.GET.get('dni', '')
    f_data = request.GET.get('data', '')
    f_cliente = request.GET.get('cliente', '')
    f_empresa = request.GET.get('empresa', '')

    # Aplicando os filtros dinamicamente
    if f_dni:
        creditos = creditos.filter(dni__icontains=f_dni) # icontains = Contém o texto (ignorando maiúsculas/minúsculas)
    if f_data:
        creditos = creditos.filter(data=f_data) # Data exata
    if f_cliente:
        creditos = creditos.filter(cliente__icontains=f_cliente)
    if f_empresa:
        creditos = creditos.filter(empresa__icontains=f_empresa)

    # Passamos os filtros de volta para o HTML para manter os campos preenchidos após recarregar
    context = {
        'creditos': creditos,
        'f_dni': f_dni,
        'f_data': f_data,
        'f_cliente': f_cliente,
        'f_empresa': f_empresa,
    }
    
    return render(request, 'analise/listar_creditos.html', context)