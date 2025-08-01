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

# Autenticação Google Sheets - Versão Melhorada
scope = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def load_google_creds():
    google_creds = os.getenv("GOOGLE_CREDS")
    if not google_creds:
        logger.warning("Variável GOOGLE_CREDS não encontrada!")
        return None
    try:
        # Corrige padding do Base64 (se necessário)
        pad = len(google_creds) % 4
        if pad: google_creds += '=' * (4 - pad)
        decoded = base64.b64decode(google_creds).decode('utf-8')
        return json.loads(decoded)
    except Exception as e:
        logger.error(f"Erro ao decodificar credenciais: {str(e)}")
        return None

try:
    creds_dict = load_google_creds()
    if creds_dict:
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        
        # Verifica se a planilha existe e está acessível
        try:
            sheet = client.open("PedidosFrozy").sheet1
            # Testa uma escrita simples
            sheet.append_row(["Teste", "123", "x", "1", "100", "Endereço teste", "local"])
            logger.info("Conexão com Google Sheets OK e escrita testada!")
        except Exception as e:
            logger.error(f"Falha ao acessar a planilha: {str(e)}")
            sheet = None
    else:
        sheet = None
        logger.warning("Modo simulado - sem Google Sheets")
except Exception as e:
    logger.error(f"Falha na inicialização do Google Sheets: {str(e)}")
    sheet = None

# Catálogo de Produtos (Frozy + Truly Juice)    
produtos = {
    "1": {
        "nome": "Frozy Pet 350ml",
        "preco_caixa": 245,
        "unidades_por_caixa": 24,
        "sabores": ["Laranja", "Framboesa", "Limão", "Cola", "Lichia", "Uva", "Coco Ananás", "Manga", "Maçã", "Maracujá"],
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753950420/Frozy_Pet_350ml_jtqsts.jpg"  
    },
    "2": {
        "nome": "Frozy Energy Pet 350ml",
        "preco_caixa": 340,
        "unidades_por_caixa": 24,
        "sabores": ["Energético"],  
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753950152/Frozy_Energy_Pet_350ml_gerkcz.jpg" 
    },
    "3": {
        "nome": "Frozy 2l",
        "preco_caixa": 290,
        "unidades_por_caixa": 6,
        "sabores": ["Laranja", "Framboesa", "Limão", "Cola", "Uva", "Coco Ananás", "Manga"], 
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753950420/Frozy_2l_nd1mlv.jpg" 
    },
    "4": {
        "nome": "Truly Juice 300 ml",
        "preco_caixa": 140,
        "unidades_por_caixa": 12,
        "sabores": ["Laranja", "Mistura Bagas", "Manga", "Guava", "Tropical", "Ananás"], 
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753949872/Truly_Juice_300_ml_deslwp.jpg"
    },
    "5": {
        "nome": "Frozy Lata 330ml",
        "preco_caixa": 440,
        "unidades_por_caixa": 24,
        "sabores": ["Laranja", "Framboesa", "Limão", "Cola", "Lichia", "Uva", "Coco Ananás"],
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753949871/Frozy_Lata_330ml_seqipb.jpg" 
    },
    "6": {
        "nome": "Frozy Energy 300ml",
        "preco_caixa": 490,
        "unidades_por_caixa": 24,
        "sabores": ["Energético"],      
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753949871/Frozy_Energy_300ml_xinmmi.jpg"
    },
    "7": {
        "nome": "Frozy Energy 500ml",
        "preco_caixa": 540,
        "unidades_por_caixa": 24,
        "sabores": ["Energético"], 
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753950152/Frozy_Energy_500ml_zautku.jpg" 
    },
    "8": {
        "nome": "Frozy Dry Lemon 300ml",
        "preco_caixa": 630,
        "unidades_por_caixa": 24,
        "sabores": ["Normal"], 
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753949962/Frozy_Dry_Lemon_300ml_eskw5c.png" 
    },
    "9": {
        "nome": "Frozy Água Tônica 300ml",
        "preco_caixa": 630,
        "unidades_por_caixa": 24,
        "sabores": ["Normal"], 
        "imagem": "https://res.cloudinary.com/dsn5zklgs/image/upload/v1753949961/Frozy_%C3%81gua_T%C3%B4nica_300ml_i5fr5r.jpg" 
    }
}

# Sessões dos Usuários (armazena pedidos em andamento)
user_sessions = {}

@app.route('/whatsapp', methods=['POST'])
def whatsapp_bot():
    # Verifica limites da Twilio
    if os.getenv("TWILIO_STATUS") == "LIMIT_EXCEEDED":
        resp = MessagingResponse()
        resp.message("⚠️ Nosso sistema está em manutenção. Por favor, tente novamente mais tarde.")
        return str(resp)

    mensagem = request.values.get("Body", "").strip().lower()
    remetente = request.values.get("From", "")
    resposta = MessagingResponse()

    # Se é a primeira interação, envia mensagem de boas-vindas + catálogo
    if remetente not in user_sessions:
        user_sessions[remetente] = {"step": "inicio", "pedidos": [], "produto_atual": None,"sabores_adicionados": []}
        
        # Envia imagem do produto principal (ex: logo Frozy)
        resposta.message().media("https://res.cloudinary.com/dsn5zklgs/image/upload/v1753949962/Todos_produtos_czuvkd.jpg")  
        
        # Mensagem de boas-vindas com imagem (opcional)
        resposta.message(
            "🍹 *Bem-vindo à aplicação de requisição de produtos da Frozy!* �\n"
            "📄 Catálogo completo: [Baixe aqui](https://drive.google.com/file/d/14yIAiKxYmhLFnD8Old84L0V9iWPw2bNP/view?usp=sharing)\n\n"
        )
        
        # Lista produtos
        menu = "📋 *Para escolher um produto digite o seu respectivo número:*\n"
        for codigo, produto in produtos.items():
            menu += f"{codigo}. {produto['nome']} - {produto['preco_caixa']} MZN/caixa\n"
        resposta.message(menu)
        return str(resposta)
    
    sessao = user_sessions[remetente]
    
    # Etapa 1: Escolha do Produto
    if sessao["step"] == "inicio":
        if mensagem in produtos:
            sessao["produto_atual"] = mensagem
            sessao["sabores_adicionados"] = []
            sessao["step"] = "escolher_sabor"
            
            # Envia imagem do produto escolhido
            resposta.message().media(produtos[mensagem]["imagem"])
            
           # Lista sabores disponíveis (excluindo já adicionados)
            sabores_disponiveis = [
                sabor for sabor in produtos[mensagem]["sabores"]
                if sabor not in sessao["sabores_adicionados"]
            ]
            
            if not sabores_disponiveis:
                resposta.message("Todos os sabores já foram adicionados! Deseja adicionar outro produto? (sim/não)")
                sessao["step"] = "adicionar_mais"
            else:
                sabores = "\n".join([f"{i+1}. {sabor}" for i, sabor in enumerate(sabores_disponiveis)])
                resposta.message(f"Escolha um sabor para {produtos[mensagem]['nome']}:\n{sabores}")
        else:
            resposta.message("❌ Código inválido. Digite o número do produto (ex: 1).")

    # Etapa 2: Escolha do Sabor
    elif sessao["step"] == "escolher_sabor":
        produto = produtos[sessao["produto_atual"]]
        sabores_disponiveis = [
            sabor for sabor in produto["sabores"]
            if sabor not in sessao["sabores_adicionados"]
        ]
        
        try:
            escolha = int(mensagem) - 1
            if 0 <= escolha < len(sabores_disponiveis):
                sabor_escolhido = sabores_disponiveis[escolha]
                sessao["sabor_atual"] = sabor_escolhido
                sessao["step"] = "quantidade"
                resposta.message(f"Quantas caixas de *{produto['nome']} ({sabor_escolhido})* você deseja?")
            else:
                resposta.message(f"❌ Escolha inválida. Digite um número entre 1 e {len(sabores_disponiveis)}.")
        except ValueError:
            resposta.message("❌ Digite apenas o número do sabor.")

    # Etapa 3: Quantidade
    elif sessao["step"] == "quantidade":
        try:
            quantidade = int(mensagem)
            if quantidade > 0:
                # Adiciona ao pedido
                pedido = {
                    "produto": produtos[sessao["produto_atual"]]["nome"],
                    "sabor": sessao["sabor_atual"],
                    "quantidade": quantidade,
                    "preco_unitario": produtos[sessao["produto_atual"]]["preco_caixa"]
                }
                sessao["pedidos"].append(pedido)
                sessao["sabores_adicionados"].append(sessao["sabor_atual"])
                
                # Pergunta se quer adicionar outro sabor do MESMO produto (alteração 3)
                sabores_restantes = [
                    sabor for sabor in produtos[sessao["produto_atual"]]["sabores"]
                    if sabor not in sessao["sabores_adicionados"]
                ]
                
                if sabores_restantes:
                    resposta.message("✅ Adicionado! Deseja escolher outro sabor para este produto? (sim/não)")
                    sessao["step"] = "outro_sabor"
                else:
                    resposta.message("✅ Todos os sabores foram adicionados! Deseja adicionar outro produto? (sim/não)")
                    sessao["step"] = "adicionar_mais"
            else:
                resposta.message("❌ Digite um número maior que zero.")
        except ValueError:
            resposta.message("❌ Digite um número válido (ex: 2).")

    # Nova Etapa: Adicionar outro sabor do mesmo produto (alteração 4)
    elif sessao["step"] == "outro_sabor":
        if mensagem == "sim":
            sessao["step"] = "escolher_sabor"
            
            # Lista apenas sabores não adicionados
            sabores_disponiveis = [
                sabor for sabor in produtos[sessao["produto_atual"]]["sabores"]
                if sabor not in sessao["sabores_adicionados"]
            ]
            sabores = "\n".join([f"{i+1}. {sabor}" for i, sabor in enumerate(sabores_disponiveis)])
            resposta.message(f"Escolha outro sabor para {produtos[sessao['produto_atual']]['nome']}:\n{sabores}")
        elif mensagem == "não":
            resposta.message("Deseja adicionar outro produto? (sim/não)")
            sessao["step"] = "adicionar_mais"
        else:
            resposta.message("Responda 'sim' ou 'não'.")
    
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
                str(pedido["quantidade"]),
                str(pedido["preco_unitario"]),
                mensagem,  # Endereço/localização
                os.getenv("ENVIRONMENT", "local")
            ]
            sheet.append_row(linha)
        
        resposta.message("🍹 *Obrigado pelo seu pedido!* 🚀\nEstamos processando e entraremos em contato em breve.")
        del user_sessions[remetente]  # Limpa a sessão

    return str(resposta)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))