
import pandas as pd
import numpy as np
from datetime import datetime
from decimal import Decimal
from .services import processar_geral_pandas # <--- Certifique-se de importar
from .services import gerar_excel_contas_receber
from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import transaction
import unicodedata
import re
from .forms import UploadSuspensosForm, EditarSuspensoForm
from .processador import processar_suspensos_db
from .models import (
    Paycash, 
    JurCargaSegura, 
    Consolidado_Juridico, 
    Bd_Clientes, 
    BaseGeral,
    ClienteSuspenso
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

@login_required
def dashboard(request):
    # ATENÇÃO: Agora aponta para analise/dashboard.html
    return render(request, 'analise/dashboard.html')

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

from django.utils import timezone # <--- Importe isso no topo se não tiver

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
    # Lógica para o botão de download
    if request.method == 'POST':
        if not BaseGeral.objects.exists():
            messages.error(request, "A base está vazia. Importe o arquivo geral primeiro.")
            return redirect('relatorio_ar')
            
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