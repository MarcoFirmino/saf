import psycopg2

# --- PREENCHA COM SEUS DADOS REAIS DENTRO DAS ASPAS ---
# Se o endereço está correto, coloque-o aqui:
HOST = "aws-0-sa-east-1.pooler.supabase.com" 
DBNAME = "postgres"
USER = "postgres.glaliyommwmaugkofdgb"
PASSWORD = "SUA_SENHA_AQUI" 
PORT = "6543" 
# -----------------------------------------------------

print(f"1. Tentando conectar especificamente em: {HOST}")

try:
    connection = psycopg2.connect(
        user=USER,
        password=PASSWORD,
        host=HOST,
        port=PORT,
        dbname=DBNAME
    )
    print("✅ SUCESSO! Conexão realizada com o Supabase.")
    
    # Teste simples de consulta
    cursor = connection.cursor()
    cursor.execute("SELECT version();")
    db_version = cursor.fetchone()
    print(f"📊 Versão do Banco: {db_version[0]}")
    
    cursor.close()
    connection.close()

except psycopg2.OperationalError as e:
    print("\n❌ FALHA OPERACIONAL (Rede/DNS/Senha):")
    print(f"O erro exato foi: {e}")
except Exception as e:
    print("\n❌ OUTRO ERRO:")
    print(e)