import re
import asyncio
import aiohttp
from datetime import datetime, timedelta
from src.utils import logger, save_json, safe_api_call

async def fetch_recent_swaps(contracts, hyperion_api, hours_back=24, limit=100):
    """
    Busca swaps recentes via API Hyperion para múltiplos contratos.
    Usa aiohttp para chamadas assíncronas.
    """
    all_swaps = []
    now = datetime.utcnow()
    cutoff = now - timedelta(hours=hours_back)

    async with aiohttp.ClientSession() as session:
        tasks = []
        for contract in contracts:
            url = f"{hyperion_api}?account={contract}&filter=transfer&limit={limit}"
            tasks.append(fetch_contract_swaps(session, contract, url, cutoff))
        
        results = await asyncio.gather(*tasks)
        for res in results:
            if res:
                all_swaps.extend(res)
    
    logger.info(f"Total de {len(all_swaps)} swaps recentes capturados.")
    return all_swaps

async def fetch_contract_swaps(session, contract, url, cutoff):
    """
    Busca swaps para um único contrato e filtra.
    """
    logger.info(f"Buscando swaps para contrato: {contract}")
    json_data = await safe_api_call(session, url)
    if not json_data:
        return []

    contract_swaps = []
    actions = json_data.get('actions', [])

    for action in actions:
        act = action.get("act", {})
        data = act.get("data", {})
        
        memo = data.get("memo", "")
        
        # Filtra por transferências *para* o contrato DEX com "deposit" no memo
        if data.get("to") != contract or "deposit" not in memo.lower():
            continue
        
        try:
            timestamp = datetime.fromisoformat(action["@timestamp"].replace("Z", "+00:00"))
        except ValueError:
            logger.warning(f"Timestamp inválido, pulando ação: {action.get('@timestamp')}")
            continue

        if timestamp <= cutoff:
            continue

        parsed_swap = parse_swap_memo(memo, data.get("quantity", ""), contract)
        if parsed_swap:
            # Adiciona metadados da transação
            parsed_swap.update({
                "tx_id": action.get("trx_id"),
                "block_num": action.get("block_num"),
                "timestamp": timestamp.isoformat() + "Z",
                "account": data.get("from"), # O usuário que iniciou a transferência
                "dex": contract,
                "action": act.get("name")
            })
            contract_swaps.append(parsed_swap)
    
    logger.info(f"Encontrados {len(contract_swaps)} swaps válidos para {contract}.")
    return contract_swaps

def parse_swap_memo(memo, quantity_in_str, dex_contract):
    """
    Extrai tokens e quantidades do memo e da quantidade de entrada.
    Retorna um dicionário com token_in, amount_in, token_out, amount_out, e o preço.
    """
    token_in_symbol = None
    amount_in = None
    token_out_symbol = None
    amount_out = None

    # Extrai token_in e amount_in da string de quantidade da ação
    try:
        parts = quantity_in_str.split(" ")
        amount_in = float(parts[0])
        token_in_symbol = parts[1]
    except (ValueError, IndexError):
        logger.warning(f"Não foi possível analisar quantity_in_str: {quantity_in_str}")
        return None

    # Regex para capturar padrões "QUANTIDADE TOKEN" no memo
    # Ex: "deposit:1.50000000 WAX,2.30000000 TACO"
    # Ex: "swap deposit 5.0 WAX for TACO"
    # Ex: "deposit 100.0000 USDT get WAX"
    # Ex: "DEX deposit: 50 WAX -> TACO"
    
    # Procura por todos os pares (quantidade, token) no memo
    memo_quantities = re.findall(r"(\d+\.?\d*)\s+([A-Z]+)", memo)
    
    # Tenta encontrar o token_out e amount_out no memo
    # O token_out é o token que NÃO é o token_in
    for amt_str, tok_sym in memo_quantities:
        if tok_sym != token_in_symbol:
            try:
                amount_out = float(amt_str)
                token_out_symbol = tok_sym
                break
            except ValueError:
                continue
    
    if not token_out_symbol or amount_out is None:
        logger.debug(f"Não foi possível extrair token_out/amount_out do memo: '{memo}' para token_in '{token_in_symbol}'")
        return None

    # Normaliza o par para TACO_WAX (alfabético)
    pair_tokens = sorted([token_in_symbol, token_out_symbol])
    pair_id = f"{pair_tokens[0]}_{pair_tokens[1]}"

    # Calcula o preço do token_out em termos do token_in
    price = amount_out / (amount_in + 1e-8) if amount_in > 0 else 0.0

    return {
        "pair": pair_id,
        "token_in": token_in_symbol,
        "amount_in": amount_in,
        "token_out": token_out_symbol,
        "amount_out": amount_out,
        "price": price,
        "memo": memo # Mantém o memo original para referência
    }

def save_recent_swaps(swaps_data, output_dir="cache/swaps"):
    """Salva os swaps recentes em um arquivo JSON."""
    filepath = os.path.join(output_dir, f"recent_swaps_{datetime.now().strftime('%Y%m%d%H%M%S')}.json")
    save_json(swaps_data, filepath)
    return filepath
