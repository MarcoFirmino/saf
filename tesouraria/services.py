import pandas as pd
import os


def gerar_prn_tesouraria(arquivo_excel, nome_aba_alvo):
    # O motor 'xlrd' é chamado automaticamente para arquivos .xls
    # O motor 'openpyxl' é usado para .xlsx e .xlsm
    xl = pd.ExcelFile(arquivo_excel)
    
    # --- REGRA DE NEGÓCIO: BUSCA CASE-INSENSITIVE ---
    aba_encontrada = None
    for sheet in xl.sheet_names:
        # Compara convertendo ambos para maiúsculas (ignora diferença de caixa)
        if sheet.strip().upper() == nome_aba_alvo.strip().upper():
            aba_encontrada = sheet
            break
            
    if not aba_encontrada:
        raise ValueError(f"A aba '{nome_aba_alvo}' não foi encontrada. Abas disponíveis: {', '.join(xl.sheet_names)}")

    # Lê a aba correta (com o nome original preservado em aba_encontrada)
    df = pd.read_excel(xl, sheet_name=aba_encontrada, header=None)

    # ... (Restante da lógica de processamento e montagem das linhas permanece a mesma) ...
    # (Metadados B3, B4, B5, B8, B9 e loop de varredura)



def gerar_prn_tesouraria(arquivo_excel, nome_aba_alvo):
    # 1. Carregar o Excel sem cabeçalho para usar coordenadas exatas do VBA
    xl = pd.ExcelFile(arquivo_excel)
    
    # Busca Case-Insensitive da aba
    aba_encontrada = None
    for sheet in xl.sheet_names:
        if sheet.upper() == nome_aba_alvo.upper():
            aba_encontrada = sheet
            break
            
    if not aba_encontrada:
        raise ValueError(f"A aba '{nome_aba_alvo}' não foi encontrada.")

    df = pd.read_excel(xl, sheet_name=aba_encontrada, header=None)

    # 2. Captura de Metadados com proteção contra 'nan'
    def limpar_meta(val):
        return str(val).strip() if pd.notna(val) and str(val).lower() != 'nan' else ""

    nro_fluxo = limpar_meta(df.iloc[2, 1])  # B3
    estab     = limpar_meta(df.iloc[3, 1])  # B4
    unid_neg  = limpar_meta(df.iloc[4, 1])  # B5
    modulo    = limpar_meta(df.iloc[7, 1])  # B8
    tipo_mov  = limpar_meta(df.iloc[8, 1])  # B9

    linhas_prn = []

    # 3. Varredura da Grade
    for col_idx in range(1, df.shape[1]):
        tipo_fluxo_fin = limpar_meta(df.iloc[11, col_idx]) # Linha 12
        tipo_fluxo     = limpar_meta(df.iloc[12, col_idx]) # Linha 13
        
        # Só processa a coluna se houver cabeçalho de fluxo
        if not tipo_fluxo_fin and not tipo_fluxo:
            continue

        for row_idx in range(13, df.shape[0]):
            valor = df.iloc[row_idx, col_idx]
            
            # Regra: valor numérico e maior que zero
            if pd.notna(valor) and isinstance(valor, (int, float)) and valor > 0:
                # Formatação de Data: ddmmyyyy (Coluna A)
                data_bruta = df.iloc[row_idx, 0]
                try:
                    data_fmt = pd.to_datetime(data_bruta).strftime('%d%m%Y')
                except:
                    data_fmt = "00000000"
                
                # --- CORREÇÃO DE VALOR (CENTAVOS) ---
                # Transforma 123.45 em 12345 (inteiro de centavos) antes de formatar com zeros
                valor_inteiro = int(float(valor))
                valor_fmt = f"{valor_inteiro:013d}"

                # 4. Montagem da Linha com Larguras Fixas (Layout 78 caracteres)
                linha = (
                    nro_fluxo[:9].ljust(9) +
                    data_fmt[:8].ljust(8) +
                    estab[:8].ljust(8) +
                    unid_neg[:8].ljust(8) +
                    tipo_fluxo_fin[:8].ljust(8) +
                    tipo_fluxo[:8].ljust(8) +
                    tipo_mov[:8].ljust(8) +
                    modulo[:8].ljust(8) +
                    valor_fmt[:13].rjust(13)
                )
                linhas_prn.append(linha)

    # 5. Nome do arquivo
    nome_original = os.path.splitext(arquivo_excel.name)[0]
    nome_saida = f"{nome_original[:3]}{estab}W.PRN"
    
    # Usa \r\n (Padrão Windows) para garantir compatibilidade com sistemas legados
    conteudo_final = "\r\n".join(linhas_prn)
    return conteudo_final, nome_saida