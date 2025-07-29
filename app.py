import os
import json
import base64
import logging
from flask import Flask, request, abort
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials

app = Flask(__name__)

# Configuração de Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Autenticação Google Sheets
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]

def load_google_creds():
    google_creds = os.getenv("GOOGLE_CREDS")
    if not google_creds:
        raise ValueError("Variável GOOGLE_CREDS não encontrada!")
    try:
        # Corrige padding do Base64 (se necessário)
        pad = len(google_creds) % 4
        if pad: google_creds += '=' * (4 - pad)
        decoded = base64.b64decode(google_creds).decode('utf-8')
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"Erro ao decodificar credenciais: {str(e)}")
        raise

try:
    creds = ServiceAccountCredentials.from_json_keyfile_dict(load_google_creds(), scope)
    client = gspread.authorize(creds)
    sheet = client.open("PedidosFrozy").sheet1  # Altere para o nome da sua planilha
    logger.info("Conexão com Google Sheets OK!")
except Exception as e:
    logger.error(f"Falha na inicialização: {str(e)}")
    raise

# Catálogo de Produtos (Frozy + Truly Juice)    
produtos = {
    "1": {
        "nome": "Frozy Pet 350ml",
        "preco_caixa": 245,
        "unidades_por_caixa": 24,
        "sabores": ["Laranja", "Framboesa", "Limão", "Cola", "Lichia", "Uva", "Coco Ananás", "Manga", "Maçã", "Maracujá"],
        "imagem": " https://drive.google.com/uc?export=view&id=1O_SpSh133QV7dhdGALnibLsYdh-zNY6d"  
    },
    "2": {
        "nome": "Frozy Energy Pet 350ml",
        "preco_caixa": 340,
        "unidades_por_caixa": 24,
        "sabores": ["Energético"],  
        "imagem": "https://drive.google.com/uc?export=view&id=1HtK7WPGtT1BIDkQTbiKHmjpIf9em_Wn6" 
    },
    "3": {
        "nome": "Frozy 2l",
        "preco_caixa": 290,
        "unidades_por_caixa": 6,
        "sabores": ["Laranja", "Framboesa", "Limão", "Cola", "Uva", "Coco Ananás", "Manga"], 
        "imagem": "https://drive.google.com/uc?export=view&id=10shJM3v_XRgGXCAbXJEHg_Mvoo5BQd00"  
    },
    "4": {
        "nome": "Truly Juice 300 ml",
        "preco_caixa": 140,
        "unidades_por_caixa": 12,
        "sabores": ["Laranja", "Mistura Bagas", "Manga", "Guava", "Tropical", "Ananás"], 
        "imagem": "https://drive.google.com/uc?export=view&id=1M9onuFaEvF2DDIzuZtMfD9gPmDbcEOfA"
    },
    "5": {
        "nome": "Frozy Lata 330ml",
        "preco_caixa": 440,
        "unidades_por_caixa": 24,
        "sabores": ["Laranja", "Framboesa", "Limão", "Cola", "Lichia", "Uva" "Coco Ananás"],
        "imagem": "https://drive.google.com/uc?export=view&id=1GLm--MmLtm4dbJXWQLwrh5D5uIZ82f3A" 
    },
    "6": {
        "nome": "Frozy Energy 300ml",
        "preco_caixa": 490,
        "unidades_por_caixa": 24,
        "sabores": ["Energético"],      
        "imagem": "https://drive.google.com/uc?export=view&id=11c2KebCWsAt0aYpmzaiFhjAUvGT4MRKc"
    },
    "7": {
        "nome": "Frozy Energy 500ml",
        "preco_caixa": 540,
        "unidades_por_caixa": 24,
        "sabores": ["Energético"], 
        "imagem": "https://drive.google.com/uc?export=view&id=1wEYg1hqQYQQ-9JCLGQxk-l6JGrLuJA-9" 
    }
}

# Sessões dos Usuários (armazena pedidos em andamento)
user_sessions = {}

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    mensagem = request.values.get("Body", "").strip().lower()
    remetente = request.values.get("From", "")
    resposta = MessagingResponse()

    # Se é a primeira interação, envia mensagem de boas-vindas + catálogo
    if remetente not in user_sessions:
        user_sessions[remetente] = {"step": "inicio", "pedidos": []}
        
        # Mensagem de boas-vindas com imagem (opcional)
        resposta.message("🍹 *Bem-vindo à Frozy Refrigerantes!* 🍹\nAqui está nosso catálogo:")
        
        # Envia imagem do produto principal (ex: logo Frozy)
        resposta.message().media("https://drive.google.com/uc?export=view&id=1ft6koTT-9PaSN8xz4XRWxKzlqrxAtbuR")  
        
        # Lista produtos
        menu = "📋 *Escolha um produto:*\n"
        for codigo, produto in produtos.items():
            menu += f"{codigo}. {produto['nome']} - {produto['preco_caixa']} MZN/caixa\n"
        resposta.message(menu)
        return str(resposta)
    
    sessao = user_sessions[remetente]
    
    # Etapa 1: Escolha do Produto
    if sessao["step"] == "inicio":
        if mensagem in produtos:
            sessao["produto_atual"] = mensagem
            sessao["step"] = "escolher_sabor"
            
            # Envia imagem do produto escolhido
            resposta.message().media(produtos[mensagem]["imagem"])
            
            # Lista sabores
            sabores = "\n".join([f"{i+1}. {sabor}" for i, sabor in enumerate(produtos[mensagem]["sabores"])])
            resposta.message(f"Escolha um sabor para {produtos[mensagem]['nome']}:\n{sabores}")
        else:
            resposta.message("❌ Código inválido. Digite o número do produto (ex: 1).")
    
    # Etapa 2: Escolha do Sabor
    elif sessao["step"] == "escolher_sabor":
        produto = produtos[sessao["produto_atual"]]
        sabores_validos = [str(i+1) for i in range(len(produto["sabores"]))]
        
        if mensagem in sabores_validos:
            sabor_escolhido = produto["sabores"][int(mensagem)-1]
            sessao["sabor_atual"] = sabor_escolhido
            sessao["step"] = "quantidade"
            resposta.message(f"Quantas caixas de *{produto['nome']} ({sabor_escolhido})* você deseja?")
        else:
            resposta.message(f"❌ Sabor inválido. Digite um número entre 1 e {len(produto['sabores'])}.")
    
    # Etapa 3: Quantidade
    elif sessao["step"] == "quantidade":
        try:
            quantidade = int(mensagem)
            if quantidade <= 0:
                raise ValueError
            
            # Adiciona ao carrinho
            pedido = {
                "produto": produtos[sessao["produto_atual"]]["nome"],
                "sabor": sessao["sabor_atual"],
                "quantidade": quantidade,
                "preco_unitario": produtos[sessao["produto_atual"]]["preco_caixa"]
            }
            sessao["pedidos"].append(pedido)
            
            # Pergunta se quer adicionar mais itens
            sessao["step"] = "adicionar_mais"
            resposta.message("✅ Pedido adicionado! Deseja adicionar outro produto? (sim/não)")
        except ValueError:
            resposta.message("❌ Digite um número válido (ex: 2).")
    
    # Etapa 4: Adicionar mais itens?
    elif sessao["step"] == "adicionar_mais":
        if mensagem == "sim":
            sessao["step"] = "inicio"
            menu = "📋 *Escolha outro produto:*\n"
            for codigo, produto in produtos.items():
                menu += f"{codigo}. {produto['nome']} - {produto['preco_caixa']} MZN/caixa\n"
            resposta.message(menu)
        elif mensagem == "não":
            # Resumo do pedido
            total = sum(p["quantidade"] * p["preco_unitario"] for p in sessao["pedidos"])
            resumo = "📦 *Resumo do Pedido:*\n"
            for p in sessao["pedidos"]:
                resumo += f"- {p['quantidade']}x {p['produto']} ({p['sabor']}): {p['quantidade'] * p['preco_unitario']} MZN\n"
            resumo += f"\n💵 *Total: {total} MZN*"
            
            resposta.message(resumo)
            resposta.message("Confirma o pedido? (sim/não)")
            sessao["step"] = "confirmar"
        else:
            resposta.message("Responda 'sim' ou 'não'.")
    
    # Etapa 5: Confirmação
    elif sessao["step"] == "confirmar":
        if mensagem == "sim":
            resposta.message("📍 Por favor, envie sua *localização* (use o botão do WhatsApp) ou digite o endereço.")
            sessao["step"] = "localizacao"
        else:
            resposta.message("Pedido cancelado. Digite 'Oi' para recomeçar.")
            del user_sessions[remetente]
    
    # Etapa 6: Localização
    elif sessao["step"] == "localizacao":
        # Salva no Google Sheets
        for pedido in sessao["pedidos"]:
            linha = [
                remetente,
                pedido["produto"],
                pedido["sabor"],
                pedido["quantidade"],
                pedido["preco_unitario"],
                mensagem,  # Endereço/localização
                os.getenv("ENVIRONMENT", "local")
            ]
            sheet.append_row(linha)
        
        resposta.message("🍹 *Obrigado pelo seu pedido!* 🚀\nEstamos processando e entraremos em contato em breve.")
        del user_sessions[remetente]  # Limpa a sessão

    return str(resposta)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))