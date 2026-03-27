# SAF - Sistema de Análise e Financeiro (Protege)

O **SAF** é uma plataforma centralizada desenvolvida em Django para automatizar processos críticos do departamento financeiro da Protege. O sistema integra ferramentas de análise de crédito e utilitários de tesouraria.

## 🚀 Funcionalidades Principal

### 📊 Módulo de Análise
* **Gestão de Suspensos**: Visualização e edição de clientes com crédito suspenso.
* **Relatórios de Inadimplência**: Importação automatizada de bases (Paycash, Jurídico Carga, Consolidado e BD Clientes).
* **Contas a Receber**: Visualização detalhada de relatórios financeiros.

### 💰 Módulo de Tesouraria
* **Conversor Excel para PRN**: Ferramenta que realiza o *unpivot* de planilhas de fluxo de caixa.
    * Suporta formatos `.xlsx`, `.xlsm` e `.xls`.
    * Gera arquivos de texto com colunas de largura fixa (padrão 78 caracteres).
    * Lógica de arredondamento: Ignora casas decimais conforme regra de negócio.
    * Busca de abas *case-insensitive*.

## 🛠️ Tecnologias Utilizadas
* **Backend**: Python 3.11 & Django 5.2.9
* **Processamento de Dados**: Pandas, Openpyxl, xlrd
* **Frontend**: Bootstrap 5 & Bootstrap Icons
* **Banco de Dados**: SQLite (Desenvolvimento)

## ⚙️ Como Instalar e Rodar o Projeto

1. **Clone o repositório**:
   ```bash
   git clone [https://github.com/MarcoFirmino/saf.git](https://github.com/MarcoFirmino/saf.git)
   cd saf