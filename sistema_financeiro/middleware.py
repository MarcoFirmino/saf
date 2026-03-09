# Crie este arquivo na mesma pasta do settings.py
from django.shortcuts import redirect
from django.urls import reverse

class ForcePasswordChangeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                # Verifica se o perfil pede troca de senha
                if request.user.profile.force_password_change:
                    # Lista de URLs permitidas (para ele não ficar em loop infinito)
                    allowed_paths = [
                        reverse('password_change'),      # URL de troca de senha
                        reverse('password_change_done'), # URL de sucesso
                        reverse('logout'),               # Permitir sair
                    ]
                    
                    if request.path not in allowed_paths:
                        return redirect('password_change')
            except:
                pass # Se o usuário não tiver perfil ou der erro, segue a vida

        response = self.get_response(request)
        return response