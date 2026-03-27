from django import forms
from .models import ClienteSuspenso

class UploadSuspensosForm(forms.Form):
    """
    Formulário simples apenas para o upload do arquivo Excel.
    """
    arquivo = forms.FileField(
        label="Selecione a planilha de Suspensos (.xlsx)",
        widget=forms.ClearableFileInput(attrs={'class': 'form-control', 'accept': '.xlsx'})
    )

class EditarSuspensoForm(forms.ModelForm):
    """
    Formulário para o Modal de Edição.
    Permite alterar os campos manuais e visualizar o status.
    """
    class Meta:
        model = ClienteSuspenso
        # Usando os nomes exatos dos campos que definimos no models.py
        fields = ['suspenso', 'cancelado_flag', 'status']
        
        labels = {
            'suspenso': 'Marcado como Suspenso (Manual)',
            'cancelado_flag': 'Marcado como Cancelado (Manual)',
            'status': 'Status Atual'
        }
        
        widgets = {
            'suspenso': forms.TextInput(attrs={'class': 'form-control'}),
            'cancelado_flag': forms.TextInput(attrs={'class': 'form-control'}),
            # Deixamos o status como leitura apenas (readonly) para evitar edição acidental,
            # já que ele é calculado pelo robô. Se quiser editar, remova o attrs.
            'status': forms.TextInput(attrs={'class': 'form-control', 'readonly': 'readonly'}),
        }


class EditarSuspensoForm(forms.ModelForm):
    class Meta:
        model = ClienteSuspenso
        fields = ['suspenso', 'cancelado_flag'] # Apenas os campos que você edita no modal

    def clean(self):
        cleaned_data = super().clean()
        for field in cleaned_data:
            valor = cleaned_data.get(field)
            # Se o valor for a string "nan", transforma em None (vazio no banco)
            if str(valor).lower() == 'nan':
                cleaned_data[field] = None
        return cleaned_data
    
class ImportarMatrizForm(forms.Form):
    arquivo_excel = forms.FileField(label="Selecione o Relatório Excel (Matriz)")
    tipo_relatorio = forms.ChoiceField(
        choices=[('Geral', 'Geral'), ('Previa', 'Prévia'),('Resumo', 'Resumo')],
        initial='Resumo'
    )