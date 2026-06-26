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
from django.db.models import Q, Sum
from analise.models import BaseGeral 
from .models import ExtratoBancario, MapeamentoDePara, ConciliacaoNota, ExcecaoConciliacao, ClienteEmail, EstabelecimentoCNPJ, SugestaoAutomacao
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
            import re  # Importação necessária para a limpeza avançada de strings
            
            data_alvo = datetime.strptime(data_extrato_str, '%Y-%m-%d').date()

            # 1. BLINDAGEM DO ARQUIVO CSV
            if arquivo.name.endswith('.csv'):
                df = pd.read_csv(arquivo, sep=';', on_bad_lines='skip')
                # Se o Pandas não separou as colunas (criou só 1), o arquivo usa vírgula!
                if len(df.columns) <= 1:
                    arquivo.seek(0)
                    df = pd.read_csv(arquivo, sep=',', on_bad_lines='skip')
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

            # 2. BLINDAGEM CIRÚRGICA DE MOEDA
            def limpar_moeda(valor_bruto):
                if pd.isna(valor_bruto):
                    return Decimal('0.00')
                if isinstance(valor_bruto, (int, float)):
                    return Decimal(str(valor_bruto))
                
                v_str = str(valor_bruto).strip()
                
                # O PULO DO GATO: Remove "R$", espaços invisíveis, letras e mantém só os números e delimitadores!
                v_str = re.sub(r'[^\d\.,\-]', '', v_str)
                
                if not v_str or v_str == '-':
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
                        # Verifica se as colunas existem antes de chamar o iloc para evitar IndexError
                        descricao = str(row.iloc[1]).strip() if len(row) > 1 else ''
                        documento = str(row.iloc[2]).strip() if len(row) > 2 else ''
                        
                        # A coluna 3 (D) é onde o Bradesco costuma pôr o Crédito
                        valor_raw = row.iloc[3] if len(row) > 3 else '0'
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
        
        # Recupera os filtros atuais (pode vir do formulário POST ou da URL GET)
        f_banco = request.POST.get('filtro_banco', '') or request.GET.get('filtro_banco', '')
        f_empresa = request.POST.get('filtro_empresa', '') or request.GET.get('filtro_empresa', '')
        f_data = request.POST.get('filtro_data', '') or request.GET.get('filtro_data', '')
        
        # Cria a string com os filtros para plugar nas URLs de redirecionamento mantendo a tela do usuário
        query_filtros = f"&filtro_banco={f_banco}&filtro_empresa={f_empresa}&filtro_data={f_data}"
        
        # ==============================================================
        # AÇÃO: GERAR CRÉDITO DE EXCEÇÃO (PDD / DNI)
        # ==============================================================
        if acao == 'gerar_credito':
            extrato_id = request.GET.get('extrato_id') or request.POST.get('extrato_id')
            if extrato_id: 
                extrato_id = str(extrato_id).replace('.', '')
                
            extrato = get_object_or_404(ExtratoBancario, id=int(extrato_id))

            data_str = request.POST.get('data')
            valor_str = request.POST.get('valor')
            estab = request.POST.get('estab')
            empresa = request.POST.get('empresa')
            cliente = request.POST.get('cliente')

            dni_digitado = request.POST.get('dni', '').strip()
            obs_digitada = request.POST.get('observacao', '').strip()

            valor_calculado = converter_moeda_br(valor_str) 

            # SEPARAÇÃO LÓGICA (DATASUL vs EXCEÇÃO)
            if dni_digitado:
                dni_final = dni_digitado
                mensagem = f"DNI {dni_final} (DataSul) alocada com sucesso e removida dos pendentes!"
            else:
                dni_final = f"CD-{extrato.id}" 
                mensagem = "Exceção (PDD/Trabalhista) alocada com sucesso e enviada para a Gestão de Exceções!"

            # Cria o Crédito na Base de Dados
            CreditoNaoDestinado.objects.create(
                dni=dni_final,
                data=data_str,
                estab=int(estab) if estab else 0,
                credito=valor_calculado,      
                saldo_final=valor_calculado,  
                cliente=cliente,
                banco=extrato.banco,
                empresa=empresa,
                observacao=obs_digitada
            )

            extrato.status = 'CONCILIADO'
            extrato.save()

            messages.success(request, mensagem)
            return redirect(f"/conciliacao/painel/?extrato_id={extrato.id}{query_filtros}")
        
        # =========================================================
        # AÇÃO: IMPORTAR COMPOSIÇÃO DE PAGAMENTO (EXCEL)
        # =========================================================
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' and 'compo_excel' in request.FILES:
            try:
                extrato_id = request.POST.get('extrato_id')
                if extrato_id: 
                    extrato_id = str(extrato_id).replace('.', '')
                    
                extrato = get_object_or_404(ExtratoBancario, id=int(extrato_id))
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

        # =========================================================
        # AÇÕES AJAX: SALVAR EMAILS, ATUALIZAR IMPOSTOS E RESUMO VERDES
        # =========================================================
        if request.headers.get('x-requested-with') == 'XMLHttpRequest' or request.content_type == 'application/json':
            data = json.loads(request.body)
            
            
            # --- AJAX: CALCULAR RESUMO DE TODOS OS VERDES (GLOBAL) ---
            if data.get('acao') == 'resumo_verdes_cnpj':
                try:
                    # Busca TODOS os depósitos verdes do sistema, não importa o CNPJ!
                    extratos_verdes = ExtratoBancario.objects.filter(status='PENDENTE', cor_automacao='VERDE')
                    
                    if not extratos_verdes.exists():
                        return JsonResponse({'status': 'erro', 'message': 'Nenhum depósito com a cor VERDE encontrado no momento.'})
                        
                    total_depositos = sum(ex.valor for ex in extratos_verdes)
                    
                    sugestoes = SugestaoAutomacao.objects.filter(extrato__in=extratos_verdes)
                    total_notas = sum(sug.valor_sugerido for sug in sugestoes)
                    
                    return JsonResponse({
                        'status': 'sucesso',
                        'qtd_depositos': extratos_verdes.count(),
                        'total_depositos': float(total_depositos),
                        'total_notas': float(total_notas)
                    })
                except Exception as e:
                    return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)
            
            # --- AJAX: SALVAR EMAIL ---
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
                    
            # --- AJAX: ATUALIZAR IMPOSTOS (COM BLINDAGEM DE DECIMAIS) ---
            if data.get('acao') == 'atualizar_impostos':
                try:
                    nota_id_bruto = data.get('nota_id')
                    if not nota_id_bruto:
                        return JsonResponse({'status': 'erro', 'message': 'ID da nota não encontrado.'}, status=400)

                    nota_id_limpo = str(nota_id_bruto).replace('.', '')
                    nota = get_object_or_404(ContasReceber, id=int(nota_id_limpo))
                    
                    def get_dec(field):
                        val = data.get(field, '0')
                        if val is None or str(val).strip() == '':
                            return Decimal('0.00')
                        # MÁGICA: Garante que se o JS mandar vírgula, o Python converte para ponto sem quebrar!
                        val = str(val).replace(',', '.')
                        return Decimal(val)

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
                    
                    variacao_percentual = 0.0
                    if nota.vl_bruto and nota.vl_bruto > 0:
                        variacao_percentual = float((nota.vl_liquido / nota.vl_bruto) * 100 - 100)
                    
                    return JsonResponse({
                        'status': 'sucesso', 
                        'novo_saldo': float(nota.vl_liquido),
                        'variacao': variacao_percentual
                    })
                except Exception as e:
                    print(f"ERRO AO SALVAR IMPOSTOS: {str(e)}") # Printa o erro no terminal para debug
                    return JsonResponse({'status': 'erro', 'message': str(e)}, status=400)

        # =========================================================
        # AÇÕES DOS BOTÕES COMUNS DA TELA
        # =========================================================
        acao = request.POST.get('acao')
        extrato_id = request.POST.get('extrato_id') or request.GET.get('extrato_id')
        if extrato_id: 
            extrato_id = str(extrato_id).replace('.', '')
            
        # --- AÇÃO 1: VINCULAR CNPJ MANUALMENTE ---
        if acao == 'vincular_cnpj' and extrato_id:
            extrato = get_object_or_404(ExtratoBancario, id=int(extrato_id))
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
            return redirect(f"{request.path}?extrato_id={extrato_id}{query_filtros}")

       # --- AÇÃO 2: EFETIVAR TODOS OS VERDES DO SISTEMA (EM LOTE GLOBAL) ---
        elif acao == 'efetivar_verdes_cnpj':
            # Pega TODOS os depósitos verdes pendentes do banco de dados
            extratos_pendentes_verdes = ExtratoBancario.objects.filter(status='PENDENTE', cor_automacao='VERDE')
            
            qtd_conciliados = 0
            for ex in extratos_pendentes_verdes:
                sugestoes = SugestaoAutomacao.objects.filter(extrato=ex)
                if sugestoes.exists():
                    for sug in sugestoes:
                        nota = sug.nota
                        if nota.status == 'ABERTO': 
                            ConciliacaoNota.objects.create(extrato=ex, nota=nota, valor_pago=sug.valor_sugerido)
                            nota.status = 'CONCILIADO'
                            nota.save()
                    
                    ex.status = 'CONCILIADO'
                    ex.save()
                    qtd_conciliados += 1
            
            if qtd_conciliados > 0:
                messages.success(request, f"🚀 Limpeza concluída! {qtd_conciliados} depósitos automáticos (Verdes) foram conciliados com sucesso.")
            else:
                messages.warning(request, "Nenhum depósito verde pendente encontrado para efetivar.")
                
            return redirect(f"{request.path}?{query_filtros}")

        # --- AÇÃO 3: CONCILIAR MÚLTIPLAS NOTAS (E MÚLTIPLOS DEPÓSITOS) ---
        elif acao == 'conciliar_multiplas':
            # 1. Pega as listas de tudo o que foi ticado na tela
            notas_ids = request.POST.getlist('notas_selecionadas')
            extratos_ids = request.POST.getlist('extratos_selecionados')
            
            # Fallback de segurança: se o HTML5 não enviar os múltiplos, pega o da URL
            if not extratos_ids and extrato_id:
                extratos_ids = [extrato_id]

            if not extratos_ids or not notas_ids:
                messages.warning(request, "Selecione pelo menos um depósito e uma nota para conciliar.")
                return redirect(f"{request.path}?extrato_id={extrato_id}{query_filtros}")

            # 2. Busca no banco todos os depósitos e notas envolvidos na transação
            extratos = ExtratoBancario.objects.filter(id__in=[int(str(eid).replace('.', '')) for eid in extratos_ids]).order_by('data_transacao')
            notas = ContasReceber.objects.filter(id__in=[int(str(nid).replace('.', '')) for nid in notas_ids]).order_by('dt_vencto_atual')

            # 3. Cria um controle de saldo em memória para os depósitos selecionados
            extratos_saldo = []
            for ex in extratos:
                total_usado = ConciliacaoNota.objects.filter(extrato=ex).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
                saldo = ex.valor - total_usado
                extratos_saldo.append({'obj': ex, 'saldo': saldo})

            notas_conciliadas_qtd = 0

            # 4. ALGORITMO DE DISTRIBUIÇÃO
            # Varre cada nota e vai "pagando" com os saldos dos depósitos disponíveis
            for nota in notas:
                saldo_nota = nota.vl_liquido
                
                for ex_dict in extratos_saldo:
                    if saldo_nota <= Decimal('0.00'):
                        break  # Esta nota já foi totalmente paga, vai para a próxima
                        
                    if ex_dict['saldo'] > Decimal('0.00'):
                        # Pega o menor valor entre o que a nota precisa e o que o depósito tem
                        valor_a_usar = min(saldo_nota, ex_dict['saldo'])
                        
                        if valor_a_usar > 0:
                            # Cria a relação (o Match) no banco de dados
                            ConciliacaoNota.objects.create(
                                extrato=ex_dict['obj'], 
                                nota=nota, 
                                valor_pago=valor_a_usar
                            )
                            
                            # Abate o valor usado da nota e do depósito atual
                            saldo_nota -= valor_a_usar
                            ex_dict['saldo'] -= valor_a_usar
                
                # Concluído o loop da nota, a marcamos como baixada
                nota.status = 'CONCILIADO'
                nota.save()
                notas_conciliadas_qtd += 1

            # 5. Fechamento dos Depósitos
            # Varre os extratos que manipulamos para verificar se o saldo zerou
            for ex_dict in extratos_saldo:
                ex = ex_dict['obj']
                # Consulta direto no banco para garantia dupla
                total_usado = ConciliacaoNota.objects.filter(extrato=ex).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
                diferenca = ex.valor - total_usado
                
                # Se usou tudo (margem de 1 centavo para arredondamento), baixa o depósito
                if diferenca <= Decimal('0.01'): 
                    ex.status = 'CONCILIADO'
                else:
                    ex.status = 'PENDENTE'
                ex.save()

            if notas_conciliadas_qtd > 0:
                messages.success(request, f"Sucesso! {notas_conciliadas_qtd} nota(s) conciliada(s) com os depósitos selecionados.")
            else:
                messages.warning(request, "Nenhuma nota foi conciliada.")
                
            # IMPORTANTE: Redireciona para o painel limpo (sem extrato_id na URL)
            # Assim a tela recarrega do zero e tira os depósitos da barra lateral!
            return redirect(f"{request.path}?{query_filtros}")

        # --- AÇÃO 4: DESFAZER CONCILIAÇÃO ---
        elif acao == 'desfazer_conciliacao' and extrato_id:
            extrato = get_object_or_404(ExtratoBancario, id=int(extrato_id))
            relacoes = ConciliacaoNota.objects.filter(extrato=extrato)
            for rel in relacoes:
                nota = rel.nota
                nota.status = 'ABERTO'
                nota.save()
            relacoes.delete()
            extrato.status = 'PENDENTE'
            extrato.save()
            messages.success(request, "Conciliação desfeita! O depósito e as notas voltaram para a fila.")
            return redirect(f"{request.path}?extrato_id={extrato_id}{query_filtros}")

        # --- AÇÃO 5: RODAR AUTOMAÇÃO (ROBÔ DE PRÉ-CONCILIAÇÃO) ---
        # --- AÇÃO 5: RODAR AUTOMAÇÃO (ROBÔ DE PRÉ-CONCILIAÇÃO) ---
        elif acao == 'rodar_automacao':
            extratos_para_analise = ExtratoBancario.objects.filter(status='PENDENTE', valor__gt=0)
            if f_banco: extratos_para_analise = extratos_para_analise.filter(banco=f_banco)
            if f_empresa: extratos_para_analise = extratos_para_analise.filter(empresa=f_empresa)
            if f_data: extratos_para_analise = extratos_para_analise.filter(data_transacao=f_data)

            SugestaoAutomacao.objects.filter(extrato__in=extratos_para_analise).delete()

            # MÁGICA 1: O robô agora tem "memória" para não usar a mesma nota duas vezes
            notas_ja_utilizadas_nesta_rodada = set()

            for extrato_analisado in extratos_para_analise:
                cor = 'VERMELHO' 
                notas_encontradas = []
                descricao_ext = str(extrato_analisado.descricao).upper()
                valor_extrato = extrato_analisado.valor
                
                if 'PGTO ITAU' in descricao_ext:
                    numeros_titulos = re.findall(r'\d+', descricao_ext)
                    if numeros_titulos:
                        notas_itau = ContasReceber.objects.filter(
                            titulo__in=numeros_titulos, status='ABERTO'
                        ).filter(
                            Q(cnpj__startswith='60.701.190') | Q(cnpj__startswith='60701190')
                        ).exclude(id__in=notas_ja_utilizadas_nesta_rodada) # Ignora as que já usou
                        
                        if notas_itau.exists():
                            soma_liquida = sum(n.vl_liquido for n in notas_itau)
                            soma_bruta = sum(n.vl_bruto for n in notas_itau)
                            
                            diferenca_liq = abs(valor_extrato - soma_liquida)
                            diferenca_bruta = abs(valor_extrato - soma_bruta)
                            
                            if diferenca_liq <= Decimal('0.05') or diferenca_bruta <= Decimal('0.05'):
                                notas_encontradas = list(notas_itau)
                                cor = 'VERDE'
                                extrato_analisado.cnpj_cpf = '60.701.190/0001-41' 
                                notas_ja_utilizadas_nesta_rodada.update([n.id for n in notas_itau])
                            else:
                                notas_encontradas = list(notas_itau)
                                cor = 'AMARELO'
                                extrato_analisado.cnpj_cpf = '60.701.190/0001-41'
                
                elif extrato_analisado.cnpj_cpf:
                    cnpj_limpo = re.sub(r'[^0-9]', '', extrato_analisado.cnpj_cpf)
                    if len(cnpj_limpo) >= 8:
                        raiz_numeros = cnpj_limpo[:8]
                        raiz_formatada = f"{raiz_numeros[:2]}.{raiz_numeros[2:5]}.{raiz_numeros[5:8]}"
                        
                        # MÁGICA 2: Ordena sempre pela data de vencimento mais antiga e ignora as usadas
                        notas_cliente = ContasReceber.objects.filter(
                            Q(cnpj__startswith=raiz_formatada) | Q(cnpj__startswith=raiz_numeros),
                            status='ABERTO'
                        ).exclude(id__in=notas_ja_utilizadas_nesta_rodada).order_by('dt_vencto_atual')
                        
                        # Pega APENAS A PRIMEIRA nota que bate o valor (a mais antiga por causa da ordem acima)
                        nota_exata = notas_cliente.filter(vl_liquido=valor_extrato).first()
                        
                        if nota_exata:
                            notas_encontradas = [nota_exata]
                            cor = 'VERDE'
                            notas_ja_utilizadas_nesta_rodada.add(nota_exata.id)
                        elif notas_cliente.exists():
                            cor = 'AMARELO'

                extrato_analisado.cor_automacao = cor
                extrato_analisado.save()

                for n in notas_encontradas:
                    SugestaoAutomacao.objects.create(
                        extrato=extrato_analisado, 
                        nota=n, 
                        valor_sugerido=n.vl_liquido
                    )

            messages.success(request, "Automação concluída! Os depósitos foram classificados com precisão cirúrgica.")
            return redirect(f"/conciliacao/painel/?{query_filtros}")

    # ==========================================
    # 2. CARREGAMENTO DA TELA (GET)
    # ==========================================
    extrato_id = request.GET.get('extrato_id')
    if extrato_id:
        extrato_id = str(extrato_id).replace('.', '')

    filtro_banco = request.GET.get('filtro_banco', '')
    filtro_empresa = request.GET.get('filtro_empresa', '')
    filtro_data = request.GET.get('filtro_data', '')

    bancos_disponiveis = ExtratoBancario.objects.filter(
        status='PENDENTE', valor__gt=0
    ).values_list('banco', flat=True).distinct().order_by('banco')

    empresas_disponiveis = ExtratoBancario.objects.filter(
        status='PENDENTE', valor__gt=0
    ).exclude(empresa__isnull=True).exclude(empresa='').values_list('empresa', flat=True).distinct().order_by('empresa')
    
    query_extratos = ExtratoBancario.objects.filter(status='PENDENTE', valor__gt=0)
        
    if filtro_banco: query_extratos = query_extratos.filter(banco=filtro_banco)
    if filtro_empresa: query_extratos = query_extratos.filter(empresa=filtro_empresa)
    if filtro_data: query_extratos = query_extratos.filter(data_transacao=filtro_data)
        
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
    notas_sugeridas_ids = [] 
    
    if extrato_id:
        extrato_selecionado = get_object_or_404(ExtratoBancario, id=int(extrato_id)) 
        
        notas_sugeridas_ids = list(SugestaoAutomacao.objects.filter(
            extrato=extrato_selecionado
        ).values_list('nota_id', flat=True))
        
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
                # LÓGICA DE MATCH INTELIGENTE
                primeiro_match_encontrado = False
            
            for nota in notas_sugeridas:
                nota.saldo_real_calculado = nota.vl_liquido
                nota.match_exato = False
                nota.match_provavel = False
                
                # Se o valor da nota for exatamente igual ao do depósito selecionado
                if nota.saldo_real_calculado == extrato_selecionado.saldo_restante:
                    if not primeiro_match_encontrado:
                        nota.match_exato = True  # Marca a mais antiga como Match Exato (será ticada)
                        primeiro_match_encontrado = True
                    else:
                        nota.match_provavel = True # As demais com mesmo valor viram Prováveis (não ticadas)
                else:
                    # Mantém a seleção do robô caso ele tenha sugerido uma composição de valores diferentes
                    if nota.id in notas_sugeridas_ids:
                        nota.match_exato = True
                
        elif extrato_selecionado.status == 'CONCILIADO':
            relacoes = ConciliacaoNota.objects.filter(extrato=extrato_selecionado).select_related('nota')
            notas_conciliadas = [rel.nota for rel in relacoes]

    email_salvo = ""
    dados_estabelecimentos = []

    if extrato_selecionado and extrato_selecionado.cnpj_cpf:
        obj_email = ClienteEmail.objects.filter(cnpj_busca=extrato_selecionado.cnpj_cpf).first()
        if obj_email:
            email_salvo = obj_email.email
        
        if notas_sugeridas:
            estabs_na_tela = set()
            for n in notas_sugeridas:
                if n.estabelecimento:
                    try:
                        val_estab = int(float(str(n.estabelecimento).strip()))
                        estabs_na_tela.add(val_estab)
                    except (ValueError, TypeError):
                        pass 
            
            if estabs_na_tela:
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
        'filtro_data': filtro_data,
        'notas_sugeridas_ids': notas_sugeridas_ids,
    }
    return render(request, 'conciliacao/painel.html', context)
# ==============================================================
# 1. FUNÇÃO DE BAIXAR O LOTE COMPLETO (TELA GESTÃO CONCILIADOS)
# ==============================================================
@login_required
def exportar_lote_datasul(request, extrato_id=None):
    # A MÁGICA: Em vez de iterar sobre as relações, iteramos sobre as NOTAS ÚNICAS
    if extrato_id:
        notas = ContasReceber.objects.filter(
            conciliacaonota__extrato_id=extrato_id, 
            status='CONCILIADO'
        ).distinct().order_by('dt_emissao_orig')
    else:
        notas = ContasReceber.objects.filter(
            status='CONCILIADO'
        ).distinct().order_by('dt_emissao_orig')
    
    if not notas.exists():
        messages.warning(request, "Nenhuma nota pendente de exportação encontrada.")
        return redirect('gestao_conciliados')

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Lote Datasul')
    
    # FORMATOS DO EXCEL
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
        try: return float(v)
        except (ValueError, TypeError): return 0.0
        
    def to_int(v):
        try: return int(float(str(v).strip()))
        except (ValueError, TypeError): return str(v).strip()

    notas_atualizadas = []
    
    # Agora o laço roda a nota apenas UMA VEZ, não importa quantos depósitos a pagaram
    for row_num, nota in enumerate(notas, 1):
        
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
    
    messages.success(request, f"Lote Excel gerado com sucesso! {len(notas_atualizadas)} notas baixadas de forma única.")
    return response
# ==============================================================
# 2. GESTÃO DE CONCILIADOS
# ==============================================================
@login_required
def gestao_conciliados(request):
    if request.method == 'POST':
        acao = request.POST.get('acao')
        
        # --- AÇÃO: DESFAZER MÚLTIPLAS NOTAS DE UMA VEZ ---
        if acao == 'desconciliar_selecionadas':
            # Aqui pegamos os IDs dos VÍNCULOS (ConciliacaoNota)
            relacoes_ids = request.POST.getlist('relacoes_selecionadas')
            
            if not relacoes_ids:
                messages.warning(request, "Nenhuma nota foi selecionada.")
                return redirect('gestao_conciliados')

            qtd_desfeita = 0
            notas_afetadas = set()
            extratos_afetados = set()
            
            # 1. Identifica todas as notas e extratos envolvidos nos vínculos selecionados
            for rel_id in relacoes_ids:
                rel = ConciliacaoNota.objects.filter(id=rel_id).select_related('nota', 'extrato').first()
                if rel:
                    notas_afetadas.add(rel.nota)
                    extratos_afetados.add(rel.extrato)
                    rel.delete() # Remove o vínculo específico
                    qtd_desfeita += 1

            # 2. Verifica se a nota ainda tem algum vínculo (se não tiver, devolve para ABERTO)
            for nota in notas_afetadas:
                if not ConciliacaoNota.objects.filter(nota=nota).exists():
                    nota.status = 'ABERTO'
                    nota.save()

            # 3. Verifica se o depósito ainda tem saldo usado (se não tiver, volta para PENDENTE)
            for extrato in extratos_afetados:
                total_usado = ConciliacaoNota.objects.filter(extrato=extrato).aggregate(Sum('valor_pago'))['valor_pago__sum'] or Decimal('0.00')
                if total_usado < extrato.valor:
                    extrato.status = 'PENDENTE'
                    extrato.save()

            messages.success(request, f"Sucesso! {qtd_desfeita} vínculo(s) de conciliação removidos.")
            return redirect('gestao_conciliados')

    # --- LISTAGEM PARA A TELA ---
    # Buscamos as NOTAS que estão conciliadas (agrupadas de forma única)
    notas_conciliadas = ContasReceber.objects.filter(status='CONCILIADO').distinct().order_by('dt_vencto_atual')

    tabela_dados = []
    for nota in notas_conciliadas:
        # Busca todos os vínculos de pagamento desta nota
        relacoes = ConciliacaoNota.objects.filter(nota=nota).select_related('extrato')
        
        # Soma o valor total pago por todos os depósitos vinculados
        valor_pago_total = sum(rel.valor_pago for rel in relacoes)
        
        tabela_dados.append({
            'nota': nota,
            'relacoes': relacoes, # Lista de depósitos que compuseram o pagamento
            'valor_pago_total': valor_pago_total,
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
            # Buscando pela ID numérica enviada pelo HTML
            # Pegamos o DNI enviado pelo HTML
            dni_recebido = request.POST.get('credito_id')
            credito = get_object_or_404(CreditoNaoDestinado, dni=dni_recebido)
            
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