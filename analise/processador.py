import re
from datetime import date
from django.db.models import Q
from .models import ClienteSuspenso, BaseGeral

def limpar_cnpj(valor):
    """Remove caracteres não numéricos para comparação."""
    if not valor: return ""
    return re.sub(r'\D', '', str(valor))

def processar_suspensos_db():
    """
    Lógica de processamento corrigida para cruzar os campos corretos.
    """
    hoje = date.today()
    
    # --- CORREÇÃO: Usando 'cnpj_cpf_cliente' que é onde o CNPJ do cliente reside ---
    todos_cnpjs_base = set(
        limpar_cnpj(x) for x in BaseGeral.objects.values_list('cnpj_cpf_cliente', flat=True) if x
    )
    
    cnpjs_vencidos = set(
        limpar_cnpj(x) for x in BaseGeral.objects.filter(
            dt_vencto_atual__lt=hoje
        ).values_list('cnpj_cpf_cliente', flat=True) if x
    )
    
    # Dívida antiga (> 365 dias)
    um_ano_atras = hoje.replace(year=hoje.year - 1)
    cnpjs_antigos = set(
        limpar_cnpj(x) for x in BaseGeral.objects.filter(
            dt_vencto_atual__lt=um_ano_atras
        ).values_list('cnpj_cpf_cliente', flat=True) if x
    )

    clientes_suspensos = ClienteSuspenso.objects.all()
    lista_para_atualizar = []

    for cliente in clientes_suspensos:
        cnpj_limpo = limpar_cnpj(cliente.cnpj)
        # Mantém o status original como ponto de partida
        novo_status = cliente.status 

        # --- REGRA 1: Verificação Manual (Respeita o que o usuário digitou) ---
        if cliente.cancelado_flag and str(cliente.cancelado_flag).strip().upper() == 'SIM':
            novo_status = "Cancelado"
        elif cliente.suspenso and str(cliente.suspenso).strip().upper() == 'SIM':
            novo_status = "Suspenso"
        
        # Se já foi definido como Cancelado manualmente, pula as regras automáticas
        if novo_status == "Cancelado":
            if cliente.status != novo_status:
                cliente.status = novo_status
                lista_para_atualizar.append(cliente)
            continue

        # --- REGRA 2: Restabelecimento Automático ---
        # Se está na Base Geral E NÃO tem títulos vencidos
        if cnpj_limpo and (cnpj_limpo in todos_cnpjs_base) and (cnpj_limpo not in cnpjs_vencidos):
            novo_status = "Restabelecer"

        # --- REGRA 3: Cancelamento Automático (Dívida > 1 ano) ---
        # Mudança de "Cancelar" para "Cancelado" para bater com o Template
        if novo_status not in ["Suspenso", "Cancelado", "Restabelecer"]:
            if cnpj_limpo in cnpjs_antigos:
                novo_status = "Cancelado"

        # Se houve mudança de fato, prepara para salvar
        if cliente.status != novo_status:
            cliente.status = novo_status
            lista_para_atualizar.append(cliente)

    # 3. Salva em lote para performance
    if lista_para_atualizar:
        ClienteSuspenso.objects.bulk_update(lista_para_atualizar, ['status'])
    
    return len(lista_para_atualizar)