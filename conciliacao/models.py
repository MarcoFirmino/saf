from django.db import models
from django.contrib.auth.models import User
from django.db.models import Sum # Adicione isto lá no topo do arquivo junto com os outros imports, se já não tiver!
# ==========================================
# 1. TABELA DE-PARA (Mantida igual)
# ==========================================
class MapeamentoDePara(models.Model):
    descricao_extrato = models.CharField(max_length=255, unique=True, verbose_name="Descrição no Extrato")
    cnpj_cpf = models.CharField(max_length=18, verbose_name="CNPJ/CPF Correspondente")
    nome_cliente = models.CharField(max_length=150, blank=True, null=True, verbose_name="Nome/Razão Social")
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Mapeamento De-Para"
        verbose_name_plural = "Mapeamentos De-Para"

    def __str__(self):
        return f"{self.descricao_extrato} -> {self.cnpj_cpf}"

# ==========================================
# 2. TABELA DE EXTRATOS IMPORTADOS (Atualizada)
# ==========================================
class ExtratoBancario(models.Model):
    BANCOS = (
        ('ITAU', 'Itaú'),
        ('BRADESCO', 'Bradesco')
    )

    EMPRESAS = (
        ('2', '2 - Protege Proteção e Transporte de Valores'),
        ('4', '4 - Proair Serviços Aux. de Transporte Aereo'),
        ('5', '5 - Provig Form de Profissionais de Segurança'),
        ('50', '50 - Protege Cargo Transportadora'),
        ('6', '6 - Protege Segurança Eletronica'),
        ('7', '7 - Protege Serviços Especiais'),
        ('80', '80 - Portaria do Futuro'),
    )
    
    STATUS = (
        ('PENDENTE', 'Pendente (Sem match)'),
        ('CONCILIADO_PARCIAL', 'Conciliado Parcialmente'),
        ('CONCILIADO', 'Conciliado 100%'),
        ('IGNORADO', 'Ignorado/Tarifa Bancária')
    )

    # --- Novos campos de Identificação da Conta ---
    empresa = models.CharField(max_length=5, choices=EMPRESAS, verbose_name="Empresa")
    conta_corrente = models.CharField(max_length=30, verbose_name="Conta Corrente")
    banco = models.CharField(max_length=20, choices=BANCOS)
    
    # --- Dados da Transação ---
    data_transacao = models.DateField()
    descricao = models.CharField(max_length=255, verbose_name="Lançamento")
    documento = models.CharField(max_length=100, blank=True, null=True, verbose_name="Dcto.")
    valor = models.DecimalField(max_digits=15, decimal_places=2) 
    saldo_conta = models.DecimalField(max_digits=15, decimal_places=2, blank=True, null=True)
    
    # --- Identificação do Cliente ---
    cnpj_cpf = models.CharField(max_length=18, blank=True, null=True, verbose_name="CNPJ/CPF Identificado")
    razao_social = models.CharField(max_length=255, blank=True, null=True, verbose_name="Razão Social Identificada")
    
    status = models.CharField(max_length=30, choices=STATUS, default='PENDENTE')
    data_importacao = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Extrato Bancário"
        verbose_name_plural = "Extratos Bancários"
        # Agora a trava de duplicidade inclui a Empresa e a Conta!
        unique_together = ('empresa', 'banco', 'conta_corrente', 'data_transacao', 'descricao', 'documento', 'valor', 'saldo_conta')

    def __str__(self):
        return f"{self.get_empresa_display()} | {self.banco} C/C: {self.conta_corrente} | {self.data_transacao.strftime('%d/%m/%Y')} | R$ {self.valor}"
    
# ==========================================
# 3. TABELA PONTE DE CONCILIAÇÃO
# ==========================================
class ConciliacaoNota(models.Model):
    extrato = models.ForeignKey(ExtratoBancario, on_delete=models.CASCADE, related_name='conciliacoes', verbose_name="Extrato Bancário")
    
    # IMPORTANTE: Se a sua tabela BaseGeral estiver no app 'analise', mantenha 'analise.BaseGeral'. 
    # Se estiver em outro app, troque a palavra 'analise' pelo nome correto.
    nota = models.ForeignKey('analise.ContasReceber', on_delete=models.PROTECT, related_name='conciliacoes', verbose_name="Nota Fiscal")
    
    valor_pago = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Valor Pago da Nota")
    
    # Se o cliente reteve impostos no momento do pagamento, gravamos aqui
    impostos_retidos = models.DecimalField(max_digits=15, decimal_places=2, default=0, verbose_name="Impostos Retidos no Pagto")
    
    data_conciliacao = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Nota Conciliada"
        verbose_name_plural = "Notas Conciliadas"
        # Garante que uma nota não seja conciliada duas vezes com o mesmo extrato
        unique_together = ('extrato', 'nota')

    def __str__(self):
        return f"Extrato: {self.extrato.id} -> Nota: {self.nota.titulo} (R$ {self.valor_pago})"
    
class ExcecaoConciliacao(models.Model):
    termo = models.CharField(max_length=255, unique=True, verbose_name="Termo Ignorado (Contém)")
    descricao = models.CharField(max_length=255, null=True, blank=True, verbose_name="Motivo/Observação")

    class Meta:
        verbose_name = "Exceção de Importação"
        verbose_name_plural = "Exceções de Importação"

    def __str__(self):
        return self.termo
    
class CreditoNaoDestinado(models.Model):
    # DNI será a chave primária e o controle único
    dni = models.CharField(max_length=15, primary_key=True, verbose_name="DNI")
    data = models.DateField(verbose_name="Data")
    estab = models.IntegerField(verbose_name="Estabelecimento")
    
    # Valores
    credito = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Crédito")
    debitos = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Débitos")
    saldo_final = models.DecimalField(max_digits=15, decimal_places=2, default=0.00, verbose_name="Saldo Final")
    
    # Informações do Cliente
    cliente = models.CharField(max_length=150, verbose_name="Cliente")
    banco = models.CharField(max_length=5, verbose_name="Banco")
    empresa = models.CharField(max_length=15, verbose_name="Empresa")

    def atualizar_saldo(self):
        """ Recalcula o saldo final baseado nos abatimentos registrados """
        # Nota: Só vai funcionar se tiver outra tabela relacionada chamada 'abatimentos'
        total_abatido = self.abatimentos.aggregate(total=Sum('valor'))['total'] or 0
        
        # O Débito total será o que já veio da planilha + os novos abatimentos
        self.debitos = total_abatido
        self.saldo_final = self.credito - self.debitos
        self.save()

    def __str__(self):
        return f"{self.dni} - {self.cliente}"
    
# models.py

class EstabelecimentoCNPJ(models.Model):
    # 1ª coluna Inteiro, 2ª e 3ª Texto
    estab = models.IntegerField(unique=True, verbose_name="Estabelecimento")
    nome_empresa = models.CharField(max_length=150, verbose_name="Nome da Empresa")
    cnpj = models.CharField(max_length=25, verbose_name="CNPJ")

    def __str__(self):
        return f"{self.estab} - {self.cnpj}"

class ClienteEmail(models.Model):
    # Tabela para salvar o e-mail atrelado ao CNPJ pesquisado
    cnpj_busca = models.CharField(max_length=25, unique=True, verbose_name="CNPJ da Busca")
    email = models.CharField(max_length=255, verbose_name="E-mails (Separados por ponto e vírgula)")

    def __str__(self):
        return f"{self.cnpj_busca} - {self.email}"