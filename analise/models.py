from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.dispatch import receiver

# --- Tabela que já criamos antes ---
class CodigoIgnorado(models.Model):
    codigo = models.IntegerField(unique=True, verbose_name="Código")

    class Meta:
        verbose_name = "Código Ignorado"
        verbose_name_plural = "Códigos Ignorados"
        db_table = "CodigosIgnorados"

    def __str__(self):
        return str(self.codigo)

# --- NOVA TABELA AQUI EMBAIXO ---
class EmpresasCorporativas(models.Model):
    # CharField é o campo de texto (String)
    # max_length=255 define que o nome pode ter até 255 letras
    nome = models.CharField(max_length=255, verbose_name="Nome da Empresa")

    class Meta:
        verbose_name = "Empresa Corporativa"
        verbose_name_plural = "Empresas Corporativas"
        db_table = "EmpresasCorporativas"

    def __str__(self):
        return self.nome
    # --- NOVAS TABELAS ---

class NegocioCorporativo(models.Model):
    nome = models.CharField(max_length=150, verbose_name="Nome")

    class Meta:
        verbose_name = "Negócio Corporativo"
        verbose_name_plural = "Negócios Corporativos"
        db_table = "NegocioCorporativo"

    def __str__(self):
        return self.nome

class ResponsavelEmpresa(models.Model):
    empresa = models.CharField(max_length=150, verbose_name="Empresa")
    carteira = models.CharField(max_length=150, verbose_name="Carteira")

    class Meta:
        verbose_name = "Responsável por Empresa"
        verbose_name_plural = "Responsáveis por Empresas"
        db_table = "ResponsavelEmpresa"

    def __str__(self):
        return f"{self.empresa} - {self.carteira}"

class ResponsavelNegocio(models.Model):
    negocio = models.CharField(max_length=150, verbose_name="Negócio")
    carteira = models.CharField(max_length=150, verbose_name="Carteira")

    class Meta:
        verbose_name = "Responsável por Negócio"
        verbose_name_plural = "Responsáveis por Negócios"
        db_table = "ResponsavelNegocio"

    def __str__(self):
        return f"{self.negocio} - {self.carteira}"
    
class JurCargaSegura(models.Model):
    # Colunas de Texto (CharField) conforme solicitado
    raiz = models.CharField(max_length=15, verbose_name="Raiz")
    razao = models.CharField(max_length=150, verbose_name="Razão Social")
    perfil = models.CharField(max_length=100, verbose_name="Perfil")
    negocio = models.CharField(max_length=50, verbose_name="Negócio")
    chave = models.CharField(max_length=150, verbose_name="Chave")
    executivo = models.CharField(max_length=50, verbose_name="Executivo")
    
    # "Responsável Financeiro" vira snake_case no código
    responsavel_financeiro = models.CharField(max_length=50, verbose_name="Responsável Financeiro")
    
    grupo = models.CharField(max_length=100, verbose_name="Grupo")
    status = models.CharField(max_length=15, verbose_name="Status")

    class Meta:
        verbose_name = "Jur Carga Segura"
        verbose_name_plural = "Jur Carga Segura"
        db_table = "JurCargaSegura"

    def __str__(self):
        # Retorna a Razão Social como identificador principal
        return self.razao
    
class Paycash(models.Model):
    # A coluna ID é criada automaticamente (automática e oculta)
    
    chave = models.CharField(max_length=30, verbose_name="Chave")
    
    # Internamente chamamos de snake_case, mas na tela aparecerá "DT.Emissao Fatura"
    dt_emissao_fatura = models.DateField(verbose_name="DT.Emissao Fatura")
    
    estabelecimento = models.IntegerField(verbose_name="Estabelecimento")
    uf = models.CharField(max_length=2, verbose_name="UF")
    nro_fatura = models.IntegerField(verbose_name="Nro Fatura")
    serie = models.CharField(max_length=5, verbose_name="Série")
    rps = models.IntegerField(verbose_name="RPS")
    codigo = models.IntegerField(verbose_name="Código")
    nome = models.CharField(max_length=200, verbose_name="Nome")

    class Meta:
        verbose_name = "Paycash"
        verbose_name_plural = "Paycash"
        db_table = "Paycash"

    def __str__(self):
        return f"{self.nome} - {self.nro_fatura}"
    
class Bd_Clientes(models.Model):
    # Coluna ID é automática
    
    cnpj_raiz = models.CharField(max_length=30, verbose_name="CNPJ_Raiz")
    razao_social = models.CharField(max_length=250, verbose_name="Razão_Social")
    perfil_fatura = models.CharField(max_length=50, verbose_name="Perfil Fatura")
    perfil_negocio = models.CharField(max_length=50, verbose_name="Perfil Negocio")
    perfil_chave = models.CharField(max_length=100, verbose_name="Perfil Chave")
    perfil_executivo = models.CharField(max_length=150, verbose_name="Perfil Executivo")
    
    # Perfil Responsavel_Financeiro
    perfil_responsavel_financeiro = models.CharField(max_length=20, verbose_name="Perfil Responsavel_Financeiro")
    
    perfil_grupo_ponto = models.CharField(max_length=50, verbose_name="Perfil Grupo_Ponto")
    perfil_status = models.CharField(max_length=10, verbose_name="Perfil Status")

    class Meta:
        verbose_name = "BD Cliente"
        verbose_name_plural = "BD Clientes"
        db_table = "Bd_Clientes"

    def __str__(self):
        return f"{self.cnpj_raiz} - {self.razao_social}"
    
class Consolidado_Juridico(models.Model):
    chave = models.CharField(max_length=20, verbose_name="Chave")
    classificacao = models.CharField(max_length=50, verbose_name="Classificação")
    estabelec = models.CharField(max_length=5, verbose_name="Estabelec")
    serie = models.CharField(max_length=5, verbose_name="Série")
    titulo = models.IntegerField(verbose_name="Título")
    unid_neg = models.CharField(max_length=5, verbose_name="Unid_Neg")
    codigo = models.IntegerField(verbose_name="Código")
    
    # Campo ajustado para snake_case no código, mas título fiel na tela
    cnpj_cpf_cliente = models.CharField(max_length=25, verbose_name="CNPJ/CPF_Cliente")
    
    grupo = models.CharField(max_length=50, verbose_name="Grupo")
    nome_abrev = models.CharField(max_length=150, verbose_name="Nome_Abrev")
    
    dt_emissao_orig = models.DateField(verbose_name="Dt.Emissão Orig", null=True, blank=True)
    dt_vencto_original = models.DateField(verbose_name="Dt.Vencto Original", null=True, blank=True)
    
    # Usamos DecimalField para garantir as 2 casas decimais financeiras
    vl_bruto_orig = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Vl.Bruto Orig.")
    vl_liquido = models.DecimalField(max_digits=15, decimal_places=2, verbose_name="Vl.líquido")

    class Meta:
        verbose_name = "Consolidado Jurídico"
        verbose_name_plural = "Consolidado Jurídico"
        db_table = "Consolidado_Juridico"

    def __str__(self):
        return f"{self.chave} - {self.nome_abrev}"
    
class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    force_password_change = models.BooleanField(default=True, verbose_name="Obrigar troca de senha")

    def __str__(self):
        return f"Perfil de {self.user.username}"

# SINAIS (Signals)
# Isso garante que sempre que o Admin criar um User, o Django cria um Profile automaticamente
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        # Se for o superuser (você), não obriga a troca. Se for usuário comum, obriga.
        obriga = False if instance.is_superuser else True
        Profile.objects.create(user=instance, force_password_change=obriga)

@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Tenta salvar o profile se ele já existir, senão cria (para evitar erros com usuários antigos)
    try:
        instance.profile.save()
    except Profile.DoesNotExist:
        Profile.objects.create(user=instance, force_password_change=False)


class BaseGeral(models.Model):
    """
    Tabela de Staging para importar o arquivo geral bruto.
    """
    # Identificação Básica
    estabelecimento = models.CharField(max_length=4, verbose_name="Estabelec")
    especie = models.CharField(max_length=3, verbose_name="Espécie")
    serie = models.CharField(max_length=5, verbose_name="Série")
    titulo = models.BigIntegerField(verbose_name="Título") # Usei BigInteger por segurança
    parcela = models.CharField(max_length=3, verbose_name="Parcela")
    
    # Datas
    dt_emissao_orig = models.DateField(verbose_name="Dt.Emissão Orig")
    dt_emissao_ult_ren = models.DateField(verbose_name="Dt.Emissão Últ.Ren", null=True, blank=True)
    dt_vencto_original = models.DateField(verbose_name="Dt.Vencto Original")
    dt_vencto_atual = models.DateField(verbose_name="Dt.Vencto Atual")
    
    # Dados de Destino/Empresa
    estab_dest = models.CharField(max_length=4, verbose_name="Estab.Dest", null=True, blank=True)
    c_custo_dest = models.CharField(max_length=4, verbose_name="C.Custo.Dest", null=True, blank=True)
    empresa = models.CharField(max_length=3, verbose_name="Empresa")
    
    # Clientes e Identificação
    cnpj = models.CharField(max_length=18, verbose_name="CNPJ", null=True, blank=True)
    cnpj_cpf_cliente = models.CharField(max_length=18, verbose_name="CNPJ/CPF Cliente", null=True, blank=True)
    codigo = models.BigIntegerField(verbose_name="Código")
    nome_abrev = models.CharField(max_length=250, verbose_name="Nome Abrev")
    
    # Valores Monetários (Todos com 2 casas decimais conforme imagem)
    vl_bruto_reneg = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Vl.Bruto Reneg.")
    vl_bruto_orig = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Vl.Bruto Orig.")
    
    # Impostos e Descontos (Permitem Nulo)
    pis = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="PIS")
    cofins = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="Cofins")
    csll = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="CSLL")
    irrf = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="IRRF")
    iss = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="ISS")
    inss = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True, verbose_name="INSS")
    
    # Totais e Contabilidade
    desconto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Desconto")
    liquidacao = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Liquidacao")
    acerto = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Acerto")
    conta_contabil = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Conta Contabil")
    multa = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Multa")
    juros = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Juros")
    vl_liq_orig = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Vl.Liq.Orig")
    vl_liquido = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True, verbose_name="Vl.Líquido")
    
    # Classificação e Controle
    carteira = models.CharField(max_length=2, verbose_name="Carteira")
    unid_negoc = models.CharField(max_length=4, verbose_name="Unid.Negoc")
    cnpj_estab = models.CharField(max_length=18, verbose_name="CNPJ Estab.", null=True, blank=True)
    gr_cli = models.CharField(max_length=5, verbose_name="Gr. Cli", null=True, blank=True)
    descricao_gr_cli = models.CharField(max_length=20, verbose_name="Descrição Gr. Cli.", null=True, blank=True)
    
    # Régua e Cobrança
    posicao_da_regua = models.CharField(max_length=100, verbose_name="Posição da Régua", null=True, blank=True)
    usuario_regua = models.CharField(max_length=20, verbose_name="Usuário Régua", null=True, blank=True)
    ultima_movimentacao = models.CharField(max_length=10, verbose_name="Última Movimentação", null=True, blank=True)
    responsavel = models.CharField(max_length=20, verbose_name="Responsável", null=True, blank=True)
    motivo_renegociacao = models.CharField(max_length=10, verbose_name="Motivo Renegociaço", null=True, blank=True)
    
    # Outros
    nosso_numero = models.CharField(max_length=15, verbose_name="Nosso Número", null=True, blank=True)
    portador = models.CharField(max_length=5, verbose_name="Portador", null=True, blank=True)
    observacao_nota = models.CharField(max_length=15, verbose_name="Observação Nota", null=True, blank=True)

    # Controle Interno do Sistema
    
    data_importacao = models.DateTimeField(auto_now_add=True, null=True, blank=True)
   
    def __str__(self):
        return f"{self.titulo} - {self.nome_abrev}"
    
class ClienteSuspenso(models.Model):
    # --- Campos Obrigatórios (Not Null) ---
    status = models.CharField(
        max_length=15, 
        verbose_name="Status",
        default="Em Análise" # Adicionei um default para evitar erro ao criar, mas é obrigatório
    )
    
    cnpj = models.CharField(
        max_length=18, 
        verbose_name="CNPJ"
    )
    
    cnpj_raiz = models.CharField(
        max_length=12, 
        verbose_name="CNPJ Raiz"
    )
    
    estabelecimento = models.CharField(
        max_length=30, 
        verbose_name="Estabelecimento"
    )
    
    razao_social = models.CharField(
        max_length=200, 
        verbose_name="Razão Social"
    )

    # --- Campos Opcionais (Admitem Nulo) ---
    data_suspensao = models.DateField(
        null=True, 
        blank=True, 
        verbose_name="Data Suspensão"
    )
    
    # Campo para marcação manual ("Sim"/"Não" ou similar - 3 chars)
    suspenso = models.CharField(
        max_length=3, 
        null=True, 
        blank=True, 
        verbose_name="Suspenso"
    )
    
    data_restabelecimento = models.DateField(
        null=True, 
        blank=True, 
        verbose_name="Data Restabelecimento"
    )
    
    executivo = models.CharField(
        max_length=150, 
        null=True, 
        blank=True, 
        verbose_name="EXECUTIVO"
    )
    
    # Decimal com 2 casas. max_digits=15 permite valores até trilhões
    inadimplencia2 = models.DecimalField(
        max_digits=15, 
        decimal_places=2, 
        null=True, 
        blank=True, 
        verbose_name="Inadimplência2"
    )
    
    operacao_ultimo_atendimento = models.DateField(
        null=True, 
        blank=True, 
        verbose_name="Operação - Último Atendimento"
    )
    
    # Campo para marcação manual ("Sim"/"Não" - 3 chars)
    cancelado_flag = models.CharField(
        max_length=3, 
        null=True, 
        blank=True, 
        verbose_name="Cancelado?"
    )
    
    data_cancelamento = models.CharField(
        null=True, 
        blank=True, 
        verbose_name="Data Cancelamento"
    )

    # Campo de controle interno (data que subiu o arquivo)
    data_importacao = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.cnpj} - {self.razao_social}"

    # --- MODELO PARA O DASHBOARD DE RESUMO ---

class DashboardIndicador(models.Model):
    # Categorias para organizar os botões do menu lateral
    CATEGORIAS = [
        ('RESUMO', 'Resumo Gerencial'),
        ('RENEGOCIACAO', 'Renegociações'),
        ('AGING_PACOTE', 'Aging Pacote'),
        ('NEGOCIO', 'Negócio'),
        ('EMPRESA', 'Empresa'),
        ('AGING', 'Aging'),
        ('AGING_JURIDICO', 'Aging Jurídico'),
    ]

    data_referencia = models.DateField(verbose_name="Data da Foto") # Ex: 31/01, 28/02, 10/03
    categoria_painel = models.CharField(max_length=50, choices=CATEGORIAS, default='RESUMO')
    
    # Descrição é o que aparece na primeira coluna (ex: "Logística", "Quebra de Acordo")
    descricao = models.CharField(max_length=150, verbose_name="Descrição/Métrica")
    
    valor = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Valor R$")
    percentual = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, verbose_name="% (se houver)")
    
    # Campo para identificar se é fechamento de mês (para não ser excluído)
    is_final_mes = models.BooleanField(default=False, verbose_name="É fechamento mensal?")

    class Meta:
        verbose_name = "Dado do Dashboard"
        verbose_name_plural = "Dados do Dashboard"
        db_table = "DashboardIndicadores"
        # Ordena para que as datas mais recentes apareçam primeiro
        ordering = ['-data_referencia', 'descricao']

    def __str__(self):
        return f"{self.data_referencia} - {self.descricao}"
    from django.db import models

class BaseHistoricaRelatorio(models.Model):
    # --- Campos de Controle do Sistema ---
    data_geracao = models.DateField(verbose_name="Data da Foto/Extração")
    aba_origem = models.CharField(max_length=50, verbose_name="Aba de Origem") # Ex: Todos, Renegociados, Jurídico

    # --- Regionalização e Identificação ---
    regional = models.CharField(max_length=100, verbose_name="Regional", null=True, blank=True)
    base_operacional = models.CharField(max_length=100, verbose_name="Base Operacional", null=True, blank=True)
    estabelecimento = models.CharField(max_length=10, verbose_name="Estabelec", null=True, blank=True)
    
    # --- Dados do Documento ---
    especie = models.CharField(max_length=5, verbose_name="Espécie", null=True, blank=True)
    serie = models.CharField(max_length=10, verbose_name="Série", null=True, blank=True)
    titulo = models.BigIntegerField(verbose_name="Título", null=True, blank=True)
    parcela = models.CharField(max_length=5, verbose_name="Parcela", null=True, blank=True)
    
    # --- Negócio e Carteira ---
    unid_negoc = models.CharField(max_length=50, verbose_name="Unid.Negoc", null=True, blank=True)
    negocio = models.CharField(max_length=100, verbose_name="Negócio", null=True, blank=True)
    empresa = models.CharField(max_length=10, verbose_name="Empresa", null=True, blank=True)
    carteira = models.CharField(max_length=10, verbose_name="Carteira", null=True, blank=True)
    
    # --- Dados do Cliente ---
    codigo = models.BigIntegerField(verbose_name="Codigo", null=True, blank=True)
    pacote = models.CharField(max_length=100, verbose_name="Pacote", null=True, blank=True)
    cnpj_raiz = models.CharField(max_length=20, verbose_name="Raiz CNPJ", null=True, blank=True)
    cnpj_cpf = models.CharField(max_length=25, verbose_name="CNPJ/CPF Cliente", null=True, blank=True)
    razao_agrupada = models.CharField(max_length=255, verbose_name="Razão Agrupada", null=True, blank=True)
    nome_abrev = models.CharField(max_length=255, verbose_name="Nome Abrev", null=True, blank=True)
    
    # --- Datas ---
    dt_emissao_orig = models.DateField(verbose_name="Dt.Emissão Orig", null=True, blank=True)
    dt_emissao_ult_ren = models.DateField(verbose_name="Dt.Emissão Últ.Ren", null=True, blank=True)
    dt_vencto_original = models.DateField(verbose_name="Dt.Vencto Original", null=True, blank=True)
    dt_vencto_atual = models.DateField(verbose_name="Dt.Vencto Atual", null=True, blank=True)
    
    # --- Valores Monetários ---
    vl_bruto_orig = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Vl.Bruto Orig.")
    vl_liquido = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Vl.líquido")
    
    # --- Aging e Status ---
    dias_atraso = models.IntegerField(verbose_name="Dias em Atraso", default=0)
    dias_atraso_re = models.IntegerField(verbose_name="Dias em Atraso RE", default=0)
    aging = models.CharField(max_length=50, verbose_name="Aging", null=True, blank=True)
    aging_re = models.CharField(max_length=50, verbose_name="Aging RE", null=True, blank=True)
    status = models.CharField(max_length=100, verbose_name="Status", null=True, blank=True)

    class Meta:
        db_table = "BaseHistoricaRelatorio"
        verbose_name = "Registro Histórico de Relatório"
        verbose_name_plural = "Registros Históricos de Relatório"
        # Indexar data_geracao e unid_negoc garante que o Dashboard carregue instantaneamente
        indexes = [
            models.Index(fields=['data_geracao', 'aba_origem', 'unid_negoc']),
        ]

    def __str__(self):
        return f"{self.data_geracao} - {self.nome_abrev} ({self.vl_liquido})"

    # Linha 458
class ResumoInadimplencia(models.Model):
    # A partir daqui, aperte TAB ou 4 espaços no início de cada linha:
        seguimento = models.CharField(max_length=150, verbose_name="Seguimento / Métrica")
        data = models.DateField(verbose_name="Data de Referência")
        valor = models.DecimalField(max_digits=18, decimal_places=2, verbose_name="Valor R$")
        tipo_relatorio = models.CharField(max_length=50, default='GERAL', verbose_name="Tipo de Relatório")

        class Meta:
            db_table = "ResumoInadimplencia"
            verbose_name = "Histórico de Resumo"
            verbose_name_plural = "Histórico de Resumos"
            ordering = ['data', 'seguimento']
            unique_together = ['seguimento', 'data', 'tipo_relatorio']

        def __str__(self):
            return f"{self.data} | {self.seguimento}: {self.valor}"

# No seu models.py
class DevedorAging(models.Model):
    # Mudamos de aging_tipo para data_base para suportar a linha "Base-31/01/2026"
    data_base = models.DateField(verbose_name="Data de Referência", null=True, blank=True)
    
    ate_30_dias = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    de_31_a_60_dias = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    de_61_a_90_dias = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    de_91_a_120_dias = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    de_121_a_150_dias = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    de_151_a_180_dias = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    mais_de_180_dias = models.DecimalField(max_digits=15, decimal_places=2, default=0.00)
    total = models.DecimalField(max_digits=15, decimal_places=2, editable=False, default=0.00)

    def save(self, *args, **kwargs):
        self.total = (
            self.ate_30_dias + self.de_31_a_60_dias + self.de_61_a_90_dias +
            self.de_91_a_120_dias + self.de_121_a_150_dias + 
            self.de_151_a_180_dias + self.mais_de_180_dias
        )
        super().save(*args, **kwargs)