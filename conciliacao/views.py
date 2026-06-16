import re
import csv
import json
import io
import xlsxwriter
from django.db.models import Sum
from django.http import JsonResponse
from datetime import datetime, date
from django.http import HttpResponse
import pandas as pd
from decimal import Decimal, InvalidOperation
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import IntegrityError
from django.db.models import Q
from analise.models import BaseGeral 
from .models import ExtratoBancario, MapeamentoDePara, ConciliacaoNota, ExcecaoConciliacao, ClienteEmail, EstabelecimentoCNPJ
# 2. Models financeiros e bases de dados que pertencem ao app 'analise'
from analise.models import ContasReceber, CreditoNaoDestinado
# --- IMPORTANDO O SERVIÇO DO APP ANALISE ---
from analise.services import converter_moeda_br
# ==========================================
# 1. IMPORTAÇÃO DOS EXTRATOS (PANDAS)
# ==========================================
@login_required
def importar_extrato(request):
    if request.method == 'POST':
        empresa = request.POST.get('empresa')
        conta_corrente = request.POST.get('conta_corrente')
        banco = request.POST.get('banco')
        data_extrato_str = request.POST.get('data_extrato')
        arquivo = request.FILES.get('arquivo')

        if not arquivo or not data_extrato_str:
            messages.error(request, "Por favor, preencha a data do movimento e selecione um arquivo.")
            return redirect('importar_extrato')

        try:
            from datetime import datetime
            data_alvo = datetime.strptime(data_extrato_str, '%Y-%m-%d').date()

            if arquivo.name.endswith('.csv'):
                df = pd.read_csv(arquivo, sep=';', on_bad_lines='skip')
            else:
                df = pd.read_excel(arquivo)

            cabecalho_idx = df[df.iloc[:, 0].astype(str).str.contains('Data', case=False, na=False)].index
            if not cabecalho_idx.empty:
                df = df.iloc[cabecalho_idx[0]:]
                df.columns = df.iloc[0]
                df = df[1:]
                df = df.dropna(subset=[df.columns[0]])

            registros_salvos = 0
            registros_duplicados = 0

            # BUSCA A BLACKLIST NO BANCO UMA ÚNICA VEZ PARA FICAR RÁPIDO
            termos_excecao = list(ExcecaoConciliacao.objects.values_list('termo', flat=True))
            # Transforma tudo em maiúsculo para garantir a comparação exata
            termos_excecao = [t.strip().upper() for t in termos_excecao]

            def limpar_moeda(valor_bruto):
                if pd.isna(valor_bruto) or str(valor_bruto).strip() == '':
                    return Decimal('0.00')
                if isinstance(valor_bruto, (int, float)):
                    return Decimal(str(valor_bruto))
                
                v_str = str(valor_bruto).strip()
                if v_str.lower() in ['nan', 'none', '']:
                    return Decimal('0.00')
                
                if v_str.endswith('-'):
                    v_str = '-' + v_str[:-1]
                
                if '.' in v_str and ',' in v_str:
                    v_str = v_str.replace('.', '').replace(',', '.')
                elif ',' in v_str:
                    v_str = v_str.replace(',', '.')
                
                try:
                    return Decimal(v_str)
                except InvalidOperation:
                    return Decimal('0.00')

            for index, row in df.iterrows():
                try:
                    data_transacao = pd.to_datetime(row.iloc[0], dayfirst=True, errors='coerce').date()
                    
                    if pd.isna(data_transacao) or data_transacao != data_alvo:
                        continue
                    
                    if banco == 'ITAU':
                        descricao = str(row.get('Lançamento', '')).strip()
                        razao_social = str(row.get('Razão social', '')).strip()
                        cnpj_cpf = str(row.get('CPF/CNPJ', '')).strip()
                        valor = limpar_moeda(row.get('Valor (R$)'))
                        documento = None
                        
                        if valor <= 0:
                            continue

                    elif banco == 'BRADESCO':
                        descricao = str(row.iloc[1]).strip() # Coluna B
                        documento = str(row.iloc[2]).strip() # Coluna C
                        
                        valor_raw = row.iloc[3] # Coluna D Exclusiva para Crédito
                        valor = limpar_moeda(valor_raw)
                        
                        if valor <= 0:
                            continue
                            
                        mapeamento = MapeamentoDePara.objects.filter(descricao_extrato=descricao).first()
                        if mapeamento:
                            cnpj_cpf = mapeamento.cnpj_cpf
                            razao_social = mapeamento.nome_cliente
                        else:
                            cnpj_cpf = None
                            razao_social = None

                    # 3º FILTRO: VERIFICA SE A DESCRIÇÃO CONTÉM ALGUMA PALAVRA DA BLACKLIST
                    descricao_upper = descricao.upper()
                    ignorar_linha = any(termo in descricao_upper for termo in termos_excecao)
                    
                    if ignorar_linha:
                        continue # Pula a linha e vai para a próxima!

                    # Se passou por todos os filtros (Data, Valor > 0 e Blacklist), salva!
                    ExtratoBancario.objects.create(
                        empresa=empresa,
                        banco=banco,
                        conta_corrente=conta_corrente,
                        data_transacao=data_transacao,
                        descricao=descricao,
                        documento=documento,
                        valor=valor,
                        cnpj_cpf=cnpj_cpf,
                        razao_social=razao_social
                    )
                    registros_salvos += 1

                except IntegrityError:
                    registros_duplicados += 1
                except Exception as e:
                    continue

            messages.success(request, f"Importação do dia {data_alvo.strftime('%d/%m/%Y')} concluída! {registros_salvos} novos créditos salvos.")
            return redirect('importar_extrato')

        except Exception as e:
            messages.error(request, f"Erro ao processar o arquivo: {str(e)}")
            return redirect('importar_extrato')

    return render(request, 'conciliacao/importar_extrato.html')

# ==========================================
# 2. PAINEL DE CONCILIAÇÃO (INTELIGÊNCIA E NOTAS)
# ==========================================
@login_required
def painel_conciliacao(request):
    # ==========================================
    # 1. PROCESSA AS AÇÕES (POST & AJAX)
    # ==========================================
    if request.method == 'POST':
        acao = request.POST.get('acao')
        
        # ==============================================================
        # NOVA AÇÃO: GERAR CRÉDITO DE EXCEÇÃO (Refatorado com Service)
        # ==============================================================
        if acao == 'gerar_credito':
            extrato_id = request.GET.get('extrato_id') or request.POST.get('extrato_id')
            extrato = get_object_or_404(ExtratoBancario, id=extrato_id)

            data_str = request.POST.get('data')
            valor_str = request.POST.get('valor')
            estab = request.POST.get('estab')
            empresa = request.POST.get('empresa')
            cliente = request.POST.get('cliente')

            dni_digitado = request.POST.get('dni', '').strip()

            valor_calculado = converter_moeda_br(valor_str) 

            # --- SEPARAÇÃO LÓGICA (DATASUL vs EXCEÇÃO) ---
            if dni_digitado:
                dni_final = dni_digitado
                mensagem = f"DNI {dni_final} (DataSul) alocada com sucesso e removida dos pendentes!"
            else:
                dni_final = f"CD-{extrato.id}" 
                mensagem = "Exceção (PDD/Trabalhista) alocada com sucesso e enviada para a Gestão de Exceções!"

            # Cria o Crédito na Base de Dados na mesma tabela
            CreditoNaoDestinado.objects.create(
                dni=dni_final,
                data=data_str,
                estab=int(estab) if estab else 0,
                credito=valor_calculado,      # <- Valor exato, sem perder centavos
                saldo_final=valor_calculado,  # <- Saldo inicial igual ao crédito
                cliente=cliente,
                banco=extrato.banco,
                empresa=empresa
            )

            # MUDA O STATUS DO EXTRATO PARA CONCILIADO
            extrato.status = 'CONCILIADO'
            extrato.save()

            # Exibe a mensagem dinâmica baseada na regra e redireciona
            messages.success(request, mensagem)
            return redirect(f"/conciliacao/painel/?extrato_id={extrato.id}")
        
        # =========================================================
        # AÇÃO: IMPORTAR COMPOSIÇÃO DE PAGAMENTO (EXCEL)
        # =========================================================
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' and 'compo_excel' in request.FILES:
            try:
                extrato_id = request.POST.get('extrato_id')
                extrato = get_object_or_404(ExtratoBancario, id=extrato_id)
                arquivo = request.FILES['compo_excel']
                df = pd.read_excel(arquivo)
                
                col_nota = next((c for c in df.columns if 'nota' in str(c).lower() or 'titulo' in str(c).lower() or 'doc' in str(c).lower()), None)
                col_valor = next((c for c in df.columns if 'valor' in str(c).lower() or 'pago' in str(c).lower()), None)
                
                if not col_nota or not col_valor:
                    return JsonResponse({'status': 'erro', 'message': 'O Excel precisa ter um cabeçalho com a palavra "Nota" e outro com "Valor".'})

                cnpj_limpo = re.sub(r'[^0-9]', '', extrato.cnpj_cpf)
                raiz_numeros = cnpj_limpo[:8]
                raiz_formatada = f"{raiz_numeros[:2]}.{raiz_numeros[2:5]}.{raiz_numeros[5:8]}"
                
                query_notas = ContasReceber.objects.filter(
                    Q(cnpj__startswith=raiz_formatada) | Q(cnpj__startswith=raiz_numeros),
                    status='ABERTO'
                )
                
                empresa_ext = str(extrato.empresa).replace('.0', '').strip()
                if empresa_ext and empresa_ext not in ['None', '', '0', '00', 'nan']:
                    query_notas = query_notas.filter(empresa=empresa_ext.zfill(2))
                    
                notas_abertas = list(query_notas)

                mapa_notas_abertas = {str(n.titulo).split('.')[0].strip().lstrip('0'): n.id for n in notas_abertas}

                ids_encontrados = []
                nao_encontrados = []

                for index, row in df.iterrows():
                    nota_excel = str(row[col_nota]).split('.')[0].strip().lstrip('0')
                    valor_excel = float(row[col_valor]) if pd.notnull(row[col_valor]) else 0.0

                    if nota_excel in mapa_notas_abertas:
                        ids_encontrados.append({
                            'id': mapa_notas_abertas[nota_excel],
                            'valor_excel': valor_excel
                        })
                    else:
                        nao_encontrados.append({'nota': nota_excel, 'valor': valor_excel})

                return JsonResponse({
                    'status': 'sucesso',
                    'ids_encontrados': ids_encontrados,
                    'nao_encontrados': nao_encontrados,
                    'qtd_importada': len(df),
                    'qtd_encontrada': len(ids_encontrados)
                })

            except Exception as e:
                return JsonResponse({'status': 'erro', 'message': str(e)})

        # --- AJAX PARA SALVAR OS IMPOSTOS E EMAILS EM TEMPO REAL ---
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            data = json.loads(request.body)
            
            if data.get('acao') == 'salvar_email':
                try:
                    cnpj_alvo = data.get('cnpj')
                    email_digitado = data.get('email')
                    if cnpj_alvo:
                        ClienteEmail.objects.update_or_create(
                            cnpj_busca=cnpj_alvo,
                            defaults={'email': email_digitado}
                        )
                    return JsonResponse({'status': 'sucesso'})
                except Exception as e:
                    return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)
                    
            if data.get('acao') == 'atualizar_impostos':
                try:
                    nota_id_limpo = str(data.get('nota_id')).replace('.', '')
                    nota = get_object_or_404(ContasReceber, id=int(nota_id_limpo))
                    
                    def get_dec(field):
                        val = data.get(field, 0)
                        return Decimal(str(val)) if val else Decimal('0.00')

                    nota.pis = get_dec('pis')
                    nota.cofins = get_dec('cofins')
                    nota.csll = get_dec('csll')
                    nota.irrf = get_dec('irrf')
                    nota.iss = get_dec('iss')
                    nota.inss = get_dec('inss')
                    nota.desconto = get_dec('desconto')
                    nota.abatimento = get_dec('abatimento')
                    nota.multa = get_dec('multa')
                    nota.juros = get_dec('juros')

                    impostos = nota.pis + nota.cofins + nota.csll + nota.irrf + nota.iss + nota.inss
                    descontos = nota.desconto + nota.abatimento
                    acrescimos = nota.multa + nota.juros
                    
                    nota.vl_liquido = nota.vl_bruto - impostos - descontos + acrescimos
                    nota.save()
                    
                    return JsonResponse({'status': 'sucesso', 'novo_saldo': float(nota.vl_liquido)})
                except Exception as e:
                    return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

        # --- POST COMUM (BOTÕES DA TELA) ---
        acao = request.POST.get('acao')
        extrato_id = request.POST.get('extrato_id') or request.GET.get('extrato_id')
        
        # --- AÇÃO 1: VINCULAR CNPJ ---
        if acao == 'vincular_cnpj' and extrato_id:
            extrato = get_object_or_404(ExtratoBancario, id=extrato_id)
            cnpj_digitado = request.POST.get('cnpj', '').strip()
            cnpj_numeros = re.sub(r'[^0-9]', '', cnpj_digitado)
            
            if cnpj_numeros:
                if len(cnpj_numeros) == 14:
                    cnpj_formatado = f"{cnpj_numeros[:2]}.{cnpj_numeros[2:5]}.{cnpj_numeros[5:8]}/{cnpj_numeros[8:12]}-{cnpj_numeros[12:]}"
                elif len(cnpj_numeros) == 8:
                    cnpj_formatado = f"{cnpj_numeros[:2]}.{cnpj_numeros[2:5]}.{cnpj_numeros[5:8]}"
                else:
                    cnpj_formatado = cnpj_digitado
                
                extrato.cnpj_cpf = cnpj_formatado
                extrato.save()
                
                MapeamentoDePara.objects.update_or_create(
                    descricao_extrato=extrato.descricao,
                    defaults={'cnpj_cpf': cnpj_formatado}
                )
                ExtratoBancario.objects.filter(descricao=extrato.descricao).update(cnpj_cpf=cnpj_formatado)
                messages.success(request, "CNPJ vinculado com sucesso! O sistema já aprendeu essa regra.")
            return redirect(f"{request.path}?extrato_id={extrato_id}")

        # --- AÇÃO 2: CONCILIAR MÚLTIPLAS NOTAS ---
        elif acao == 'conciliar_multiplas' and extrato_id:
            notas_ids = request.POST.getlist('notas_selecionadas')
            extrato = get_object_or_404(ExtratoBancario, id=extrato_id)

            notas_conciliadas_qtd = 0
            for nota_id_bruto in notas_ids:
                nota_id_limpo = str(nota_id_bruto).replace('.', '')
                nota = get_object_or_404(ContasReceber, id=int(nota_id_limpo))
                
                if not ConciliacaoNota.objects.filter(extrato=extrato, nota=nota).exists():
                    ConciliacaoNota.objects.create(extrato=extrato, nota=nota, valor_pago=nota.vl_liquido)
                    nota.status = 'CONCILIADO'
                    nota.save()
                    notas_conciliadas_qtd += 1
            
            if notas_conciliadas_qtd > 0:
                total_usado = ConciliacaoNota.objects.filter(extrato=extrato).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
                if total_usado >= extrato.valor:
                    extrato.status = 'CONCILIADO'
                else:
                    extrato.status = 'PENDENTE'
                extrato.save()
                messages.success(request, f"Sucesso! {notas_conciliadas_qtd} nota(s) conciliada(s).")
            else:
                messages.warning(request, "Nenhuma nota foi selecionada.")
            return redirect(f"{request.path}?extrato_id={extrato_id}")

        # --- AÇÃO 3: DESFAZER CONCILIAÇÃO ---
        elif acao == 'desfazer_conciliacao' and extrato_id:
            extrato = get_object_or_404(ExtratoBancario, id=extrato_id)
            relacoes = ConciliacaoNota.objects.filter(extrato=extrato)
            for rel in relacoes:
                nota = rel.nota
                nota.status = 'ABERTO'
                nota.save()
            relacoes.delete()
            extrato.status = 'PENDENTE'
            extrato.save()
            messages.success(request, "Conciliação desfeita! O depósito e as notas voltaram para a fila.")
            return redirect(f"{request.path}?extrato_id={extrato_id}")

    # ==========================================
    # 2. CARREGAMENTO DA TELA (GET)
    # ==========================================
    extrato_id = request.GET.get('extrato_id')
    filtro_banco = request.GET.get('filtro_banco', '')
    filtro_empresa = request.GET.get('filtro_empresa', '')
    
    # --- Mantendo apenas PENDENTES no painel lateral ---
    bancos_disponiveis = ExtratoBancario.objects.filter(
        status='PENDENTE', valor__gt=0
    ).values_list('banco', flat=True).distinct().order_by('banco')

    empresas_disponiveis = ExtratoBancario.objects.filter(
        status='PENDENTE', valor__gt=0
    ).exclude(empresa__isnull=True).exclude(empresa='').values_list('empresa', flat=True).distinct().order_by('empresa')
    
    query_extratos = ExtratoBancario.objects.filter(
        status='PENDENTE', valor__gt=0
    )
        
    if filtro_banco:
        query_extratos = query_extratos.filter(banco=filtro_banco)

    if filtro_empresa:
        query_extratos = query_extratos.filter(empresa=filtro_empresa)
        
    extratos_pendentes_qs = query_extratos.order_by('data_transacao')

    extratos_pendentes = []
    for ex in extratos_pendentes_qs:
        total_usado = ConciliacaoNota.objects.filter(extrato=ex).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
        ex.saldo_restante = ex.valor - total_usado
        ex.is_parcial = total_usado > 0
        
        if ex.saldo_restante > 0:
            extratos_pendentes.append(ex)

    extrato_selecionado = None
    notas_sugeridas = []
    notas_conciliadas = []
    
    if extrato_id:
        extrato_selecionado = get_object_or_404(ExtratoBancario, id=extrato_id)
        
        total_usado_sel = ConciliacaoNota.objects.filter(extrato=extrato_selecionado).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
        extrato_selecionado.saldo_restante = extrato_selecionado.valor - total_usado_sel
        
        if extrato_selecionado.status == 'PENDENTE' and extrato_selecionado.cnpj_cpf:
            cnpj_limpo = re.sub(r'[^0-9]', '', extrato_selecionado.cnpj_cpf)
            if len(cnpj_limpo) >= 8:
                raiz_numeros = cnpj_limpo[:8]
                raiz_formatada = f"{raiz_numeros[:2]}.{raiz_numeros[2:5]}.{raiz_numeros[5:8]}"
                
                query_notas = ContasReceber.objects.filter(
                    Q(cnpj__startswith=raiz_formatada) | Q(cnpj__startswith=raiz_numeros),
                    status='ABERTO'
                )
                
                empresa_ext = str(extrato_selecionado.empresa).replace('.0', '').strip()
                if empresa_ext and empresa_ext not in ['None', '', '0', '00', 'nan']:
                    query_notas = query_notas.filter(empresa=empresa_ext.zfill(2))
                    
                notas_sugeridas = list(query_notas.order_by('dt_vencto_atual'))

            for nota in notas_sugeridas:
                nota.saldo_real_calculado = nota.vl_liquido
                nota.match_exato = (extrato_selecionado.saldo_restante == nota.vl_liquido)
                
        elif extrato_selecionado.status == 'CONCILIADO':
            relacoes = ConciliacaoNota.objects.filter(extrato=extrato_selecionado).select_related('nota')
            notas_conciliadas = [rel.nota for rel in relacoes]

    # === NOVA LÓGICA DO E-MAIL ===
    email_salvo = ""
    dados_estabelecimentos = []

    if extrato_selecionado and extrato_selecionado.cnpj_cpf:
        # 1. Puxa o e-mail se já existir para este CNPJ
        obj_email = ClienteEmail.objects.filter(cnpj_busca=extrato_selecionado.cnpj_cpf).first()
        if obj_email:
            email_salvo = obj_email.email
        
        # 2. Puxa os CNPJs dos estabelecimentos listados na grade (Join manual)
        if notas_sugeridas:
            estabs_na_tela = set()
            for n in notas_sugeridas:
                if n.estabelecimento:
                    try:
                        # A MÁGICA AQUI: Converte "404.0", "0404" ou " 404 " em número inteiro puro: 404
                        val_estab = int(float(str(n.estabelecimento).strip()))
                        estabs_na_tela.add(val_estab)
                    except (ValueError, TypeError):
                        pass # Ignora se vier lixo ou vazio
            
            if estabs_na_tela:
                # Agora o banco vai achar perfeitamente, pois os tipos batem (Inteiro com Inteiro)
                lista_bd = EstabelecimentoCNPJ.objects.filter(estab__in=estabs_na_tela)
                for item in lista_bd:
                    dados_estabelecimentos.append({
                        'estab': item.estab,
                        'empresa': item.nome_empresa,
                        'cnpj': item.cnpj
                    })

    context = {
        'extratos_pendentes': extratos_pendentes,
        'extrato_selecionado': extrato_selecionado,
        'notas_sugeridas': notas_sugeridas,
        'notas_conciliadas': notas_conciliadas,
        'bancos_disponiveis': bancos_disponiveis,
        'filtro_banco': filtro_banco,
        'empresas_disponiveis': empresas_disponiveis,
        'filtro_empresa': filtro_empresa,
        'email_salvo': email_salvo,
        'dados_estabelecimentos': json.dumps(dados_estabelecimentos),
    }
    return render(request, 'conciliacao/painel.html', context)
# ==============================================================
# 1. FUNÇÃO DE BAIXAR O LOTE COMPLETO (TELA GESTÃO CONCILIADOS)
# ==============================================================
@login_required
def exportar_lote_datasul(request, extrato_id=None):
    relacoes = ConciliacaoNota.objects.filter(nota__status='CONCILIADO').select_related('extrato', 'nota').order_by('extrato__data_transacao')
    
    if not relacoes.exists():
        messages.warning(request, "Nenhuma nota pendente de exportação encontrada.")
        return redirect('gestao_conciliados')

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Lote Datasul')
    
    # FORMATOS DO EXCEL
    fmt_texto = workbook.add_format({'num_format': '@'}) 
    fmt_numero = workbook.add_format({'num_format': '0.00'}) # Formato de número com 2 casas decimais
    
    cabecalho = [
        'Estabelec', 'Espécie', 'Série', 'Título', 'Parcela', 
        'Dt.Emissão Orig', 'Dt.Vencto Atual', 'Empresa', 'CNPJ', 
        'Nome Abrev', 'Vl.Bruto', 'PIS', 'Cofins', 'CSLL', 'IRRF', 
        'ISS', 'INSS', 'Desconto', 'Abatimento', 'Multa', 'Juros', 
        'Vl.líquido', 'Carteira'
    ]
    
    for col_num, nome_col in enumerate(cabecalho):
        worksheet.write(0, col_num, nome_col)
    
    def date_to_excel(dt):
        if not dt: return ''
        if isinstance(dt, str):
            try:
                dt = datetime.strptime(dt, '%Y-%m-%d').date()
            except Exception:
                return dt
        d = dt.date() if hasattr(dt, 'date') else dt
        return (d - date(1899, 12, 30)).days

    def to_float(v):
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0
    def to_int(v):
        try:
            # Transforma em float primeiro para evitar erros se o número vier como "1234.0"
            return int(float(str(v).strip()))
        except (ValueError, TypeError):
            # Se por acaso vier uma letra no título, devolve como texto para não perder a informação
            return str(v).strip()

    notas_atualizadas = []
    for row_num, rel in enumerate(relacoes, 1):
        nota = rel.nota
        
        estab_str = str(nota.estabelecimento).replace('.0', '').strip()
        parcela_str = str(nota.parcela).replace('.0', '').strip().zfill(2)
        empresa_str = str(nota.empresa).replace('.0', '').strip().zfill(2)
        carteira_str = str(nota.carteira).replace('.0', '').strip()
        
        worksheet.write(row_num, 0, estab_str, fmt_texto)
        worksheet.write(row_num, 1, str(nota.especie).strip())
        worksheet.write(row_num, 2, str(nota.serie).strip())
        worksheet.write(row_num, 3, to_int(nota.titulo))
        worksheet.write(row_num, 4, parcela_str, fmt_texto)
        worksheet.write(row_num, 5, date_to_excel(nota.dt_emissao_orig))
        worksheet.write(row_num, 6, date_to_excel(nota.dt_vencto_atual))
        worksheet.write(row_num, 7, empresa_str, fmt_texto)
        worksheet.write(row_num, 8, str(nota.cnpj).strip())
        worksheet.write(row_num, 9, str(nota.nome_abrev).strip())
        
        # Agora são gravados como NÚMEROS reais para o Excel
        worksheet.write_number(row_num, 10, to_float(nota.vl_bruto), fmt_numero)
        worksheet.write_number(row_num, 11, to_float(nota.pis), fmt_numero)
        worksheet.write_number(row_num, 12, to_float(nota.cofins), fmt_numero)
        worksheet.write_number(row_num, 13, to_float(nota.csll), fmt_numero)
        worksheet.write_number(row_num, 14, to_float(nota.irrf), fmt_numero)
        worksheet.write_number(row_num, 15, to_float(nota.iss), fmt_numero)
        worksheet.write_number(row_num, 16, to_float(nota.inss), fmt_numero)
        worksheet.write_number(row_num, 17, to_float(nota.desconto), fmt_numero)
        worksheet.write_number(row_num, 18, to_float(nota.abatimento), fmt_numero)
        worksheet.write_number(row_num, 19, to_float(nota.multa), fmt_numero)
        worksheet.write_number(row_num, 20, to_float(nota.juros), fmt_numero)
        worksheet.write_number(row_num, 21, to_float(nota.vl_liquido), fmt_numero)
        
        worksheet.write(row_num, 22, carteira_str, fmt_texto)
        
        nota.status = 'EXPORTADO'
        notas_atualizadas.append(nota)
        
    ContasReceber.objects.bulk_update(notas_atualizadas, ['status'])
    
    workbook.close()
    output.seek(0)
    
    nome_arquivo = f'lote_datasul_{datetime.now().strftime("%Y%m%d_%H%M")}.xlsx'
    response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    
    messages.success(request, f"Lote Excel gerado com sucesso! {len(notas_atualizadas)} notas baixadas.")
    return response


    extrato = get_object_or_404(ExtratoBancario, id=extrato_id)
    relacoes = ConciliacaoNota.objects.filter(extrato=extrato).select_related('nota')
    
    if not relacoes.exists():
        messages.warning(request, "Nenhuma nota encontrada para este depósito.")
        return redirect(f"/conciliacao/painel/?extrato_id={extrato_id}")

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Lote Datasul')
    
    fmt_texto = workbook.add_format({'num_format': '@'}) 
    fmt_numero = workbook.add_format({'num_format': '0.00'}) 
    
    cabecalho = [
        'Estabelec', 'Espécie', 'Série', 'Título', 'Parcela', 
        'Dt.Emissão Orig', 'Dt.Vencto Atual', 'Empresa', 'CNPJ', 
        'Nome Abrev', 'Vl.Bruto', 'PIS', 'Cofins', 'CSLL', 'IRRF', 
        'ISS', 'INSS', 'Desconto', 'Abatimento', 'Multa', 'Juros', 
        'Vl.líquido', 'Carteira'
    ]
    
    for col_num, nome_col in enumerate(cabecalho):
        worksheet.write(0, col_num, nome_col)
    
    def date_to_excel(dt):
        if not dt: return ''
        if isinstance(dt, str):
            try:
                dt = datetime.strptime(dt, '%Y-%m-%d').date()
            except Exception:
                return dt
        d = dt.date() if hasattr(dt, 'date') else dt
        return (d - date(1899, 12, 30)).days

    def to_float(v):
        try:
            return float(v)
        except (ValueError, TypeError):
            return 0.0

    for row_num, rel in enumerate(relacoes, 1):
        nota = rel.nota
        
        estab_str = str(nota.estabelecimento).replace('.0', '').strip()
        parcela_str = str(nota.parcela).replace('.0', '').strip().zfill(2)
        empresa_str = str(nota.empresa).replace('.0', '').strip().zfill(2)
        carteira_str = str(nota.carteira).replace('.0', '').strip()
        
        worksheet.write(row_num, 0, estab_str, fmt_texto)
        worksheet.write(row_num, 1, str(nota.especie).strip())
        worksheet.write(row_num, 2, str(nota.serie).strip())
        worksheet.write(row_num, 3, str(nota.titulo).strip())
        worksheet.write(row_num, 4, parcela_str, fmt_texto)
        worksheet.write(row_num, 5, date_to_excel(nota.dt_emissao_orig))
        worksheet.write(row_num, 6, date_to_excel(nota.dt_vencto_atual))
        worksheet.write(row_num, 7, empresa_str, fmt_texto)
        worksheet.write(row_num, 8, str(nota.cnpj).strip())
        worksheet.write(row_num, 9, str(nota.nome_abrev).strip())
        
        worksheet.write_number(row_num, 10, to_float(nota.vl_bruto), fmt_numero)
        worksheet.write_number(row_num, 11, to_float(nota.pis), fmt_numero)
        worksheet.write_number(row_num, 12, to_float(nota.cofins), fmt_numero)
        worksheet.write_number(row_num, 13, to_float(nota.csll), fmt_numero)
        worksheet.write_number(row_num, 14, to_float(nota.irrf), fmt_numero)
        worksheet.write_number(row_num, 15, to_float(nota.iss), fmt_numero)
        worksheet.write_number(row_num, 16, to_float(nota.inss), fmt_numero)
        worksheet.write_number(row_num, 17, to_float(nota.desconto), fmt_numero)
        worksheet.write_number(row_num, 18, to_float(nota.abatimento), fmt_numero)
        worksheet.write_number(row_num, 19, to_float(nota.multa), fmt_numero)
        worksheet.write_number(row_num, 20, to_float(nota.juros), fmt_numero)
        worksheet.write_number(row_num, 21, to_float(nota.vl_liquido), fmt_numero)
        
        worksheet.write(row_num, 22, carteira_str, fmt_texto)
        
    workbook.close()
    output.seek(0)
    
    dt_str = extrato.data_transacao.strftime("%d%m%Y") if extrato.data_transacao else datetime.now().strftime("%d%m%Y")
    nome_arquivo = f"{extrato.id}_{extrato.banco}_{dt_str}.xlsx"
    
    response = HttpResponse(output, content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
    
    return response

@login_required
def gestao_conciliados(request):
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'desconciliar_nota':
            relacao_id = request.POST.get('relacao_id')
            rel = get_object_or_404(ConciliacaoNota, id=relacao_id)
            extrato = rel.extrato
            nota = rel.nota

            nota.status = 'ABERTO'
            nota.save()
            rel.delete()

            total_usado = ConciliacaoNota.objects.filter(extrato=extrato).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
            if total_usado < extrato.valor:
                extrato.status = 'PENDENTE'
            extrato.save()

            messages.success(request, f"Nota {nota.titulo} desfeita! Depósito liberado parcialmente.")
            return redirect('gestao_conciliados')

    extratos_ids = ConciliacaoNota.objects.filter(nota__status='CONCILIADO').values_list('extrato_id', flat=True).distinct()
    extratos = ExtratoBancario.objects.filter(id__in=extratos_ids).order_by('-data_transacao')

    tabela_dados = []
    for extrato in extratos:
        relacoes = ConciliacaoNota.objects.filter(extrato=extrato, nota__status='CONCILIADO').select_related('nota')
        if relacoes.exists():
            total_usado = sum(rel.valor_pago for rel in relacoes)
            total_geral_extrato = ConciliacaoNota.objects.filter(extrato=extrato).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
            saldo_restante = extrato.valor - total_geral_extrato

            tabela_dados.append({
                'extrato': extrato,
                'relacoes': relacoes,
                'total_usado': total_usado,
                'saldo_restante': saldo_restante,
            })

    return render(request, 'conciliacao/gestao_conciliados.html', {'tabela_dados': tabela_dados})

@login_required
def notas_baixadas(request):

    # Permite desfazer mesmo se já foi baixado (útil caso tenha baixado errado)
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'desconciliar_nota':
            relacao_id = request.POST.get('relacao_id')
            rel = get_object_or_404(ConciliacaoNota, id=relacao_id)
            extrato = rel.extrato
            nota = rel.nota

            nota.status = 'ABERTO'
            nota.save()
            rel.delete()

            total_usado = ConciliacaoNota.objects.filter(extrato=extrato).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
            if total_usado < extrato.valor:
                extrato.status = 'PENDENTE'
            extrato.save()

            messages.success(request, f"Nota {nota.titulo} desfeita com sucesso! Ela voltou para a fila de Pendentes.")
            return redirect('notas_baixadas')

    # Filtros recebidos do formulário
    filtro_data = request.GET.get('data', '')
    filtro_empresa = request.GET.get('empresa', '')
    filtro_banco = request.GET.get('banco', '')

    # Puxa apenas notas EXPORTADAS
    relacoes_query = ConciliacaoNota.objects.filter(nota__status='EXPORTADO').select_related('extrato', 'nota')

    # Aplica os filtros
    if filtro_data:
        relacoes_query = relacoes_query.filter(extrato__data_transacao=filtro_data)
    if filtro_empresa:
        # A empresa no banco está em formato numérico 01, 02...
        relacoes_query = relacoes_query.filter(nota__empresa=filtro_empresa)
    if filtro_banco:
        relacoes_query = relacoes_query.filter(extrato__banco=filtro_banco)

    extratos_ids = relacoes_query.values_list('extrato_id', flat=True).distinct()
    extratos = ExtratoBancario.objects.filter(id__in=extratos_ids).order_by('-data_transacao')

    tabela_dados = []
    for extrato in extratos:
        relacoes = relacoes_query.filter(extrato=extrato)
        if relacoes.exists():
            total_usado = sum(rel.valor_pago for rel in relacoes)
            tabela_dados.append({
                'extrato': extrato,
                'relacoes': relacoes,
                'total_usado': total_usado,
            })

    # Listas para popular os Dropdowns de Filtro
    bancos_disp = ExtratoBancario.objects.filter(id__in=ConciliacaoNota.objects.filter(nota__status='EXPORTADO').values('extrato_id')).values_list('banco', flat=True).distinct()
    empresas_disp = ContasReceber.objects.filter(status='EXPORTADO').values_list('empresa', flat=True).distinct()

    context = {
        'tabela_dados': tabela_dados,
        'bancos_disponiveis': bancos_disp,
        'empresas_disponiveis': empresas_disp,
        'filtro_data': filtro_data,
        'filtro_empresa': filtro_empresa,
        'filtro_banco': filtro_banco,
    }
    return render(request, 'conciliacao/notas_baixadas.html', context)

@login_required
def editar_credito(request, dni):
    if request.method == 'POST':
        credito = get_object_or_404(CreditoNaoDestinado, dni=dni)
        credito.estab = request.POST.get('estab')
        credito.empresa = request.POST.get('empresa')
        credito.cliente = request.POST.get('cliente')
        credito.save()
        messages.success(request, f"Crédito {dni} atualizado com sucesso!")
    return redirect('gestao_conciliados') # Mude para o nome correto da sua URL de notas baixadas

@login_required
def cancelar_credito(request, dni):

    if request.method == 'POST':
        credito = get_object_or_404(CreditoNaoDestinado, dni=dni)
        
        # Inteligência Artificial: Tentar encontrar o Extrato original para o devolver a PENDENTE!
        extrato_revertido = False
        if credito.dni.startswith('CD-'):
            extrato_id = credito.dni.split('-')[1]
            extrato = ExtratoBancario.objects.filter(id=extrato_id).first()
            if extrato:
                extrato.status = 'PENDENTE'
                extrato.save()
                extrato_revertido = True
        
        # Se o utilizador digitou um DNI manual, procura o extrato pelo valor, banco e data
        if not extrato_revertido:
            extrato = ExtratoBancario.objects.filter(
                banco=credito.banco, 
                data_transacao=credito.data, 
                saldo_restante=credito.credito,
                status='CONCILIADO'
            ).first()
            if extrato:
                extrato.status = 'PENDENTE'
                extrato.save()

        credito.delete()
        messages.warning(request, f"Crédito {dni} apagado. O depósito voltou para PENDENTE no Painel.")
        
    return redirect('gestao_conciliados')

@login_required
def painel_creditos_nao_destinados(request):
    # ==========================================
    # AÇÃO POST: CANCELAR A EXCEÇÃO E DEVOLVER
    # ==========================================
    if request.method == 'POST':
        acao = request.POST.get('acao')
        if acao == 'cancelar_credito':
            # Como a Chave Primária é o DNI, pegamos ele do formulário
            credito_dni = request.POST.get('credito_id')
            credito = get_object_or_404(CreditoNaoDestinado, dni=credito_dni)
            
            # Devolve para o painel de conciliação usando a regra do prefixo CD-
            if credito.dni.startswith('CD-'):
                try:
                    ext_id = int(credito.dni.replace('CD-', ''))
                    extrato = ExtratoBancario.objects.filter(id=ext_id).first()
                    if extrato:
                        extrato.status = 'PENDENTE'
                        extrato.save()
                        messages.success(request, "Exceção cancelada! O depósito voltou para o Painel de Conciliação.")
                except ValueError:
                    messages.warning(request, "Exceção excluída, mas não foi possível retornar o extrato.")
            else:
                messages.warning(request, "Crédito excluído, mas sem vínculo rastreável para retorno.")

            credito.delete()
            return redirect('creditos_nao_destinados')

    # ==========================================
    # CARREGAMENTO DA TELA (GET) - O FILTRO MÁGICO
    # ==========================================
    # O segredo está aqui: filter(dni__startswith='CD-')
    # Isso garante que NENHUMA DNI do DataSul apareça nesta tela!
    excecoes = CreditoNaoDestinado.objects.filter(dni__startswith='CD-').order_by('-data')
    
    context = {
        'creditos': excecoes
    }
    return render(request, 'conciliacao/creditos_nao_destinados.html', context)