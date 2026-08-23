DERIV_API_BASE_URL = "https://api.derivws.com"
DERIV_WS_URL = "wss://api.derivws.com/trading/v1/options/ws/public"
DERIV_AUTHENTICATED_WS_BASE = "wss://api.derivws.com/trading/v1/options/ws"
DERIV_OPTIONS_ACCOUNTS_URL = f"{DERIV_API_BASE_URL}/trading/v1/options/accounts"
DERIV_API_EVENTS = {"connected", "disconnected", "authorized", "unauthorized", "balance_updated", "tick_received", "contract_purchased", "contract_sold", "proposal_updated", "heartbeat", "reconnected", "failed_connection"}
