from django.shortcuts import render
from django.http import HttpResponse
from django.contrib import messages  # Importante para o feedback visual
from .services import gerar_prn_tesouraria

def converter_prn_view(request):
    if request.method == "POST" and request.FILES.get('arquivo_excel'):
        arquivo = request.FILES['arquivo_excel']
        # Captura o nome da aba, com fallback para 'Planilha1'
        nome_aba = request.POST.get('nome_aba', 'Planilha1') 
        
        try:
            conteudo, nome_arquivo = gerar_prn_tesouraria(arquivo, nome_aba)
            
            # Monta a resposta de download
            response = HttpResponse(conteudo, content_type='text/plain')
            response['Content-Disposition'] = f'attachment; filename="{nome_arquivo}"'
            return response
            
        except Exception as e:
            # Usa o sistema de mensagens que já configuramos no base.html
            messages.error(request, f"Erro no processamento: {e}")
            return render(request, 'tesouraria/upload.html')

    # GET: Renderiza a página inicial de upload
    return render(request, 'tesouraria/upload.html')