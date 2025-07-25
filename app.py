from flask import Flask, request, abort
from twilio.twiml.messaging_response import MessagingResponse
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import os
import ipaddress
import json

app = Flask(__name__)

# Google Sheets Setup
scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
google_creds = os.getenv("GOOGLE_CREDS")
creds = ServiceAccountCredentials.from_json_keyfile_dict(json.loads(google_creds), scope)
client = gspread.authorize(creds)
sheet = client.open("WhatsAppOrders").sheet1  # Name of your Google Sheet

# Product Menu (customize this!)
products = {
    "1": {"name": "Chocolate Box", "flavors": ["Dark", "Milk", "White"], "price": 12.99},
    "2": {"name": "Cookie Pack", "flavors": ["Vanilla", "Chocolate Chip"], "price": 8.99}
}

# Track user sessions (in-memory for testing)
user_sessions = {}

@app.before_request
def verify_twilio_ip():
    """Verify requests come from Twilio's IP range"""
    twilio_ips = [
        '54.244.51.0/24',
        '54.252.254.64/26',
        '18.228.49.0/24'
    ]
    client_ip = request.headers.get('X-Forwarded-For', request.remote_addr)
    if not any(ipaddress.ip_address(client_ip.split(',')[0].strip()) in ipaddress.ip_network(ip) for ip in twilio_ips):
        abort(403)

@app.route("/whatsapp", methods=["POST"])
def whatsapp_bot():
    incoming_msg = request.values.get("Body", "").strip().lower()
    sender = request.values.get("From", "")
    resp = MessagingResponse()

    # New user: Show product menu
    if sender not in user_sessions:
        user_sessions[sender] = {"step": "choose_product"}
        menu = "Welcome! 🛍️ Choose a product:\n"
        for num, item in products.items():
            menu += f"{num}. {item['name']} (${item['price']})\n"
        resp.message(menu)
    
    # Existing user: Handle their current step
    else:
        current_step = user_sessions[sender]["step"]
        
        # Step 1: Product selection
        if current_step == "choose_product":
            if incoming_msg in products:
                user_sessions[sender]["product"] = incoming_msg
                user_sessions[sender]["step"] = "choose_flavor"
                flavors = "\n".join(products[incoming_msg]["flavors"])
                resp.message(f"Choose a flavor:\n{flavors}")
            else:
                resp.message("❌ Invalid choice. Please reply with the product number (e.g., 1).")
        
        # Step 2: Flavor selection
        elif current_step == "choose_flavor":
            selected_flavors = products[user_sessions[sender]["product"]]["flavors"]
            if incoming_msg.capitalize() in selected_flavors:
                user_sessions[sender]["flavor"] = incoming_msg
                user_sessions[sender]["step"] = "ask_quantity"
                resp.message("How many boxes do you want?")
            else:
                resp.message(f"❌ Invalid flavor. Choose from: {', '.join(selected_flavors)}")
        
        # Step 3: Quantity selection
        elif current_step == "ask_quantity":
            try:
                quantity = int(incoming_msg)
                if quantity <= 0:
                    raise ValueError
                user_sessions[sender]["quantity"] = quantity
                product = products[user_sessions[sender]["product"]]
                total = quantity * product["price"]
                user_sessions[sender]["step"] = "confirm_order"
                resp.message(
                    f"Your order: {quantity}x {product['name']} ({user_sessions[sender]['flavor']})\n"
                    f"Total: ${total:.2f}\n"
                    "Confirm? (yes/no)"
                )
            except ValueError:
                resp.message("❌ Please enter a valid number (e.g., 2)")
        
        # Step 4: Order confirmation
        elif current_step == "confirm_order":
            if incoming_msg.lower() == "yes":
                # Save to Google Sheets
                order = [
                    sender,
                    products[user_sessions[sender]["product"]]["name"],
                    user_sessions[sender]["flavor"],
                    user_sessions[sender]["quantity"],
                    float(products[user_sessions[sender]["product"]]["price"]),
                    "",  # Address placeholder
                    os.environ.get("RAILWAY_ENVIRONMENT", "local")
                ]
                sheet.append_row(order)
                resp.message("✅ Order confirmed! Please share your delivery address.")
                user_sessions[sender]["step"] = "get_address"
            else:
                resp.message("Order canceled. Start over by sending 'Hi'")
                del user_sessions[sender]
        
        # Step 5: Address collection
        elif current_step == "get_address":
            # Update address in Google Sheets
            last_row = len(sheet.get_all_values())
            sheet.update_cell(last_row, 6, incoming_msg)  # Column 6 is address
            resp.message("📦 Thank you! We'll process your order shortly.")
            del user_sessions[sender]

    return str(resp)

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))